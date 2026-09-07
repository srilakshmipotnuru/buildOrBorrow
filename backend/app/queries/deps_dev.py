import re
import logging
from typing import Optional, Dict, Any, List
from google.cloud import bigquery
from app.core.bigquery import get_bigquery_client, execute_safe_query
from app.core.config import settings

logger = logging.getLogger(__name__)


def is_version_vulnerable(version_str: Optional[str], range_str: Optional[str]) -> bool:
    """
    Checks if a resolved version string is affected by a deps.dev VulnerableVersionRange string.
    Example: version="3.11.1", range="< 2.0.0" -> False (patched/clean)
    Example: version="1.0.0", range="< 2.0.0" -> True (vulnerable)
    """
    if not version_str or not range_str:
        return False
    try:
        clean_v = version_str.strip().lstrip("v")
        v_parts = [int(p) for p in clean_v.split(".") if p.isdigit()]
        
        match = re.search(r"<\s*v?([0-9\.]+)", range_str)
        if match:
            target_v = [int(p) for p in match.group(1).split(".") if p.isdigit()]
            if v_parts and target_v:
                return v_parts < target_v
    except Exception:
        pass
    return False


def parse_semver(version_str: str) -> tuple[int, int, int]:
    """Parses a version string into (major, minor, patch) integers."""
    clean_v = version_str.strip().lstrip("v")
    parts = []
    for p in clean_v.split("."):
        digits = re.findall(r"\d+", p)
        if digits:
            parts.append(int(digits[0]))
        else:
            break
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def find_safe_pinned_version(
    current_version: str,
    version_history: List[Dict[str, Any]],
    affected_version_ranges: List[str]
) -> Optional[str]:
    """
    Finds the most recent vulnerability-free version within the same SemVer compatibility branch:
    1. If Major >= 1: matches same Major version (e.g. 2.x).
    2. If Major == 0: matches same Major AND Minor version (e.g. 0.4.x).
    3. Excludes current vulnerable version and newer releases.
    4. Must have 0 active vulnerabilities against affected_version_ranges.
    """
    if not current_version or not version_history:
        return None

    try:
        cur_major, cur_minor, cur_patch = parse_semver(current_version)
    except Exception:
        return None

    for item in version_history:
        cand_v_str = item.get("Version") or item.get("version")
        if not cand_v_str or cand_v_str.strip().lower() == current_version.strip().lower():
            continue

        try:
            cand_major, cand_minor, cand_patch = parse_semver(cand_v_str)
        except Exception:
            continue

        # SemVer compatibility rules:
        if cur_major >= 1:
            if cand_major != cur_major:
                continue
        else:
            # For 0.x, minor changes can introduce breaking changes
            if cand_major != cur_major or cand_minor != cur_minor:
                continue

        # Must be strictly earlier than current version
        if (cand_major, cand_minor, cand_patch) >= (cur_major, cur_minor, cur_patch):
            continue

        # Check against all affected vulnerability ranges
        is_vuln = any(is_version_vulnerable(cand_v_str, r) for r in affected_version_ranges)
        if not is_vuln:
            logger.info(f"   [Safe Version Pinning] Found safe version '{cand_v_str}' for current vulnerable v{current_version}")
            return cand_v_str

    return None


