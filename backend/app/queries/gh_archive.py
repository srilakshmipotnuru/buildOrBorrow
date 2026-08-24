# app/queries/gh_archive.py
from datetime import datetime, timedelta, timezone
from google.cloud import bigquery
from app.core.bigquery import execute_safe_query

def query_github_weekly_activity(
    client: bigquery.Client, 
    repo_owner: str, 
    repo_name: str, 
    lookback_weeks: int = 4
) -> list[dict]:
    full_repo_name = f"{repo_owner}/{repo_name}"
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(weeks=lookback_weeks)
    
    # Suffix for '20*' tables: YYYYMMDD without the leading '20'
    # e.g., 20260824 -> suffix is '260824'
    start_suffix = start_date.strftime('%Y%m%d')[2:]
    end_suffix = end_date.strftime('%Y%m%d')[2:]
    
    query = f"""
    SELECT
      TIMESTAMP_TRUNC(created_at, WEEK) AS week_start,
      COUNTIF(type = 'PushEvent') AS push_events,
      COUNTIF(type = 'PullRequestEvent') AS pr_events,
      COUNTIF(type = 'IssuesEvent') AS issue_events,
      COUNTIF(type = 'WatchEvent') AS star_events,
      COUNT(1) AS total_events
    FROM
      `githubarchive.day.20*`
    WHERE
      _TABLE_SUFFIX BETWEEN '{start_suffix}' AND '{end_suffix}'
      AND repo.name = @repo_name
    GROUP BY
      week_start
    ORDER BY
      week_start ASC
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("repo_name", "STRING", full_repo_name)
        ]
    )
    
    rows = execute_safe_query(client, query, job_config=job_config)
    
    return [
        {
            "week_start": row.week_start.isoformat() if row.week_start else None,
            "push_events": row.push_events,
            "pr_events": row.pr_events,
            "issue_events": row.issue_events,
            "star_events": row.star_events,
            "total_events": row.total_events,
        }
        for row in rows
    ]