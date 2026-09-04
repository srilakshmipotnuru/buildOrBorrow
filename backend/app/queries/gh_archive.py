import logging
from typing import Optional, Dict, Any, List
from google.cloud import bigquery
from app.core.bigquery import execute_safe_query, get_bigquery_client
from app.core.config import settings

logger = logging.getLogger(__name__)


def query_github_weekly_activity(
    client: Optional[bigquery.Client] = None, 
    repo_owner: str = "", 
    repo_name: str = "", 
    lookback_weeks: int = settings.DEFAULT_LOOKBACK_WEEKS
) -> List[Dict[str, Any]]:
    """
    Query historical weekly GitHub activity from the custom pre-aggregated data warehouse
    (`build_or_borrow_dw.github_weekly_activity`).
    
    The custom table stores 104 continuous weeks of activity partitioned by `week_start`
    and clustered by `repo_name`.

    POST-MVP DELTA REFRESH REFERENCE:
    --------------------------------
    For ongoing weekly maintenance post-MVP, an automated Cloud Scheduler / Cron job can append
    new activity and prune records older than 104 weeks:
      1. INSERT INTO `build_or_borrow_dw.github_weekly_activity`
         SELECT ... FROM `githubarchive.day.*` WHERE _TABLE_SUFFIX = FORMAT_DATE('%Y%m%d', CURRENT_DATE() - 1)
      2. DELETE FROM `build_or_borrow_dw.github_weekly_activity`
         WHERE week_start < DATE_SUB(CURRENT_DATE(), INTERVAL 104 WEEK)
    """
    bq_client = client or get_bigquery_client()
    full_repo_name = f"{repo_owner}/{repo_name}".strip().lower()

    custom_table = f"`{settings.CUSTOM_BQ_PROJECT}.{settings.CUSTOM_BQ_DATASET}.{settings.CUSTOM_BQ_TABLE}`"
    logger.info(f"   [GH Warehouse Query] Reading 104-week activity for '{full_repo_name}' from {custom_table}...")

    # Direct indexed lookup on clustered custom warehouse:
    query = f"""
    SELECT
      week_start,
      push_events,
      create_events,
      pr_events,
      comment_events,
      issue_events,
      star_events,
      active_contributors,
      total_events,
      weighted_activity
    FROM
      {custom_table}
    WHERE
      repo_name = @repo_name
    ORDER BY
      week_start ASC
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("repo_name", "STRING", full_repo_name)
        ]
    )
    
    rows = execute_safe_query(bq_client, query, job_config=job_config, max_allowed_mb=settings.BQ_GH_ARCHIVE_MAX_ALLOWED_MB)
    
    results = [
        {
            "week_start": row.week_start.isoformat() if hasattr(row.week_start, "isoformat") else str(row.week_start),
            "push_events": row.push_events,
            "create_events": getattr(row, "create_events", 0),
            "pr_events": row.pr_events,
            "comment_events": getattr(row, "comment_events", 0),
            "issue_events": row.issue_events,
            "star_events": row.star_events,
            "active_contributors": row.active_contributors,
            "total_events": row.total_events,
            "weighted_activity": float(row.weighted_activity) if row.weighted_activity is not None else 0.0,
        }
        for row in rows
    ]

    return results


def query_arima_plus_forecast(
    client: Optional[bigquery.Client] = None,
    repo_owner: str = "",
    repo_name: str = "",
    lookback_weeks: int = settings.DEFAULT_LOOKBACK_WEEKS,
    forecast_weeks: int = settings.DEFAULT_FORECAST_WEEKS,
    weekly_history: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Executes real BigQuery ML ARIMA_PLUS forecast on weekly weighted activity.
    Step 1: Trains a per-repo ARIMA_PLUS model in dataset (`build_or_borrow_dw.forecast_{safe_owner}_{safe_repo}`).
            When `weekly_history` is supplied, it trains via an inline UNNEST parameter (0 bytes scanned).
    Step 2: Calls ML.FORECAST on the trained model with 90% statistical confidence bounds.
    Falls back gracefully if BigQuery ML dataset encounters permission or timeout constraints.
    """
    bq_client = client or get_bigquery_client()
    full_repo_name = f"{repo_owner}/{repo_name}".strip().lower()

    # Collision-safe identifier combining owner and repo name
    safe_owner = repo_owner.replace("-", "_").replace(".", "_").lower()
    safe_repo = repo_name.replace("-", "_").replace(".", "_").lower()
    model_name = f"forecast_{safe_owner}_{safe_repo}"
    model_identifier = f"`{settings.CUSTOM_BQ_PROJECT}.{settings.CUSTOM_BQ_DATASET}.{model_name}`"

    # Step 1: SQL to train ARIMA_PLUS model
    if weekly_history and len(weekly_history) >= 10:
        # Zero-scan inline training using UNNEST array:
        create_model_sql = f"""
        CREATE OR REPLACE MODEL {model_identifier}
        OPTIONS(
          model_type = 'ARIMA_PLUS',
          time_series_timestamp_col = 'week_start',
          time_series_data_col = 'weighted_activity',
          horizon = {forecast_weeks}
        ) AS
        SELECT
          PARSE_TIMESTAMP('%Y-%m-%d', SUBSTR(week_start, 1, 10)) AS week_start,
          weighted_activity
        FROM
          UNNEST(@history)
        """
        struct_list = [
            bigquery.StructQueryParameter(
                "item",
                bigquery.ScalarQueryParameter("week_start", "STRING", str(r.get("week_start", ""))[:10]),
                bigquery.ScalarQueryParameter("weighted_activity", "FLOAT64", float(r.get("weighted_activity", 0.0)))
            )
            for r in weekly_history
            if r.get("week_start")
        ]
        train_job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("history", "RECORD", struct_list)
            ]
        )
    else:
        # Fallback to direct warehouse table query
        custom_table = f"`{settings.CUSTOM_BQ_PROJECT}.{settings.CUSTOM_BQ_DATASET}.{settings.CUSTOM_BQ_TABLE}`"
        create_model_sql = f"""
        CREATE OR REPLACE MODEL {model_identifier}
        OPTIONS(
          model_type = 'ARIMA_PLUS',
          time_series_timestamp_col = 'week_start',
          time_series_data_col = 'weighted_activity',
          horizon = {forecast_weeks}
        ) AS
        SELECT
          TIMESTAMP(week_start) AS week_start,
          weighted_activity
        FROM
          {custom_table}
        WHERE
          repo_name = @repo_name
        ORDER BY
          week_start ASC
        """
        train_job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("repo_name", "STRING", full_repo_name)
            ]
        )

    # Step 2: SQL to generate 13-week forecast with 90% confidence intervals
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

    try:
        logger.info(f"   [BQ ML ARIMA] Step 1: Training ARIMA_PLUS model {model_identifier}...")
        execute_safe_query(bq_client, create_model_sql, job_config=train_job_config, max_allowed_mb=settings.BQ_GH_ARCHIVE_MAX_ALLOWED_MB)
        
        logger.info(f"   [BQ ML ARIMA] Step 2: Executing ML.FORECAST horizon={forecast_weeks} wks...")
        rows = execute_safe_query(bq_client, forecast_sql, max_allowed_mb=settings.BQ_GH_ARCHIVE_MAX_ALLOWED_MB)
        
        return [
            {
                "week_start": row.week_start.isoformat() if hasattr(row.week_start, "isoformat") else str(row.week_start),
                "projected_events": row.projected_events,
                "confidence_lower": row.confidence_lower,
                "confidence_upper": row.confidence_upper,
            }
            for row in rows
        ]
    except Exception as e:
        logger.warning(f"BigQuery ML ARIMA forecast failed ({e}). Falling back to statistical series forecasting.")
        return []