def query_package_version_history(
    package_name: str,
    system: Optional[str] = None,
    client: Optional[bigquery.Client] = None,
    limit: int = 15
) -> List[Dict[str, Any]]:
    """
    Queries up to `limit` recent released versions from deps.dev PackageVersions table
    published within the last 365 days (12-month recency horizon).
    """
    package_name = package_name.strip().lower()
    target_system = (system or "PYPI").strip().upper()
    bq_client = client or get_bigquery_client()

    sql = f"""
    SELECT 
        Version,
        CAST(SnapshotAt AS STRING) AS published_at,
        VersionInfo.Ordinal AS ordinal
    FROM `bigquery-public-data.deps_dev_v1.PackageVersions`
    WHERE System = @system 
      AND Name = @package_name
      AND VersionInfo.IsRelease = true
      AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
    ORDER BY VersionInfo.Ordinal DESC
    LIMIT {limit}
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("package_name", "STRING", package_name),
            bigquery.ScalarQueryParameter("system", "STRING", target_system)
        ]
    )
    try:
        rows = execute_safe_query(bq_client, sql, job_config=job_config, max_allowed_mb=settings.BQ_DEPS_DEV_MAX_ALLOWED_MB)
        return [{"Version": r.Version, "published_at": r.published_at, "ordinal": r.ordinal} for r in rows]
    except Exception as e:
        logger.warning(f"Failed to query version history for {package_name}: {e}")
        return []


def query_package_resolution(
    package_name: str,
    system: Optional[str] = None,
    client: Optional[bigquery.Client] = None
) -> Optional[Dict[str, Any]]:
    """
    Query deps.dev BigQuery dataset across ALL ecosystems (PYPI, NPM, CARGO, GO, MAVEN).
    Uses 2-CTE partition pruning with centralized settings for byte limit guardrails.
    """
    package_name = package_name.strip().lower()
    target_system = (system or "PYPI").strip().upper()
    bq_client = client or get_bigquery_client()
    
    sql = f"""
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
          AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {settings.DEPS_DEV_PARTITION_DAYS} DAY)
        ORDER BY VersionInfo.Ordinal DESC
        LIMIT 1
    ),
    target_project AS (
        SELECT 
            System, 
            Name, 
            ProjectName
        FROM `bigquery-public-data.deps_dev_v1.PackageVersionToProject`
        WHERE System = @system 
          AND Name = @package_name
          AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {settings.DEPS_DEV_PARTITION_DAYS} DAY)
        ORDER BY 
          -- 1. Prefer official GITHUB project type
          CASE WHEN UPPER(ProjectType) = 'GITHUB' THEN 0 ELSE 1 END ASC,
          -- 2. Avoid auxiliary build/release repos (e.g. 'numpy/numpy-release')
          CASE WHEN LOWER(ProjectName) LIKE '%-release' THEN 1 ELSE 0 END ASC,
          -- 3. Latest snapshot recency
          SnapshotAt DESC
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
    
    logger.info(f"   [deps.dev] Resolving package '{package_name}' ({target_system}) in BigQuery PackageVersions...")
    try:
        results = execute_safe_query(bq_client, sql, job_config=job_config, max_allowed_mb=settings.BQ_DEPS_DEV_MAX_ALLOWED_MB)
        
        if results:
            row = results[0]
            lic_str = ", ".join(list(row.Licenses)) if row.Licenses else "Unknown"
            logger.info(f"   [deps.dev] Resolution Success: {row.Name} v{row.Version} | License: [{lic_str}] | Repo: {row.ProjectName}")
            return {
                "name": row.Name,
                "system": row.System,
                "version": row.Version,
                "project_name": row.ProjectName,
                "licenses": list(row.Licenses) if row.Licenses else [],
                "github_url": f"https://github.com/{row.ProjectName}" if row.ProjectName else None,
                "published_at": row.published_at,
                "stargazers_count": 0,
                "forks_count": 0,
                "dependents_count": 0
            }
        logger.warning(f"   [deps.dev] No release resolution record found for '{package_name}' in {target_system}")
        return None
    except Exception as e:
        logger.error(f"   [deps.dev] Resolution query failed for '{package_name}': {e}", exc_info=True)
        return None


