import os
import sys
import requests
from google.cloud import bigquery
from dotenv import load_dotenv

# Load environment variables from local .env file
load_dotenv()

# Reconfigure stdout to UTF-8 to prevent Windows terminal encoding crashes
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Dynamic GCP project detection for collaborators
GCP_PROJECT = os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")


def get_bigquery_client():
    """
    Returns a BigQuery client for any collaborator.
    Uses the collaborator's active GCP_PROJECT env variable if set,
    otherwise defaults to their active 'gcloud config set project' setting.
    """
    if GCP_PROJECT:
        return bigquery.Client(project=GCP_PROJECT)
    return bigquery.Client()


def dry_run(package_name: str):
    """
    Step 1: Package Resolution via deps.dev BigQuery dataset.
    Resolves package name, system/ecosystem, latest version, and GitHub repo.
    """
    print(f" ---- Step 1: Package Resolution for: {package_name} ------")
    
    client = get_bigquery_client()

    sql = """
    SELECT 
        p.Name,
        p.System,
        p.Version,
        proj.ProjectName
    FROM `bigquery-public-data.deps_dev_v1.PackageVersions` p
    JOIN `bigquery-public-data.deps_dev_v1.PackageVersionToProject` proj
      ON p.System = proj.System 
     AND p.Name = proj.Name 
     AND p.Version = proj.Version
    WHERE p.System = 'PYPI'
      AND LOWER(p.Name) = LOWER(@package_name)
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("package_name", "STRING", package_name)
        ]
    )

    query_job = client.query(sql, job_config=job_config)
    results = list(query_job.result())

    mb_scanned = (query_job.total_bytes_processed or 0) / (1024 * 1024)
    print(f"[BigQuery] Step 1 Data Scanned: {mb_scanned:.2f} MB ({query_job.total_bytes_processed:,} bytes)")

    if results:
        row = results[0]
        print(f"[+] Package Name: {row.Name}")
        print(f"[+] Ecosystem:    {row.System}")
        print(f"[+] Version:      {row.Version}")
        print(f"[+] GitHub Repo:  {row.ProjectName}")
        
        # Trigger Step 2 & Step 3 with resolved GitHub repository name
        fetch_recent_issues(row.ProjectName)
        get_historical_trend(row.ProjectName)
    else:
        print("❌ No result found in deps.dev BigQuery dataset.")


def fetch_recent_issues(github_repo: str):
    """
    Step 2: Fetch recent open GitHub issue titles via GitHub REST API.
    Used by diagnosis_agent to detect unaddressed security bugs or syntax breakages.
    """
    print(f"\n --- Step 2: Fetching recent open issues from: {github_repo} ---")

    api_url = f"https://api.github.com/repos/{github_repo}/issues?state=open&per_page=10"
    response = requests.get(api_url)

    if response.status_code == 200:
        issues = response.json()
        titles = []
        for issue in issues:
            # Exclude Pull Requests from issue count
            if "pull_request" not in issue:
                titles.append(issue.get("title"))
        
        print(f"[+] Found {len(titles)} open issues:")
        for idx, t in enumerate(titles[:5], 1):
            print(f"   {idx}. {t}")
        return titles
    else:
        print(f"⚠️ Error fetching issues (HTTP {response.status_code})")
        return []


def get_historical_trend(github_repo: str):
    """
    Step 3: Query 90-day activity trend from GH Archive in BigQuery.
    Fetches PushEvent, IssuesEvent, and PullRequestEvent event counts.
    """
    print(f"\n ---- Step 3: Querying GH Archive from BigQuery for: {github_repo} ------")
    
    client = get_bigquery_client()
    
    sql = """
        SELECT 
            SAFE.PARSE_DATE('%Y%m%d', _TABLE_SUFFIX) AS event_date,
            type,
            COUNT(1) AS event_count
        FROM `githubarchive.day.20*`
        WHERE LENGTH(_TABLE_SUFFIX) = 8
          AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY))
          AND repo.name = @repo_name
          AND type IN ('PushEvent', 'IssuesEvent', 'PullRequestEvent')
        GROUP BY event_date, type
        ORDER BY event_date DESC
        LIMIT 10
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("repo_name", "STRING", github_repo)
        ]
    )
    
    query_job = client.query(sql, job_config=job_config)
    results = list(query_job.result())
    
    mb_scanned = (query_job.total_bytes_processed or 0) / (1024 * 1024)
    print(f"[BigQuery] Step 3 Data Scanned: {mb_scanned:.2f} MB ({query_job.total_bytes_processed:,} bytes)")
    
    if results:
        print(f"[+] Found {len(results)} activity events in GH Archive:")
        for row in results[:5]:
            print(f"   Date: {row.event_date} | Type: {row.type} | Count: {row.event_count}")
    else:
        print("   [!] No activity events found in the last 90 days.")


