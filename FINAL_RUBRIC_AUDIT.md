# Final Rubric Audit – Project 2

**Project:** Global Supply Chain & Logistics Delay Tracker  
**Group:** Hanz Abraham Gonzales and Rafael Ragasa

This audit maps the implementation to the five official rubric components. It is a readiness audit, not a guarantee of the instructor's final grade.

## 1. Ingestion Engine & Execution Logic — 20 points

**Status: PASS**

Evidence:

- Uses Python `sqlite3` to connect to `database/shop_oltp_p2.db`.
- Reads from the `orders` table through pandas.
- Performs schema locking before extraction.
- Local execution extracted exactly 4,000 rows.
- Two observed runs completed in approximately 1.748 s and 1.706 s, both below the five-second excellent threshold.
- Top-level exception handling logs failures instead of hiding them.

## 2. Fault Isolation & Quarantine Strategy — 25 points

**Status: PASS**

Evidence:

- Row-level validation uses guarded exception boundaries.
- Invalid rows do not stop valid records from continuing.
- 160 negative-duration rows are written to `quarantine/negative_durations.csv`.
- 120 missing-ID rows are written to `quarantine/missing_container_ids.csv`.
- Every quarantine row includes `quarantine_reason`.
- Quarantine files are overwritten per run for idempotency.

Expected totals:

```text
Source:       4000
Valid:        3720
Quarantined:   280
```

## 3. PII Masking & Data Sanitization — 20 points

**Status: PASS AFTER FINAL LOCAL RERUN**

Evidence in final code:

- Port strings use `.str.strip()` plus normalized casing.
- Shipping-line and status strings are standardized.
- `hashlib.sha256()` pseudonymizes non-empty `container_id` values.
- Raw `container_id` is removed from exported analytical detail.
- Quarantine exports also mask non-empty container tracking IDs.
- Read-back validation rejects analytical output if raw `container_id` is present or if hashes are not valid 64-character hexadecimal SHA-256 tokens.

Final local verification command:

```powershell
python logistics_pipeline.py
```

## 4. Storage Serialization & Partitioning — 20 points

**Status: PASS**

Evidence:

- Required summary is Apache Parquet: `data/analytics/shipping_line_performance.parquet`.
- Uses `pyarrow` with Snappy compression.
- Detail output is Hive-style partitioned by:

```text
shipping_line=<value>/year=<value>/
```

- Pipeline performs Parquet read-back validation.
- Final analytical layer is not CSV/JSON.

## 5. DataOps Observability & Idempotency — 15 points

**Status: PASS**

Evidence:

- Timestamped structured execution log is written to `logs/transit_runs.log`.
- Log captures major milestones, counts, duration, and errors.
- Quarantine and summary outputs overwrite rather than append.
- Lakehouse partitions are recreated before writing.
- Source builder uses fixed seed `42`.
- Two consecutive observed runs produced the same counts:

```text
Run 1: 4000 source / 3720 valid / 280 quarantine / 5 summary
Run 2: 4000 source / 3720 valid / 280 quarantine / 5 summary
```

## Readiness Summary

| Rubric Component | Max | Readiness |
|---|---:|---|
| Ingestion Engine & Execution Logic | 20 | PASS |
| Fault Isolation & Quarantine | 25 | PASS |
| PII Masking & Sanitization | 20 | PASS after final rerun |
| Parquet & Hive Partitioning | 20 | PASS |
| Observability & Idempotency | 15 | PASS |
| **Total coverage** | **100** | **Implementation covers all categories** |

## Final Required Verification

After applying the final SHA-256 code hardening, run the pipeline twice and confirm both runs still report:

```text
Source rows:       4000
Valid rows:        3720
Quarantined rows:   280
Summary rows:         5
```

Then inspect one detail Parquet file and confirm the identifier column is `container_id_hash`, not raw `container_id`.
