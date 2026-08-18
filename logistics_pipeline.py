from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database" / "shop_oltp_p2.db"
TABLE_NAME = "orders"
LOG_PATH = BASE_DIR / "logs" / "transit_runs.log"
QUARANTINE_DIR = BASE_DIR / "quarantine"
NEGATIVE_QUARANTINE_PATH = QUARANTINE_DIR / "negative_durations.csv"
MISSING_ID_QUARANTINE_PATH = QUARANTINE_DIR / "missing_container_ids.csv"
ANALYTICS_DIR = BASE_DIR / "data" / "analytics"
SUMMARY_PARQUET_PATH = ANALYTICS_DIR / "shipping_line_performance.parquet"
LAKEHOUSE_DIR = BASE_DIR / "data" / "lakehouse"

EXPECTED_SCHEMA = {
    "order_id": "INTEGER",
    "container_id": "TEXT",
    "shipping_line": "TEXT",
    "port_name": "TEXT",
    "transit_duration_hours": "REAL",
    "order_status": "TEXT",
    "order_date": "TEXT",
}


def setup_directories() -> None:
    for path in [LOG_PATH.parent, QUARANTINE_DIR, ANALYTICS_DIR, LAKEHOUSE_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("logistics_pipeline")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def connect_database(logger: logging.Logger) -> sqlite3.Connection:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"SQLite database not found: {DATABASE_PATH}. Run source_builder.py first."
        )
    logger.info("Connecting to SQLite source: %s", DATABASE_PATH)
    return sqlite3.connect(DATABASE_PATH)


def validate_schema(connection: sqlite3.Connection, logger: logging.Logger) -> None:
    logger.info("Validating source schema for table '%s'.", TABLE_NAME)
    schema_rows = connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    if not schema_rows:
        raise ValueError(f"Required table '{TABLE_NAME}' does not exist.")

    actual_schema = {row[1]: str(row[2]).upper() for row in schema_rows}

    actual_columns = set(actual_schema)
    expected_columns = set(EXPECTED_SCHEMA)
    missing_columns = expected_columns - actual_columns
    unexpected_columns = actual_columns - expected_columns

    if missing_columns or unexpected_columns:
        raise ValueError(
            "Schema lock failed. "
            f"Missing columns: {sorted(missing_columns)}; "
            f"Unexpected columns: {sorted(unexpected_columns)}"
        )

    mismatched_types = []
    for column, expected_type in EXPECTED_SCHEMA.items():
        actual_type = actual_schema[column]
        if actual_type != expected_type:
            mismatched_types.append(
                f"{column}: expected {expected_type}, found {actual_type}"
            )

    if mismatched_types:
        raise ValueError("Schema type mismatch: " + "; ".join(mismatched_types))

    logger.info("Schema lock passed with %d expected columns.", len(EXPECTED_SCHEMA))


def extract_data(connection: sqlite3.Connection, logger: logging.Logger) -> pd.DataFrame:
    logger.info("Extracting operational records from SQLite.")
    dataframe = pd.read_sql_query(
        f"SELECT * FROM {TABLE_NAME} ORDER BY order_id", connection
    )
    logger.info("Extracted %d source rows.", len(dataframe))
    return dataframe


def _is_missing(value: object) -> bool:
    return pd.isna(value) or str(value).strip() == ""




