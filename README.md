# Global Supply Chain & Logistics Delay Tracker

**Course:** Data Warehousing – Lesson 3 Prelim Mini Project  
**Project:** Project 2 – Global Supply Chain & Logistics Delay Tracker  
**Group Members:** Hanz Abraham Gonzales and Rafael Ragasa

## 1. Project Overview

This project implements a fault-tolerant Python ETL/data-engineering pipeline for a simulated logistics OLTP source. The pipeline extracts operational records from SQLite, validates the source schema, isolates corrupted records into quarantine files, sanitizes inconsistent text, masks operational tracking identifiers with SHA-256, aggregates shipping-line performance, and writes analytical data as Apache Parquet using Hive-style partition directories.

The project separates the operational SQLite source from the analytical Parquet layer so analytical processing does not depend on repeatedly querying the OLTP source.

## 2. Public Base Dataset

**Dataset:** `global_supply_chain_risk_2026.csv`  
**Source:** Kaggle – *Global Supply Chain Risk & Logistics (2024–2026)*  
**Author:** Nudrat Abbas  
**License:** CC0 / Public Domain

The public dataset contains 5,000 simulated international shipment records with origin/destination ports, transport modes, risk metrics, carrier reliability, lead-time information, and disruption indicators.

The original CSV is preserved unchanged in:

```text
data/raw/global_supply_chain_risk_2026.csv
```

## 3. Academic Adaptation and Transparency

The public CSV does not naturally contain the exact Project 2 schema or the dirty-record patterns required by the mini-project. Therefore, `source_builder.py` constructs a separate simulated OLTP database from the first 4,000 source rows.

The following adaptations are explicitly synthetic and are **not claimed to be original observations from the public dataset**:

- `shipping_line` is assigned deterministic neutral labels `LINE_A` to `LINE_E` because the public dataset contains carrier reliability scores but no carrier names.
- controlled negative transit-duration records are injected;
- controlled missing container IDs are injected;
- controlled whitespace/casing errors are injected into port names.

This provides a reproducible test source for the required fault-tolerant ETL behavior while preserving the original public dataset.

## 4. Pipeline Lineage

```text
Public Internet Dataset
 data/raw/global_supply_chain_risk_2026.csv
                 |
                 v
          source_builder.py
                 |
                 v
       Simulated SQLite OLTP
 database/shop_oltp_p2.db
        table: orders
                 |
                 v
       logistics_pipeline.py
                 |
       +---------+----------+
       |                    |
       v                    v
  Valid records        Invalid records
       |                    |
       |                    +--> quarantine/negative_durations.csv
       |                    +--> quarantine/missing_container_ids.csv
       |
       v
  Sanitize strings
       |
       v
 Aggregate by shipping_line
       |
       +--> data/analytics/shipping_line_performance.parquet
       |
       v
 SHA-256-mask container tracking identifiers
       |
       v
 Hive-style Parquet detail layer
 data/lakehouse/
   shipping_line=LINE_A/
     year=2024/
     year=2025/
       |
       v
 Parquet read-back validation
```

## 5. Simulated OLTP Schema

The SQLite `orders` table contains:

| Column | SQLite type | Purpose |
|---|---|---|
| `order_id` | INTEGER | Primary key |
| `container_id` | TEXT | Operational shipment/container identifier |
| `shipping_line` | TEXT | Deterministic synthetic line label |
| `port_name` | TEXT | Destination port used for cleaning tests |
| `transit_duration_hours` | REAL | `Lead_Time_Days × 24` |
| `order_status` | TEXT | `ARRIVED` |
| `order_date` | TEXT | Operational timestamp |

## 6. Controlled Data-Quality Anomalies

`source_builder.py` uses the fixed seed `42` and creates exactly 4,000 OLTP rows:

| Controlled issue | Rows | Pipeline action |
|---|---:|---|
| Negative transit duration | 160 | Quarantine |
| Missing container ID | 120 | Quarantine |
| Messy port string | 120 | Sanitize and retain |
| **Total rows receiving one controlled issue** | **400 (10%)** | — |

The anomaly groups are disjoint and deterministic.

## 7. Requirements

- Python 3.10+
- pandas 2.2.3
- pyarrow 18.1.0
- SQLite support through Python `sqlite3`
- Python standard libraries: `logging`, `hashlib`, `pathlib`, `shutil`, `time`

Create the environment:

```powershell
python -m venv .venv
```

PowerShell activation, when allowed:

```powershell
.\.venv\Scripts\Activate.ps1
```

If script execution is blocked, the virtual environment can be used directly without activation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## 8. Run the Project

Build/rebuild the simulated OLTP source:

```powershell
python source_builder.py
```

Run the ETL pipeline:

```powershell
python logistics_pipeline.py
```

## 9. Schema Locking

Before extraction, the pipeline reads SQLite metadata using:

```sql
PRAGMA table_info(orders)
```

It compares the real table against the required seven-column schema. Missing columns, unexpected columns, or incompatible declared types cause a logged failure before downstream processing. This prevents silent schema drift.

## 10. Fault Isolation and Quarantine

Row-level validation uses guarded exception boundaries so one bad row does not terminate the entire run.

Records are rejected when they contain conditions such as:

