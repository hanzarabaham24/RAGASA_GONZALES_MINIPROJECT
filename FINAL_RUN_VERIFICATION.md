# Final Run Verification

This file records the final local execution result for Project 2 – Global Supply Chain & Logistics Delay Tracker.

## Verified Execution

The pipeline was executed successfully from the project virtual environment after rebuilding the simulated SQLite OLTP source.

```text
Source rows:       4000
Valid rows:        3720
Quarantined rows:   280
Summary rows:         5
Execution time:    1.709 seconds
```

Additional successful checks reported by the pipeline:

- SQLite connection and extraction succeeded.
- Schema lock passed with all 7 expected columns.
- 160 negative-duration rows were quarantined.
- 120 missing-container rows were quarantined.
- SHA-256 masking was applied to container tracking identifiers in exported outputs.
- Port and shipping-line strings were sanitized.
- Shipping-line performance aggregation completed.
- Required analytical Parquet summary was written.
- Hive-style detail partitions were written by `shipping_line` and `year`.
- Parquet read-back validation passed, including SHA-256 masking checks.
- The pipeline completed successfully in under five seconds.

## Group Members

- Hanz Abraham Gonzales
- Rafael Ragasa
