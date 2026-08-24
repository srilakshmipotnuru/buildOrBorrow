import logging
from typing import Optional, List, Any
from google.cloud import bigquery
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_bigquery_client(project_id: Optional[str] = None) -> bigquery.Client:
    """
    Factory function returning a Google Cloud BigQuery client instance.
    
    Resolves project ID in priority order:
    1. Explicitly passed project_id parameter
    2. Resolved project ID from settings (GCP_PROJECT / GOOGLE_CLOUD_PROJECT)
    3. Default active gcloud SDK configuration
    """
    target_project = project_id or settings.get_gcp_project()
    
    if target_project:
        logger.info(f"Initializing BigQuery client for GCP Project: {target_project}")
        return bigquery.Client(project=target_project)
    
    logger.info("Initializing BigQuery client with default active gcloud config.")
    return bigquery.Client()


def execute_safe_query(
    client: bigquery.Client,
    sql: str,
    job_config: Optional[bigquery.QueryJobConfig] = None,
    max_allowed_mb: float = 50.0
) -> List[Any]:
    """
    Executes a BigQuery SQL query with BigQuery's server-side maximum_bytes_billed hard limit.
    If a query attempts to scan more than max_allowed_mb (default 50 MB), BigQuery server
    automatically aborts the query before scanning or spending quota.
    """
    real_config = job_config or bigquery.QueryJobConfig()
    
    # Convert max_allowed_mb to bytes for BigQuery's server-side hard limit
    max_bytes = int(max_allowed_mb * 1024 * 1024)
    if real_config.maximum_bytes_billed is None:
        real_config.maximum_bytes_billed = max_bytes

    try:
        query_job = client.query(sql, job_config=real_config)
        results = list(query_job.result())
        
        actual_mb = (query_job.total_bytes_processed or 0) / (1024 * 1024)
        logger.info(f"BigQuery Query Executed Safely. Scanned: {actual_mb:.2f} MB (Limit: {max_allowed_mb:.2f} MB)")
        return results
    except Exception as e:
        logger.error(f"BigQuery Query Execution Failed / Aborted: {e}")
        raise