if __name__ == "__main__":
    dry_run("feedparser")


"""
==================================================================================
  PROJECT BUILDORBORROW - DRY RUN DOCUMENTATION & SYSTEM PIPELINE STEPS
==================================================================================

FILE PURPOSE:
  This script (`dryrun/dry_run.py`) is a clean, standalone prototype to test and 
  verify the core Google Cloud data fetching and API pipeline before building the 
  modular FastAPI backend routes and Google ADK agents.

COLLABORATOR NOTE ON GCP PROJECT IDS:
  - Do NOT hardcode specific GCP project IDs in code!
  - `get_bigquery_client()` dynamically detects each collaborator's active project 
    ID from their local `gcloud config set project <PROJECT_ID>` setting or from 
    the `GCP_PROJECT` / `GOOGLE_CLOUD_PROJECT` environment variable.
  - Before running, every collaborator should authenticate once via:
      1. `gcloud auth application-default login`
      2. `gcloud config set project <THEIR_PROJECT_ID>`

WHAT THIS SCRIPT EXECUTES:
  1. Connects to Google Cloud BigQuery using the collaborator's active project.
  2. Resolves PyPI package metadata & GitHub repo URL via `deps_dev_v1`.
  3. Fetches real recent open issue titles via GitHub REST API.
  4. Queries 90 days of historical activity from `githubarchive.day.20*`.
  5. Tracks exact BigQuery memory/bytes scanned to verify free-tier safety.

----------------------------------------------------------------------------------
FULL SYSTEM PIPELINE STEPS (For Collaborators & Team Review):
----------------------------------------------------------------------------------

[STEP 0] USER INPUT:
  Developer enters package name (e.g. 'feedparser') or task requirement into React UI.

[STEP 1] PACKAGE & REPO RESOLUTION (deps.dev BigQuery):
  Query `bigquery-public-data.deps_dev_v1` to map package name -> GitHub Repo URL & License.

[STEP 2] GITHUB ISSUE TEXT EXTRACTION (GitHub REST API):
  Fetch 10–20 recent issue titles. Crucial for detecting unaddressed bugs/vulnerabilities.

[STEP 3] HISTORICAL TREND AGGREGATION (GH Archive BigQuery):
  Pull 18–24 months of PushEvent, IssuesEvent, and PullRequestEvent grouped weekly.

[STEP 3B] TIME-SERIES FORECASTING (BigQuery ML ARIMA_PLUS):
  Run BigQuery ML `ARIMA_PLUS` on weekly push counts to project 90-day activity trend & bounds.

[STEP 4] AI DIAGNOSIS AGENT (Google ADK + Gemini):
  Evaluates 90-day forecast + issue text to classify:
  - "Declining BUT Stable" (mature / feature-complete package)
  - "Declining AND Struggling" (abandoned package with active unaddressed bugs)

[STEP 5] AI VERDICT AGENT (Google ADK + Gemini):
  Combines quantitative evidence, forecast, diagnosis, and user feature request to output:
  - BORROW  : Safe to use! Project is mature/stable.
  - MIGRATE : Risk! Project is unmaintained; switch to suggested alternative.
  - BUILD   : Feature is tiny; implement 20 lines of zero-dep code instead.

[STEP 6] BUILDER AGENT (Google ADK + Gemini):
  Executes ONLY on BUILD verdict to generate a small zero-dependency code replacement.

[STEP 7] REACT UI FRONTEND:
  Renders expandable stage pipeline rows + verdict card with copyable markdown and side-by-side comparison.
==================================================================================
"""