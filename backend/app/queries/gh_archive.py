import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from google.cloud import bigquery
from app.core.bigquery import execute_safe_query, get_bigquery_client
from app.core.config import settings

logger = logging.getLogger(__name__)

# In-Memory LRU Cache for GH Archive Queries (Key: repo_name_lookback_weeks -> List[Dict])
_GH_ARCHIVE_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def query_github_weekly_activity(
    client: Optional[bigquery.Client] = None, 
    repo_owner: str = "", 
    repo_name: str = "", 
    lookback_weeks: int = settings.DEFAULT_LOOKBACK_WEEKS
) -> List[Dict[str, Any]]:
    """
    Query GH Archive weekly activity using month-granularity partitions (`githubarchive.month.*`).
    Scanning 24 monthly tables instead of ~730 daily tables slashes per-table metadata & scan overhead by ~95%.
    Uses integer actor.id scanning and in-memory LRU caching to minimize byte consumption.
    """
    bq_client = client or get_bigquery_client()
    full_repo_name = f"{repo_owner}/{repo_name}".strip().lower()

    cache_key = f"{full_repo_name}_{lookback_weeks}"
    if cache_key in _GH_ARCHIVE_CACHE:
        logger.info(f"   [GH Archive Cache HIT] Returning cached activity for '{full_repo_name}' (0 MB scanned)")
        return _GH_ARCHIVE_CACHE[cache_key]
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(weeks=lookback_weeks)
    
    # Format YYYYMM for githubarchive.month.* table suffix filtering
    start_suffix = start_date.strftime('%Y%m')
    end_suffix = end_date.strftime('%Y%m')
    
    logger.info(f"   [GH Archive Query] Scanning monthly tables ({start_suffix} to {end_suffix}) for '{full_repo_name}'...")

    # Optimized SQL using githubarchive.month.* (24 table objects instead of 730):
    query = f"""
    SELECT
      TIMESTAMP_TRUNC(created_at, WEEK) AS week_start,
      COUNTIF(type = 'PushEvent') AS push_events,
      COUNTIF(type = 'PullRequestEvent') AS pr_events,
      COUNTIF(type = 'IssuesEvent') AS issue_events,
      COUNTIF(type = 'WatchEvent') AS star_events,
      COUNT(DISTINCT actor.id) AS active_contributors,
      COUNT(1) AS total_events,
      CAST(
        (COUNTIF(type = 'PushEvent') * 3.0) +
        (COUNTIF(type = 'PullRequestEvent') * 2.0) +
        (COUNTIF(type = 'IssuesEvent') * 1.0)
        AS FLOAT64
      ) AS weighted_activity
    FROM
      `githubarchive.month.*`
    WHERE
      _TABLE_SUFFIX BETWEEN '{start_suffix}' AND '{end_suffix}'
      AND repo.name = @repo_name
      AND type IN ('PushEvent', 'PullRequestEvent', 'IssuesEvent', 'WatchEvent')
    GROUP BY
      week_start
    ORDER BY
      week_start ASC
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("repo_name", "STRING", f"{repo_owner}/{repo_name}")
        ]
    )
    
    rows = execute_safe_query(bq_client, query, job_config=job_config, max_allowed_mb=settings.BQ_GH_ARCHIVE_MAX_ALLOWED_MB)
    
    results = [
        {
            "week_start": row.week_start.isoformat() if row.week_start else None,
            "push_events": row.push_events,
            "pr_events": row.pr_events,
            "issue_events": row.issue_events,
            "star_events": row.star_events,
            "active_contributors": row.active_contributors,
            "total_events": row.total_events,
            "weighted_activity": row.weighted_activity,
        }
        for row in rows
    ]

    _GH_ARCHIVE_CACHE[cache_key] = results
    return results


def query_arima_plus_forecast(
    client: Optional[bigquery.Client] = None,
    repo_owner: str = "",
    repo_name: str = "",
    lookback_weeks: int = settings.DEFAULT_LOOKBACK_WEEKS,
    forecast_weeks: int = settings.DEFAULT_FORECAST_WEEKS
) -> List[Dict[str, Any]]:
    """
    Executes BigQuery ML ARIMA_PLUS forecast on GH Archive weekly weighted activity.
    Step 1: Trains a per-repo ARIMA_PLUS model in user dataset (`buildorborrow.forecast_{owner}_{repo}`).
    Step 2: Calls ML.FORECAST on the trained model with 90% confidence bounds.
    Falls back gracefully if BigQuery ML dataset is unconfigured or permissions are restricted.
    """
    bq_client = client or get_bigquery_client()
    full_repo_name = f"{repo_owner}/{repo_name}"
    safe_name = f"{repo_owner}_{repo_name}".replace("-", "_").replace(".", "_").lower()
    
    project_id = settings.get_gcp_project() or "project-d8b4c833-4a30-41ee-89a"
    model_identifier = f"`{project_id}.buildorborrow.forecast_{safe_name}`"

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(weeks=lookback_weeks)
    
    start_suffix = start_date.strftime('%Y%m')
    end_suffix = end_date.strftime('%Y%m')
    
    # Step 1: SQL to extract weekly training dataset from monthly tables
    historical_weekly_sql = f"""
      SELECT
        TIMESTAMP_TRUNC(created_at, WEEK) AS week_start,
        CAST(
          (COUNTIF(type = 'PushEvent') * 3.0) +
          (COUNTIF(type = 'PullRequestEvent') * 2.0) +
          (COUNTIF(type = 'IssuesEvent') * 1.0)
          AS FLOAT64
        ) AS weighted_activity
      FROM
        `githubarchive.month.*`
      WHERE
        _TABLE_SUFFIX BETWEEN '{start_suffix}' AND '{end_suffix}'
        AND repo.name = @repo_name
        AND type IN ('PushEvent', 'PullRequestEvent', 'IssuesEvent', 'WatchEvent')
      GROUP BY
        week_start
    """

    create_model_sql = f"""
    CREATE OR REPLACE MODEL {model_identifier}
    OPTIONS(
      model_type = 'ARIMA_PLUS',
      time_series_timestamp_col = 'week_start',
      time_series_data_col = 'weighted_activity'
    ) AS
    {historical_weekly_sql}
    """

    forecast_sql = f"""
    SELECT
      forecast_timestamp AS week_start,
      CAST(GREATEST(0, ROUND(forecast_value)) AS INT64) AS projected_events,
      CAST(GREATEST(0, ROUND(prediction_interval_lower_bound)) AS INT64) AS confidence_lower,
      CAST(GREATEST(0, ROUND(prediction_interval_upper_bound)) AS INT64) AS confidence_upper
    FROM
      ML.FORECAST(
        MODEL {model_identifier},
        STRUCT({forecast_weeks} AS horizon, 0.90 AS confidence_level)
      )
    ORDER BY
      week_start ASC
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("repo_name", "STRING", full_repo_name)
        ]
    )

    try:
        logger.info(f"   [BQ ML ARIMA] Step 1: Training ARIMA_PLUS model {model_identifier}...")
        execute_safe_query(bq_client, create_model_sql, job_config=job_config, max_allowed_mb=settings.BQ_GH_ARCHIVE_MAX_ALLOWED_MB)
        
        logger.info(f"   [BQ ML ARIMA] Step 2: Executing ML.FORECAST horizon={forecast_weeks} wks...")
        rows = execute_safe_query(bq_client, forecast_sql, job_config=job_config, max_allowed_mb=settings.BQ_GH_ARCHIVE_MAX_ALLOWED_MB)
        
        return [
            {
                "week_start": row.week_start.isoformat() if row.week_start else None,
                "projected_events": row.projected_events,
                "confidence_lower": row.confidence_lower,
                "confidence_upper": row.confidence_upper,
            }
            for row in rows
        ]
    except Exception as e:
        logger.warning(f"BigQuery ML ARIMA forecast failed or unconfigured ({e}). Falling back to statistical series forecasting.")
        return []