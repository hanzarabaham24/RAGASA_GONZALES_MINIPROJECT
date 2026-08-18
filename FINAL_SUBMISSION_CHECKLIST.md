# Final Submission Checklist

Use this immediately before submitting the GitHub repository link.

## Local technical verification

- [ ] `.venv` is active or commands explicitly use `.venv\Scripts\python.exe`.
- [ ] `python source_builder.py` completes successfully.
- [ ] `python logistics_pipeline.py` completes successfully.
- [ ] Run `python logistics_pipeline.py` a second time.
- [ ] Both runs show `4000` source rows.
- [ ] Both runs show `3720` valid rows.
- [ ] Both runs show `280` quarantined rows.
- [ ] Both runs show `5` summary rows.
- [ ] Execution remains under 5 seconds on the submission machine.

## Required Project 2 artifacts

- [ ] `logistics_pipeline.py`
- [ ] `logs/transit_runs.log`
- [ ] `quarantine/negative_durations.csv`
- [ ] `data/analytics/shipping_line_performance.parquet`
- [ ] `README.md`
- [ ] README contains a pipeline lineage diagram.

## Common technical requirements

- [ ] `database/shop_oltp_p2.db` exists.
- [ ] `requirements.txt` is present and version-locked.
- [ ] `.venv/` is NOT committed.
- [ ] `__pycache__/` and `*.pyc` are NOT committed.
- [ ] `data/lakehouse/` contains `shipping_line=<value>/year=<value>/` folders.
- [ ] Parquet files open successfully in a Parquet viewer.
- [ ] `negative_durations.csv` contains 160 rejected negative-duration rows.
- [ ] `missing_container_ids.csv` contains 120 missing-ID rows.
- [ ] Analytical detail contains `container_id_hash`.
- [ ] Analytical detail does NOT contain raw `container_id`.
- [ ] `container_id_hash` values are 64 hexadecimal characters.
- [ ] `logs/transit_runs.log` contains the final successful executions.

## Documentation

- [ ] Group members are listed as Hanz Abraham Gonzales and Rafael Ragasa.
- [ ] Dataset source is documented.
- [ ] Synthetic shipping-line labels are clearly disclosed.
- [ ] Controlled anomaly injection is clearly disclosed.
- [ ] OLTP vs OLAP is explained.
- [ ] Schema locking is explained.
- [ ] Fault isolation/quarantine is explained.
- [ ] SHA-256 masking is explained.
- [ ] Parquet and Hive partitioning are explained.
- [ ] Idempotency is explained with repeated-run evidence.

## GitHub

- [ ] Repository exists on GitHub.
- [ ] Repository does not contain `.venv/` or `__pycache__/`.
- [ ] Both members have repository access if required.
- [ ] At least the remaining final code hardening was performed on a real feature branch.
- [ ] Documentation finalization was performed on a real feature branch.
- [ ] Pull Requests were genuinely opened, reviewed, and merged.
- [ ] `main` contains the final tested version.
- [ ] GitHub repository link opens correctly for the instructor.

## Final inspection

- [ ] Open `README.md` on GitHub and verify the lineage diagram renders/readably displays.
- [ ] Open the final log and confirm `PROJECT 2 PIPELINE SUCCESS`.
- [ ] Check repository status with `git status`; it should be clean.
- [ ] Submit the repository link before the deadline.
