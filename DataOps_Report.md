# DataOps Report – Project 2

**Project:** Global Supply Chain & Logistics Delay Tracker  
**Group Members:** Hanz Abraham Gonzales and Rafael Ragasa

## 1. OLTP and OLAP Separation

The SQLite `orders` database represents the simulated operational/transactional source. The pipeline extracts records from this OLTP layer and writes analytical results to Apache Parquet instead of running analytical processing directly against the operational source. This separation supports system reliability and creates a storage layer designed for analytical access.

## 2. Reliability and Fault Isolation

The pipeline validates records at a row boundary. Invalid records are quarantined instead of being silently deleted or allowed to terminate the entire runtime. Negative transit durations and missing container identifiers are written to segregated quarantine CSV files with a `quarantine_reason` field for diagnosis.

A final row-level `try-except` boundary protects the pipeline from unexpected malformed values. This lets valid records continue through processing even when individual source records fail validation.

## 3. Schema Locking

Before extraction, the pipeline runs SQLite `PRAGMA table_info(orders)` and compares the actual source table against the expected Project 2 schema:

- `order_id` – INTEGER
- `container_id` – TEXT
- `shipping_line` – TEXT
- `port_name` – TEXT
- `transit_duration_hours` – REAL
- `order_status` – TEXT
- `order_date` – TEXT

Missing columns, unexpected columns, or incompatible declared types stop the run before transformation. This prevents schema drift from silently corrupting downstream analytics.

## 4. Idempotency

For the same SQLite source, repeated executions produce the same analytical state. The design enforces this by:

- overwriting quarantine CSV files instead of appending;
- overwriting the summary Parquet file;
- recreating the Hive-style lakehouse directory before each write;
- rebuilding the simulated source deterministically with random seed `42`.

Two consecutive local runs produced identical data counts:

```text
Run 1: source=4000 | valid=3720 | quarantined=280 | summary=5
Run 2: source=4000 | valid=3720 | quarantined=280 | summary=5
```

The log file is intentionally appended because it records execution history and is not part of the analytical dataset.

## 5. Observability

Python's `logging` module records timestamped pipeline events in `logs/transit_runs.log`. The log captures:

- pipeline start and completion;
- SQLite connection;
- schema-lock result;
- extracted source count;
- quarantine counts;
- string sanitization;
- SHA-256 identifier masking;
- aggregation;
- Parquet writing;
- Hive partition creation;
- Parquet read-back validation;
- execution duration;
- caught exceptions.

This provides an auditable execution trace for DataOps troubleshooting and verification.

## 6. Data Sanitization

Operational `port_name` values may contain leading/trailing whitespace and inconsistent casing. The pipeline standardizes them using trimming and title casing. Shipping-line and status strings are stripped and normalized to uppercase.

These transformations prevent logically identical values such as `" Shanghai "`, `"SHANGHAI"`, and `"shanghai"` from being treated as different analytical categories.

## 7. SHA-256 Data Protection

Project 2 does not contain personal customer PII, but it does contain an operational tracking identifier (`container_id`). To satisfy the common data-protection requirement without inventing personal data, the pipeline applies SHA-256 pseudonymization to this tracking identifier before it is written outside the OLTP source.

Implementation:

```text
container_id -> hashlib.sha256(...) -> container_id_hash
```

The raw `container_id` is removed from exported analytical detail and quarantine output. The generated `container_id_hash` is a fixed 64-character hexadecimal token. Read-back validation verifies that raw container IDs do not leak into the analytical layer.

## 8. Apache Parquet and Hive-Style Storage

The required shipping-line analytical summary is stored as compressed Apache Parquet:

```text
data/analytics/shipping_line_performance.parquet
```

A clean detail layer is stored using native Hive-style partitions:

```text
data/lakehouse/shipping_line=<value>/year=<value>/
```

This `key=value/` structure allows partition-aware analytical engines to locate subsets of data efficiently. Parquet also preserves analytical data types and uses compressed column-oriented storage.

## 9. Analytical Transformation

After invalid rows are quarantined and valid data is sanitized, records are grouped by `shipping_line`. The summary contains:

- unique container count;
- total transit duration in hours;
- average transit duration in hours;
- minimum transit duration in hours;
- maximum transit duration in hours.

The expected final summary contains five rows, one for each deterministic synthetic shipping line.

## 10. Data Lineage

```text
Public CSV
    -> source_builder.py
    -> simulated SQLite OLTP: shop_oltp_p2.db / orders
    -> schema lock
    -> extraction
    -> row validation
       -> invalid -> quarantine CSV + SHA-256 masking
       -> valid   -> sanitization
    -> shipping-line aggregation
    -> SHA-256 mask container tracking ID in detail layer
    -> summary Parquet
    -> Hive-partitioned detail Parquet
    -> Parquet read-back validation
    -> timestamped execution log
```

## 11. Controlled Test Data and Reproducibility

The original public CSV is preserved. The SQLite source is a coursework simulation built from the first 4,000 source rows. Neutral synthetic shipping-line labels and controlled data-quality anomalies are introduced only in the simulated copy to exercise the required validation and fault-isolation mechanisms.

The builder uses fixed seed `42`, so the same source rows receive the same controlled anomalies whenever the simulated database is rebuilt.

## 12. Reliability Summary

The architecture follows the core reliability goals expected from a data pipeline:

- **Reliability:** bad rows are isolated without terminating valid processing.
- **Maintainability:** logic is split into clear functions for setup, extraction, validation, sanitization, protection, transformation, storage, and read-back checks.
- **Scalability:** analytical output uses Parquet and Hive-style partitions rather than flat text as the final analytical layer.
- **Idempotency:** repeated executions do not duplicate analytical data.
- **Observability:** timestamped logs expose what the pipeline did during each run.
- **Schema consistency:** the pipeline refuses incompatible source structures before transformation.