def hash_identifier(value: object) -> str | None:
    """Return a SHA-256 token for a non-empty operational identifier."""
    if _is_missing(value):
        return None
    normalized = str(value).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def protect_identifier_output(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove raw container IDs and keep only SHA-256 tokens in exported data."""
    protected = dataframe.copy()
    if "container_id" in protected.columns:
        protected["container_id_hash"] = protected["container_id"].map(hash_identifier)
        protected = protected.drop(columns=["container_id"])
    return protected


def validate_record(record: dict) -> list[str]:
    """Return validation errors for one operational record."""
    errors: list[str] = []

    try:
        if _is_missing(record.get("container_id")):
            errors.append("MISSING_CONTAINER_ID")

        if _is_missing(record.get("shipping_line")):
            errors.append("MISSING_SHIPPING_LINE")

        if _is_missing(record.get("port_name")):
            errors.append("MISSING_PORT_NAME")

        duration = float(record.get("transit_duration_hours"))
        if duration < 0:
            errors.append("NEGATIVE_TRANSIT_DURATION")

        if _is_missing(record.get("order_date")):
            errors.append("MISSING_ORDER_DATE")
        else:
            pd.to_datetime(record["order_date"], errors="raise")

    except (TypeError, ValueError, OverflowError) as exc:
        errors.append(f"MALFORMED_VALUE:{type(exc).__name__}")

    return errors


def validate_and_quarantine(
    dataframe: pd.DataFrame, logger: logging.Logger
) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger.info("Validating %d records and isolating invalid rows.", len(dataframe))

    invalid_rows: list[dict] = []
    valid_rows: list[dict] = []

    for record in dataframe.to_dict(orient="records"):
        try:
            errors = validate_record(record)
            if errors:
                quarantined = record.copy()
                quarantined["quarantine_reason"] = ";".join(errors)
                invalid_rows.append(quarantined)
            else:
                valid_rows.append(record)
        except Exception as exc:  # Last-resort row boundary: do not kill the run.
            quarantined = record.copy()
            quarantined["quarantine_reason"] = (
                f"UNEXPECTED_VALIDATION_ERROR:{type(exc).__name__}"
            )
            invalid_rows.append(quarantined)
            logger.exception(
                "Unexpected row-level validation error for order_id=%s",
                record.get("order_id"),
            )

    valid_df = pd.DataFrame(valid_rows, columns=dataframe.columns)
    invalid_df = pd.DataFrame(invalid_rows)

    negative_df = (
        invalid_df[
            invalid_df["quarantine_reason"].str.contains(
                "NEGATIVE_TRANSIT_DURATION", na=False
            )
        ].copy()
        if not invalid_df.empty
        else pd.DataFrame(columns=[*dataframe.columns, "quarantine_reason"])
    )

    missing_id_df = (
        invalid_df[
            invalid_df["quarantine_reason"].str.contains(
                "MISSING_CONTAINER_ID", na=False
            )
        ].copy()
        if not invalid_df.empty
        else pd.DataFrame(columns=[*dataframe.columns, "quarantine_reason"])
    )

    # Protect the operational tracking identifier before any non-OLTP export.
    negative_output = protect_identifier_output(negative_df)
    missing_id_output = protect_identifier_output(missing_id_df)

    # Overwrite operational quarantine outputs on every run for idempotency.
    negative_output.to_csv(NEGATIVE_QUARANTINE_PATH, index=False)
    missing_id_output.to_csv(MISSING_ID_QUARANTINE_PATH, index=False)
    logger.info("Applied SHA-256 masking to container tracking identifiers in quarantine outputs.")

    logger.warning("Quarantined %d invalid rows in total.", len(invalid_df))
    logger.info(
        "Negative-duration quarantine rows: %d; missing-container rows: %d.",
        len(negative_df),
        len(missing_id_df),
    )

    return valid_df, invalid_df


def sanitize_data(dataframe: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    logger.info("Sanitizing port and shipping-line strings.")
    clean = dataframe.copy()

    clean["port_name"] = (
        clean["port_name"].astype("string").str.strip().str.title()
    )
    clean["shipping_line"] = (
        clean["shipping_line"].astype("string").str.strip().str.upper()
    )
    clean["order_status"] = (
        clean["order_status"].astype("string").str.strip().str.upper()
    )
    clean["transit_duration_hours"] = pd.to_numeric(
        clean["transit_duration_hours"], errors="raise"
    )
    clean["order_date"] = pd.to_datetime(clean["order_date"], errors="raise")
    clean["year"] = clean["order_date"].dt.year.astype("int64")

    return clean


def mask_analytical_identifiers(
    dataframe: pd.DataFrame, logger: logging.Logger
) -> pd.DataFrame:
    logger.info("Masking container tracking identifiers with SHA-256 for analytical output.")
    return protect_identifier_output(dataframe)


def transform_data(dataframe: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    logger.info("Aggregating shipping-line performance metrics.")
    summary = (
        dataframe.groupby("shipping_line", as_index=False)
        .agg(
            container_count=("container_id", "nunique"),
            total_transit_duration_hours=("transit_duration_hours", "sum"),
            average_transit_duration_hours=("transit_duration_hours", "mean"),
            minimum_transit_duration_hours=("transit_duration_hours", "min"),
            maximum_transit_duration_hours=("transit_duration_hours", "max"),
        )
        .sort_values("shipping_line")
        .reset_index(drop=True)
    )

    for column in [
        "total_transit_duration_hours",
        "average_transit_duration_hours",
        "minimum_transit_duration_hours",
        "maximum_transit_duration_hours",
    ]:
        summary[column] = summary[column].round(2)

    return summary


def write_parquet(
    clean_detail: pd.DataFrame, summary: pd.DataFrame, logger: logging.Logger
) -> None:
    logger.info("Writing required analytical Parquet summary.")

    # A single required summary artifact from the Project 2 specification.
    summary.to_parquet(
        SUMMARY_PARQUET_PATH,
        engine="pyarrow",
        compression="snappy",
        index=False,
    )

    # Common project constraints require Hive-style key=value partitioning.
    # Recreate the lakehouse directory before each run to guarantee idempotency.
    if LAKEHOUSE_DIR.exists():
        shutil.rmtree(LAKEHOUSE_DIR)
    LAKEHOUSE_DIR.mkdir(parents=True, exist_ok=True)

    partition_columns = ["shipping_line", "year"]
    clean_detail.to_parquet(
        LAKEHOUSE_DIR,
        engine="pyarrow",
        compression="snappy",
        index=False,
        partition_cols=partition_columns,
    )

    logger.info(
        "Wrote Hive-style detail partitions by shipping_line and year under %s.",
        LAKEHOUSE_DIR,
    )


def validate_output(
    expected_clean_rows: int,
    expected_summary_rows: int,
    logger: logging.Logger,
) -> None:
    logger.info("Performing Parquet read-back validation.")

    summary_readback = pd.read_parquet(SUMMARY_PARQUET_PATH, engine="pyarrow")
    if len(summary_readback) != expected_summary_rows:
        raise ValueError(
            "Summary read-back row count mismatch: "
            f"expected {expected_summary_rows}, got {len(summary_readback)}"
        )

    expected_summary_columns = {
        "shipping_line",
        "container_count",
        "total_transit_duration_hours",
        "average_transit_duration_hours",
        "minimum_transit_duration_hours",
        "maximum_transit_duration_hours",
    }
    if set(summary_readback.columns) != expected_summary_columns:
        raise ValueError(
            "Summary Parquet schema mismatch. "
            f"Found columns: {summary_readback.columns.tolist()}"
        )

    detail_readback = pd.read_parquet(LAKEHOUSE_DIR, engine="pyarrow")
    if len(detail_readback) != expected_clean_rows:
        raise ValueError(
            "Partitioned detail row count mismatch: "
            f"expected {expected_clean_rows}, got {len(detail_readback)}"
        )

    negative_partition_rows = (
        pd.to_numeric(detail_readback["transit_duration_hours"], errors="coerce") < 0
    ).sum()
    if negative_partition_rows:
        raise ValueError(
            f"Invalid negative durations leaked into analytical layer: {negative_partition_rows}"
        )

    if "container_id" in detail_readback.columns:
        raise ValueError("Raw container IDs leaked into the analytical layer.")

    if "container_id_hash" not in detail_readback.columns:
        raise ValueError("Expected SHA-256 container_id_hash is missing from analytical detail.")

    hashes = detail_readback["container_id_hash"].astype("string")
    if hashes.isna().any() or not hashes.str.fullmatch(r"[0-9a-f]{64}").all():
        raise ValueError("Invalid SHA-256 container identifier tokens found in analytical detail.")

    logger.info("Parquet read-back validation passed, including SHA-256 masking checks.")


def main() -> None:
    start_time = time.perf_counter()
    setup_directories()
    logger = configure_logging()
    logger.info("========== PROJECT 2 PIPELINE START ==========")

    source_count = 0
    valid_count = 0
    quarantined_count = 0
    output_count = 0

    try:
        with connect_database(logger) as connection:
            validate_schema(connection, logger)
            source_df = extract_data(connection, logger)

        source_count = len(source_df)
        valid_df, invalid_df = validate_and_quarantine(source_df, logger)
        valid_count = len(valid_df)
        quarantined_count = len(invalid_df)

        clean_df = sanitize_data(valid_df, logger)
        summary_df = transform_data(clean_df, logger)
        protected_detail_df = mask_analytical_identifiers(clean_df, logger)
        output_count = len(summary_df)

        write_parquet(protected_detail_df, summary_df, logger)
        validate_output(valid_count, output_count, logger)

        elapsed = time.perf_counter() - start_time
        logger.info(
            "Pipeline summary | source=%d | valid=%d | quarantined=%d | "
            "summary_rows=%d | duration=%.3fs",
            source_count,
            valid_count,
            quarantined_count,
            output_count,
            elapsed,
        )
        logger.info("========== PROJECT 2 PIPELINE SUCCESS ==========")

        print("\nPipeline completed successfully.")
        print(f"Source rows:       {source_count}")
        print(f"Valid rows:        {valid_count}")
        print(f"Quarantined rows:  {quarantined_count}")
        print(f"Summary rows:      {output_count}")
        print(f"Execution time:    {elapsed:.3f} seconds")
        print(f"Summary Parquet:   {SUMMARY_PARQUET_PATH}")
        print(f"Partitioned data:  {LAKEHOUSE_DIR}")

    except Exception:
        logger.exception("Pipeline failed.")
        raise


if __name__ == "__main__":
    main()