- missing `container_id`;
- missing `shipping_line`;
- missing `port_name`;
- negative `transit_duration_hours`;
- malformed duration values;
- missing or malformed `order_date`.

Required quarantine output:

```text
quarantine/negative_durations.csv
```

Additional diagnostic output:

```text
quarantine/missing_container_ids.csv
```

Each quarantine record includes `quarantine_reason`.

## 11. Sanitization and SHA-256 Masking

Valid port names are trimmed and normalized to title case. Shipping-line and status strings are stripped and normalized to uppercase.

Examples:

```text
"   los angeles   " -> "Los Angeles"
"SHANGHAI"         -> "Shanghai"
```

The raw operational `container_id` remains only in the SQLite source while processing. Before any exported analytical or quarantine output, non-empty container identifiers are transformed using:

```text
SHA-256(container_id) -> 64-character hexadecimal token
```

The final analytical detail layer therefore contains `container_id_hash` and does not expose raw `container_id` values.

## 12. Analytical Transformation

Valid records are grouped by `shipping_line` to calculate:

- unique container count;
- total transit duration in hours;
- average transit duration in hours;
- minimum transit duration in hours;
- maximum transit duration in hours.

Required analytical output:

```text
data/analytics/shipping_line_performance.parquet
```

Expected summary rows: **5** (`LINE_A` to `LINE_E`).

## 13. Hive-Style Parquet Storage

The clean detail layer is written as compressed Parquet partitioned by shipping line and year:

```text
data/lakehouse/
  shipping_line=LINE_A/
    year=2024/
      *.parquet
    year=2025/
      *.parquet
```

The `key=value/` folder naming is the required Hive-style partition structure.

## 14. Logging and Observability

Runtime events are written to:

```text
logs/transit_runs.log
```

The log captures:

- pipeline start/end;
- SQLite connection;
- schema validation;
- extraction row count;
- quarantine counts;
- sanitization;
- SHA-256 masking;
- transformation;
- Parquet writing;
- read-back validation;
- total execution time;
- caught exceptions.

## 15. Idempotency

Repeated execution against the same source produces the same analytical state because:

- quarantine CSVs are overwritten;
- the summary Parquet file is overwritten;
- the Hive-partitioned lakehouse directory is recreated before each write;
- `source_builder.py` rebuilds the source deterministically with seed `42`.

Logs intentionally append because they represent execution history rather than analytical data.

### Verified consecutive runs before final SHA-256 hardening

```text
Run 1: source=4000 | valid=3720 | quarantined=280 | summary=5 | 1.748s
Run 2: source=4000 | valid=3720 | quarantined=280 | summary=5 | 1.706s
```

The identical data counts demonstrate idempotent output behavior. After applying the final SHA-256 hardening change, rerun the pipeline twice and confirm the same counts.

## 16. Output Read-Back Validation

After writing Parquet, the pipeline reads the outputs again and checks:

- expected summary row count;
- expected summary columns;
- expected detail row count;
- no negative durations in analytical detail;
- raw `container_id` is absent from analytical detail;
- `container_id_hash` exists and matches a 64-character SHA-256 hexadecimal format.

## 17. Expected Final Results

```text
Source rows:        4000
Valid rows:         3720
Quarantined rows:    280
Negative durations:  160
Missing IDs:         120
Summary rows:          5
```

Execution should remain comfortably under the five-second excellent-rubric target on the tested machine.

## 18. Repository Structure

```text
global_supply_chain_logistics_project/
|
+-- data/
|   +-- raw/
|   |   +-- global_supply_chain_risk_2026.csv
|   +-- analytics/
|   |   +-- shipping_line_performance.parquet
|   +-- lakehouse/
|       +-- shipping_line=LINE_A/
|       +-- shipping_line=LINE_B/
|       +-- shipping_line=LINE_C/
|       +-- shipping_line=LINE_D/
|       +-- shipping_line=LINE_E/
|
+-- database/
|   +-- shop_oltp_p2.db
+-- logs/
|   +-- transit_runs.log
+-- quarantine/
|   +-- negative_durations.csv
|   +-- missing_container_ids.csv
+-- source_builder.py
+-- logistics_pipeline.py
+-- requirements.txt
+-- .gitignore
+-- README.md
+-- DataOps_Report.md
+-- FINAL_RUBRIC_AUDIT.md
+-- FINAL_SUBMISSION_CHECKLIST.md
+-- GIT_WORKFLOW.md
```

## 19. Quick Defense Answers

**Why separate OLTP and analytics?**  
The SQLite source represents operational data, while Parquet is optimized for analytical workloads. Separating them protects the transactional source from analytical processing.

**What is quarantine?**  
It preserves invalid records for inspection instead of silently deleting them or allowing them to crash the pipeline.

**What is schema locking?**  
The pipeline verifies the expected table structure before processing so unexpected schema changes cannot silently corrupt downstream results.

**What is idempotency?**  
Running the pipeline repeatedly with the same source produces the same final analytical state without duplicate rows.

**Why SHA-256?**  
It replaces the operational container tracking identifier with a fixed-length one-way token before external analytical output.

**Why Parquet?**  
Parquet is compressed, column-oriented analytical storage that preserves data types and supports efficient query access.

**What is Hive-style partitioning?**  
It organizes files in `key=value/` directories such as `shipping_line=LINE_A/year=2024/`.
