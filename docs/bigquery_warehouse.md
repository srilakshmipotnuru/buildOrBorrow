# BuildOrBorrow: BigQuery Data Warehouse & ML Architecture

This document provides the complete technical reference for the **BuildOrBorrow** BigQuery custom data warehouse, aggregation DDL scripts, BigQuery ML forecasting models, and collaborator IAM configuration.

---

## 1. 🗄️ Dataset Architecture & Schema Overview

* **GCP Project ID**: `project-bbc67fb6-4e57-4565-bb5`
* **Dataset Name**: `build_or_borrow_dw`
* **Table Name**: `github_weekly_activity`
* **Data Volume**: ~17.3 Million pre-aggregated rows (August 2024 – August 2026, 104 continuous weeks)
* **Partitioning Strategy**: `PARTITION BY week_start` (Weekly DATE partitioning)
* **Clustering Strategy**: `CLUSTER BY repo_name` (Indexed per-repository lookup)

---

## 2. ⚡ Warehouse Creation DDL Query

The following BigQuery SQL query extracts raw developer activity events from `githubarchive.month.*`, applies composite maintenance weighting, filters out automated bot activity, and materializes the partitioned warehouse table:

```sql
CREATE OR REPLACE TABLE `project-bbc67fb6-4e57-4565-bb5.build_or_borrow_dw.github_weekly_activity`
PARTITION BY week_start
CLUSTER BY repo_name
OPTIONS(
  description = "Pre-aggregated 104-week GitHub maintenance timeline with weighted activity & bot filtering."
) AS
SELECT
  -- 1. Weekly Partitioning & Repo Clustering Key
  DATE(TIMESTAMP_TRUNC(created_at, WEEK)) AS week_start,
  LOWER(repo.name) AS repo_name,

  -- 2. Granular Event Breakdown
  COUNTIF(type = 'PushEvent') AS push_events,
  COUNTIF(type = 'CreateEvent') AS create_events,
  COUNTIF(type = 'PullRequestEvent') AS pr_events,
  COUNTIF(type IN ('IssueCommentEvent', 'PullRequestReviewCommentEvent')) AS comment_events,
  COUNTIF(type = 'IssuesEvent') AS issue_events,
  COUNTIF(type = 'WatchEvent') AS star_events,

  -- 3. Contributor & Velocity Aggregations
  COUNT(DISTINCT actor.id) AS active_contributors,
  COUNT(1) AS total_events,

  -- 4. Composite Weighted Maintenance Velocity Score
  CAST(
    (COUNTIF(type = 'PushEvent') * 3.0) +
    (COUNTIF(type = 'CreateEvent') * 3.0) +
    (COUNTIF(type = 'PullRequestEvent') * 2.0) +
    (COUNTIF(type = 'IssuesEvent') * 1.0) +
    (COUNTIF(type IN ('IssueCommentEvent', 'PullRequestReviewCommentEvent')) * 1.0)
    AS FLOAT64
  ) AS weighted_activity

FROM `githubarchive.month.*`
WHERE 
  -- 104-Week Horizon Filter (2 Full Years)
  _TABLE_SUFFIX BETWEEN '202408' AND '202608'
  AND type IN (
    'PushEvent', 'CreateEvent', 'PullRequestEvent', 
    'IssuesEvent', 'IssueCommentEvent', 'PullRequestReviewCommentEvent', 'WatchEvent'
  )
  -- Filter out automated bots (Dependabot, Renovate, GitHub Actions bots)
  AND LOWER(actor.login) NOT LIKE '%[bot]'
  AND repo.name IS NOT NULL

GROUP BY
  week_start,
  repo_name;
```

---

## 3. 🧠 BigQuery ML `ARIMA_PLUS` Forecasting Engine

BigQuery ML time-series models (`model_type = 'ARIMA_PLUS'`) are trained on the 104-week `weighted_activity` timeline to project developer activity 90 days into the future.

### **Zero-Scan Inline Parameter Model Training**
To eliminate the 7.8 GB multi-iteration table scan cost of `CREATE MODEL`, the backend passes the 104 historical weeks directly as an inline parameter array (`UNNEST(@history)`), resulting in **0 bytes scanned** during model fitting:

```sql
CREATE OR REPLACE MODEL `project-bbc67fb6-4e57-4565-bb5.build_or_borrow_dw.forecast_{safe_owner}_{safe_repo}`
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'week_start',
  time_series_data_col = 'weighted_activity',
  horizon = 13
) AS
SELECT
  PARSE_TIMESTAMP('%Y-%m-%d', SUBSTR(week_start, 1, 10)) AS week_start,
  weighted_activity
FROM
  UNNEST(@history);
```

### **Active Generated Models**
The following 8 models have been trained and are active inside `build_or_borrow_dw`:
1. `forecast_psf_requests`
2. `forecast_axios_axios`
3. `forecast_spring_projects_spring_boot`
4. `forecast_openai_whisper`
5. `forecast_matplotlib_matplotlib`
6. `forecast_manimcommunity_manim`
7. `forecast_allegro_bigcache`
8. `forecast_azure_azure_sdk_for_go`

---

## 4. 👥 Collaborator IAM & Console Access Guide

When sharing dataset access with collaborators (without giving full GCP project-level admin roles), follow this guide for console UI setup:

### **Required IAM Dataset Roles**
Grant the collaborator's Google email address the following dataset-level roles under **BigQuery $\rightarrow$ `build_or_borrow_dw` $\rightarrow$ Sharing $\rightarrow$ Permissions**:
* **`BigQuery Data Viewer`** (`roles/bigquery.dataViewer`): View table schemas and preview dataset rows.
* **`BigQuery Data Editor`** (`roles/bigquery.dataEditor`): View, inspect, and manage BigQuery ML model objects (`ARIMA_PLUS`).

### **Console UI Setup Steps for Collaborator**
1. Open **[console.cloud.google.com/bigquery](https://console.cloud.google.com/bigquery)**.
2. In the left **Explorer** sidebar, click **`+ ADD`** $\rightarrow$ **Star a project by name**.
3. Type the Project ID: `project-bbc67fb6-4e57-4565-bb5` and click **Star**.
4. Expand `project-bbc67fb6-4e57-4565-bb5` $\rightarrow$ `build_or_borrow_dw` to view tables and models.
5. If models do not immediately appear, click **`⋮` (three dots)** next to `build_or_borrow_dw` $\rightarrow$ **Refresh dataset**.

### **Query Execution (Billing Project)**
Collaborators execute queries referencing the full 3-part dataset path:

```sql
SELECT * 
FROM `project-bbc67fb6-4e57-4565-bb5.build_or_borrow_dw.github_weekly_activity`
WHERE repo_name = 'psf/requests'
ORDER BY week_start DESC
LIMIT 50;
```
