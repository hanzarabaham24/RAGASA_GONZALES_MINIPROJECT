from __future__ import annotations

import logging
import random
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SOURCE_CSV = BASE_DIR / "data" / "raw" / "global_supply_chain_risk_2026.csv"
DATABASE_PATH = BASE_DIR / "database" / "shop_oltp_p2.db"
TABLE_NAME = "orders"
SOURCE_ROW_LIMIT = 4000
RANDOM_SEED = 42

# Controlled anomaly counts. Together they affect 10% of the 4,000-row OLTP source.
NEGATIVE_DURATION_COUNT = 160
MISSING_CONTAINER_COUNT = 120
MESSY_PORT_COUNT = 120

SHIPPING_LINES = ["LINE_A", "LINE_B", "LINE_C", "LINE_D", "LINE_E"]


def assign_shipping_line(order_id: int) -> str:
    """Deterministically assign a neutral synthetic shipping-line label."""
    return SHIPPING_LINES[(order_id - 1) % len(SHIPPING_LINES)]


def make_messy_port(value: str, pattern_number: int) -> str:
    """Create controlled string-quality anomalies for pipeline cleaning tests."""
    value = str(value)
    pattern = pattern_number % 3
    if pattern == 0:
        return f"   {value.lower()}   "
    if pattern == 1:
        return value.upper()
    return f"  {value.swapcase()} "


def build_oltp_source() -> None:
    if not SOURCE_CSV.exists():
        raise FileNotFoundError(f"Source CSV not found: {SOURCE_CSV}")

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(SOURCE_CSV).head(SOURCE_ROW_LIMIT).copy()
    if len(source) != SOURCE_ROW_LIMIT:
        raise ValueError(
            f"Expected at least {SOURCE_ROW_LIMIT} source rows, found {len(source)}."
        )

    required_source_columns = {
        "Shipment_ID",
        "Date",
        "Destination_Port",
        "Lead_Time_Days",
    }
    missing = required_source_columns - set(source.columns)
    if missing:
        raise ValueError(f"Source CSV is missing required columns: {sorted(missing)}")

    orders = pd.DataFrame()
    orders["order_id"] = range(1, SOURCE_ROW_LIMIT + 1)
    orders["container_id"] = source["Shipment_ID"].astype("string")
    orders["shipping_line"] = orders["order_id"].map(assign_shipping_line)
    orders["port_name"] = source["Destination_Port"].astype("string")
    orders["transit_duration_hours"] = (
        pd.to_numeric(source["Lead_Time_Days"], errors="raise") * 24
    ).round(2)
    orders["order_status"] = "ARRIVED"
    orders["order_date"] = pd.to_datetime(source["Date"], errors="raise").dt.strftime(
        "%Y-%m-%d 00:00:00"
    )

    # Pick disjoint row sets so exactly 10% of records receive one controlled anomaly.
    rng = random.Random(RANDOM_SEED)
    all_indices = list(range(SOURCE_ROW_LIMIT))
    rng.shuffle(all_indices)

    negative_idx = all_indices[:NEGATIVE_DURATION_COUNT]
    missing_idx = all_indices[
        NEGATIVE_DURATION_COUNT : NEGATIVE_DURATION_COUNT + MISSING_CONTAINER_COUNT
    ]
    messy_idx = all_indices[
        NEGATIVE_DURATION_COUNT + MISSING_CONTAINER_COUNT :
        NEGATIVE_DURATION_COUNT + MISSING_CONTAINER_COUNT + MESSY_PORT_COUNT
    ]

    orders.loc[negative_idx, "transit_duration_hours"] *= -1
    orders.loc[missing_idx, "container_id"] = None

    for n, idx in enumerate(messy_idx):
        orders.at[idx, "port_name"] = make_messy_port(orders.at[idx, "port_name"], n)

    # Rebuild the SQLite database from scratch for deterministic source generation.
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            f"""
            CREATE TABLE {TABLE_NAME} (
                order_id INTEGER PRIMARY KEY,
                container_id TEXT,
                shipping_line TEXT NOT NULL,
                port_name TEXT NOT NULL,
                transit_duration_hours REAL NOT NULL,
                order_status TEXT NOT NULL,
                order_date TEXT NOT NULL
            )
            """
        )
        orders.to_sql(TABLE_NAME, connection, if_exists="append", index=False)
        connection.commit()

    print(f"Created: {DATABASE_PATH}")
    print(f"Rows: {len(orders)}")
    print(f"Negative durations injected: {len(negative_idx)}")
    print(f"Missing container IDs injected: {len(missing_idx)}")
    print(f"Messy port strings injected: {len(messy_idx)}")
    print(f"Controlled anomaly rows: {len(negative_idx) + len(missing_idx) + len(messy_idx)}")


if __name__ == "__main__":
    build_oltp_source()