def query_security_and_dependencies(
    package_name: str,
    system: str = "PYPI",
    version: Optional[str] = None,
    client: Optional[bigquery.Client] = None
) -> Dict[str, Any]:
    """
    Query deps.dev for security vulnerability severity breakdown (CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN)
    and transitive dependency count bloat with centralized safety guardrails.
    """
    package_name = package_name.strip().lower()
    target_system = (system or "PYPI").strip().upper()
    bq_client = client or get_bigquery_client()
    
    logger.info(f"   [deps.dev Security] Scanning security advisories & transitive bloat for '{package_name}'...")
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

    output["affected_version_ranges"] = []
    output["active_cves_on_current_version"] = 0
    output["patched_historical_cves"] = 0
    output["is_current_version_vulnerable"] = False

    # Resolve version if missing to guarantee exact version scoping
    if not version:
        resolution = query_package_resolution(package_name=package_name, system=target_system, client=client)
        if resolution:
            version = resolution.get("version")

    # 1. Query Vulnerability Advisories & Affected Version Ranges using UNNEST(Packages)
    advisories_sql = """
    SELECT 
        UPPER(COALESCE(a.GitHubSeverity, a.Severity, 'UNKNOWN')) AS severity,
        a.SourceID,
        pkg.AffectedVersions AS affected_range
    FROM `bigquery-public-data.deps_dev_v1.Advisories` a,
    UNNEST(a.Packages) AS pkg
    WHERE pkg.System = @system 
      AND pkg.Name = @package_name
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("system", "STRING", target_system),
            bigquery.ScalarQueryParameter("package_name", "STRING", package_name)
        ]
    )

    try:
        rows = execute_safe_query(bq_client, advisories_sql, job_config=job_config, max_allowed_mb=settings.BQ_DEPS_DEV_MAX_ALLOWED_MB)
        seen_sources = set()
        ranges_set = set()

        for r in rows:
            src = r.SourceID
            sev = (r.severity or "").upper()
            aff_range = r.affected_range

            if aff_range:
                ranges_set.add(aff_range)

            if src not in seen_sources:
                seen_sources.add(src)
                output["total_vulnerabilities"] += 1
                if "CRITICAL" in sev:
                    output["critical_vulnerabilities"] += 1
                elif "HIGH" in sev:
                    output["high_vulnerabilities"] += 1
                elif "MEDIUM" in sev or "MODERATE" in sev:
                    output["medium_vulnerabilities"] += 1
                elif "LOW" in sev:
                    output["low_vulnerabilities"] += 1
                else:
                    output["unknown_vulnerabilities"] += 1

                # Scoped Version Check: Is current version in affected range?
                is_active = is_version_vulnerable(version, aff_range) if aff_range and version else False
                if is_active:
                    output["active_cves_on_current_version"] += 1
                else:
                    output["patched_historical_cves"] += 1

        output["is_current_version_vulnerable"] = output["active_cves_on_current_version"] > 0
        output["affected_version_ranges"] = list(ranges_set)[:5]

        # Safe Version Pinning Evaluation:
        # If current release has active CVEs, inspect release history for a clean version in the same major branch
        if output["is_current_version_vulnerable"] and version:
            history = query_package_version_history(package_name=package_name, system=target_system, client=client)
            safe_ver = find_safe_pinned_version(version, history, output["affected_version_ranges"])
            output["recommended_pinned_version"] = safe_ver
            if safe_ver:
                logger.info(
                    f"   [Safe Version Pinning] Recommended clean pinned version: v{safe_ver} "
                    f"(Current v{version} has {output['active_cves_on_current_version']} active CVEs)"
                )

        logger.info(
            f"   [deps.dev Security] Scoped Advisory Summary for '{package_name}' v{version or 'latest'}: "
            f"Total={output['total_vulnerabilities']} (Active on current v{version}: {output['active_cves_on_current_version']}, Patched Historical: {output['patched_historical_cves']}, Recommended Pin: {output['recommended_pinned_version']})"
        )
    except Exception as e:
        logger.error(f"Error querying advisories for {package_name}: {e}")

    # Resolve version if missing to guarantee exact partition pruning on Dependencies table
    if not version:
        resolution = query_package_resolution(package_name=package_name, system=target_system, client=client)
        if resolution:
            version = resolution.get("version")

    # 2. Query Transitive Dependency Count Bloat (Uses HyperLogLog++ APPROX_COUNT_DISTINCT for memory & speed optimization)
    if version:
        deps_sql = f"""
        SELECT 
            APPROX_COUNT_DISTINCT(Dependency.Name) AS total_dependencies
        FROM `bigquery-public-data.deps_dev_v1.Dependencies`
        WHERE System = @system 
          AND Name = @package_name
          AND Version = @version
          AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {settings.DEPS_DEV_PARTITION_DAYS} DAY)
        """
        deps_job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("system", "STRING", target_system),
                bigquery.ScalarQueryParameter("package_name", "STRING", package_name),
                bigquery.ScalarQueryParameter("version", "STRING", version)
            ]
        )
        try:
            rows = execute_safe_query(bq_client, deps_sql, job_config=deps_job_config, max_allowed_mb=settings.BQ_DEPS_DEV_MAX_ALLOWED_MB)
            if rows:
                output["transitive_dependencies"] = rows[0].total_dependencies or 0
                output["direct_dependencies"] = None
                logger.info(f"   [deps.dev Security] Dependency Bloat for '{package_name}' v{version}: {output['transitive_dependencies']} transitive dependencies")
        except Exception as e:
            logger.error(f"Error querying dependencies for {package_name}: {e}")

    return output

