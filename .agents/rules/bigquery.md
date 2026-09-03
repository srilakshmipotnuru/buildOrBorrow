# BigQuery Query & Dataset Verification Rules

When developing, proposing, or executing BigQuery SQL queries—especially on large, public, or third-party datasets (such as `deps_dev_v1` or `githubarchive`):

## 1. Never Assume Column Formatting or Data Formats
- Do not assume a column contains URL prefixes (e.g. `github.com/...`) or specific prefixes without verifying.
- Always check if the dataset separates platform identifiers into a distinct column (e.g. `Type = 'GITHUB'` and `Name = 'owner/repo'`).

## 2. Mandatory Pre-Execution Verification Protocol
Before writing or proposing any query scanning > 100 MB or performing an ETL insertion:
1. **Inspect Actual Rows (0-Cost):** Run `bq head -n 5 <dataset.table>` or a minimal metadata check to observe literal values, case sensitivity, and column formats.
2. **Test Join on a Single Small Partition:** Always test `JOIN` or `WHERE` filters against a single daily/monthly partition (with `LIMIT 5`) using Python/CLI to confirm that the query produces non-zero matched rows on actual data.
3. **Validate Partition Pruning:** Verify that timestamp/date partitions (like `SnapshotAt` or `_TABLE_SUFFIX`) are explicitly constrained to avoid scanning redundant historical table snapshots.
4. **Dry-Run Confirmation:** Always verify `total_bytes_processed` via a dry-run job before running any large operations.
