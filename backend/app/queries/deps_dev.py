import logging
from typing import Optional, Dict, Any
from google.cloud import bigquery
from app.core.bigquery import get_bigquery_client, execute_safe_query

logger = logging.getLogger(__name__)


def query_package_resolution(
    package_name: str,
    system: Optional[str] = None,
    client: Optional[bigquery.Client] = None
) -> Optional[Dict[str, Any]]:
    """
    Query deps.dev BigQuery dataset across ALL ecosystems (PYPI, NPM, CARGO, GO, MAVEN).
    Uses 2-CTE 30-day partition pruning with 2.5 GB safety limit guardrail.
    """
    package_name = package_name.strip().lower()
    target_system = (system or "PYPI").strip().upper()
    bq_client = client or get_bigquery_client()
    
    sql = """
    WITH target_package AS (
        SELECT 
            Name, 
            System, 
            Version, 
            Licenses, 
            SnapshotAt
        FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
        WHERE System = @system 
          AND Name = @package_name
          AND VersionInfo.IsRelease = true
          AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        ORDER BY VersionInfo.Ordinal DESC
        LIMIT 1
    ),
    target_project AS (
        SELECT 
            System, 
            Name, 
            Version, 
            ProjectName
        FROM `bigquery-public-data.deps_dev_v1.PackageVersionToProject`
        WHERE System = @system 
          AND Name = @package_name
          AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        LIMIT 1
    )
    SELECT 
        tp.Name,
        tp.System,
        tp.Version,
        tp.Licenses,
        CAST(tp.SnapshotAt AS STRING) AS published_at,
        proj.ProjectName
    FROM target_package tp
    LEFT JOIN target_project proj
      ON tp.System = proj.System 
     AND tp.Name = proj.Name
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("package_name", "STRING", package_name),
            bigquery.ScalarQueryParameter("system", "STRING", target_system)
        ]
    )
    
    try:
        results = execute_safe_query(bq_client, sql, job_config=job_config, max_allowed_mb=2500.0)
        
        if results:
            row = results[0]
            return {
                "name": row.Name,
                "system": row.System,
                "version": row.Version,
                "project_name": row.ProjectName,
                "licenses": list(row.Licenses) if row.Licenses else [],
                "github_url": f"https://github.com/{row.ProjectName}" if row.ProjectName else None,
                "published_at": row.published_at
            }
        return None
    except Exception as e:
        logger.error(f"Error querying deps.dev resolution for {package_name}: {e}", exc_info=True)
        return None


def query_security_and_dependencies(
    package_name: str,
    system: str = "PYPI",
    version: Optional[str] = None,
    client: Optional[bigquery.Client] = None
) -> Dict[str, Any]:
    """
    Query deps.dev for security vulnerability severity breakdown (CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN)
    and transitive dependency count bloat with Dry Run safety guardrail.
    """
    package_name = package_name.strip().lower()
    target_system = (system or "PYPI").strip().upper()
    bq_client = client or get_bigquery_client()
    
    output = {
        "critical_vulnerabilities": 0,
        "high_vulnerabilities": 0,
        "medium_vulnerabilities": 0,
        "low_vulnerabilities": 0,
        "unknown_vulnerabilities": 0,
        "total_vulnerabilities": 0,
        "direct_dependencies": None,
        "transitive_dependencies": 0,
        "license": "Unknown"
    }

    # 1. Query Vulnerability Advisories by Severity using UNNEST(Packages)
    advisories_sql = """
    SELECT 
        UPPER(COALESCE(a.GitHubSeverity, a.Severity, 'UNKNOWN')) AS severity,
        COUNT(DISTINCT a.SourceID) AS count
    FROM `bigquery-public-data.deps_dev_v1.Advisories` a,
    UNNEST(a.Packages) AS pkg
    WHERE pkg.System = @system 
      AND pkg.Name = @package_name
    GROUP BY severity
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("system", "STRING", target_system),
            bigquery.ScalarQueryParameter("package_name", "STRING", package_name)
        ]
    )

    try:
        rows = execute_safe_query(bq_client, advisories_sql, job_config=job_config, max_allowed_mb=2500.0)
        for r in rows:
            sev = (r.severity or "").upper()
            cnt = r.count or 0
            output["total_vulnerabilities"] += cnt
            if "CRITICAL" in sev:
                output["critical_vulnerabilities"] += cnt
            elif "HIGH" in sev:
                output["high_vulnerabilities"] += cnt
            elif "MEDIUM" in sev or "MODERATE" in sev:
                output["medium_vulnerabilities"] += cnt
            elif "LOW" in sev:
                output["low_vulnerabilities"] += cnt
            else:
                output["unknown_vulnerabilities"] += cnt
    except Exception as e:
        logger.error(f"Error querying advisories for {package_name}: {e}")

    # Resolve version if missing to guarantee exact partition pruning on Dependencies table
    if not version:
        resolution = query_package_resolution(package_name=package_name, system=target_system, client=client)
        if resolution:
            version = resolution.get("version")

    # 2. Query Transitive Dependency Count Bloat
    if version:
        deps_sql = """
        SELECT 
            COUNT(DISTINCT Dependency.Name) AS total_dependencies
        FROM `bigquery-public-data.deps_dev_v1.Dependencies`
        WHERE System = @system 
          AND Name = @package_name
          AND Version = @version
          AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        """
        deps_job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("system", "STRING", target_system),
                bigquery.ScalarQueryParameter("package_name", "STRING", package_name),
                bigquery.ScalarQueryParameter("version", "STRING", version)
            ]
        )
        try:
            rows = execute_safe_query(bq_client, deps_sql, job_config=deps_job_config, max_allowed_mb=2500.0)
            if rows:
                output["transitive_dependencies"] = rows[0].total_dependencies or 0
                output["direct_dependencies"] = None
        except Exception as e:
            logger.error(f"Error querying dependencies for {package_name}: {e}")

    return output
