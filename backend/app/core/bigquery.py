import logging
from typing import Optional, List, Any
from google.cloud import bigquery
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_bigquery_client() -> bigquery.Client:
    """
    FastAPI dependency that returns an authenticated BigQuery client.
    Parameterless signature prevents FastAPI from injecting project_id into Swagger.
    """
    target_project = settings.get_gcp_project() if hasattr(settings, "get_gcp_project") else None
    
    if target_project:
        logger.debug(f"Initializing BigQuery client for GCP Project: {target_project}")
        return bigquery.Client(project=target_project)
    
    logger.debug("Initializing BigQuery client with default active gcloud config.")
    return bigquery.Client()


def execute_safe_query(
    client: bigquery.Client,
    sql: str,
    job_config: Optional[bigquery.QueryJobConfig] = None,
    max_allowed_mb: Optional[float] = None
) -> List[Any]:
    """
    Executes a BigQuery SQL query safely.
    - If settings.ENABLE_BIGQUERY_BYTE_LIMITS is True (Testing mode): Enforces server-side maximum_bytes_billed limit.
    - If settings.ENABLE_BIGQUERY_BYTE_LIMITS is False (Production mode): Sets maximum_bytes_billed to None (unrestricted).
    """
    real_config = job_config or bigquery.QueryJobConfig()
    target_max_mb = max_allowed_mb if max_allowed_mb is not None else settings.BQ_DEFAULT_MAX_ALLOWED_MB

    if settings.ENABLE_BIGQUERY_BYTE_LIMITS:
        # Internal Testing Mode: Apply server-side maximum_bytes_billed limit
        max_bytes = int(target_max_mb * 1024 * 1024)
        if real_config.maximum_bytes_billed is None:
            real_config.maximum_bytes_billed = max_bytes
        logger.debug(f"BigQuery Byte Limit ENABLED: Enforcing {target_max_mb:.2f} MB cap.")
    else:
        # Production Deployment Mode: Disable byte limit restrictions
        real_config.maximum_bytes_billed = None
        logger.debug("BigQuery Byte Limit DISABLED: Running query without maximum_bytes_billed restriction.")

    try:
        query_job = client.query(sql, job_config=real_config)
        results = list(query_job.result())
        
        actual_mb = (query_job.total_bytes_processed or 0) / (1024 * 1024)
        if settings.ENABLE_BIGQUERY_BYTE_LIMITS:
            logger.info(f"BigQuery Query Executed. Scanned: {actual_mb:.2f} MB (Cap: {target_max_mb:.2f} MB)")
        else:
            logger.info(f"BigQuery Query Executed. Scanned: {actual_mb:.2f} MB (Cap: Disabled)")
        return results
    except Exception as e:
        logger.error(f"BigQuery Query Execution Failed / Aborted: {e}")
        raise