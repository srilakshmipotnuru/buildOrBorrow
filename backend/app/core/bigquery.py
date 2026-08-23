import logging
from typing import Optional
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
