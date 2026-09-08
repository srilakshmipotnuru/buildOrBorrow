import re
import json
import logging
import urllib.request
import urllib.parse
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


def get_package_lookup_names(package_name: str, system: str) -> List[str]:
    """Generates package search aliases for PEP 503 normalization (PyPI) and common variants."""
    clean = package_name.strip().lower()
    names = [clean]
    target_sys = (system or "").strip().upper()
    if target_sys == "PYPI":
        names.append(clean.replace("_", "-"))
        names.append(clean.replace("-", "_"))
    return list(dict.fromkeys(names))


def query_package_resolution_rest_fallback(
    package_name: str,
    system: str
) -> Optional[Dict[str, Any]]:
    """
    Fallback: Queries the free deps.dev public REST API to resolve package metadata.
    Triggered only when BigQuery returns None (package outside 30-day SnapshotAt window).
    Handles packages abandoned years ago that are no longer crawled by deps.dev BigQuery snapshots.
    Two-step: (1) fetch package listing to find default version, (2) fetch version detail for relatedProjects.
    Cost: $0. Latency: ~300-500ms. Rate limit: none documented.
    """
    target_system = (system or "PYPI").strip().upper()
    encoded_name = urllib.parse.quote(package_name, safe="")
    headers = {"User-Agent": "BuildOrBorrow/1.0"}

    try:
        # Step 1: Get package listing to identify the default/latest version
        pkg_url = f"https://api.deps.dev/v3/systems/{target_system}/packages/{encoded_name}"
        req = urllib.request.Request(pkg_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            pkg_data = json.loads(resp.read().decode("utf-8"))

        versions = pkg_data.get("versions", [])
        if not versions:
            logger.warning(f"   [deps.dev REST] No versions listed for '{package_name}' ({target_system})")
            return None

        # Prefer the explicitly flagged default version; fall back to last in list
        default_ver = None
        for v in versions:
            if v.get("isDefault"):
                default_ver = v["versionKey"]["version"]
                break
        if not default_ver:
            default_ver = versions[-1]["versionKey"]["version"]

        # Step 2: Fetch full version detail for licenses + relatedProjects (GitHub URL)
        encoded_ver = urllib.parse.quote(default_ver, safe="")
        ver_url = f"https://api.deps.dev/v3/systems/{target_system}/packages/{encoded_name}/versions/{encoded_ver}"
        req2 = urllib.request.Request(ver_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=8) as resp2:
            ver_data = json.loads(resp2.read().decode("utf-8"))

        published_at = ver_data.get("publishedAt")
        raw_licenses = ver_data.get("licenses", [])
        licenses = [lic if isinstance(lic, str) else lic.get("license", "") for lic in raw_licenses]
        licenses = [l for l in licenses if l]

        # Extract GitHub source repo from relatedProjects (prefer SOURCE_REPO over ISSUE_TRACKER)
        github_url = None
        project_name = None
        related = ver_data.get("relatedProjects", [])
        for rel_type_pref in ("SOURCE_REPO", "ISSUE_TRACKER", ""):
            for proj in related:
                proj_id = proj.get("projectKey", {}).get("id", "")
                rel_type = proj.get("relationType", "")
                if proj_id.startswith("github.com/") and (rel_type == rel_type_pref or rel_type_pref == ""):
                    project_name = proj_id.replace("github.com/", "", 1)
                    github_url = f"https://github.com/{project_name}"
                    break
            if github_url:
                break

        logger.info(
            f"   [deps.dev REST Fallback] Resolved '{package_name}' v{default_ver} "
            f"({target_system}) | Repo: {github_url or 'None'} | Published: {(published_at or '')[:10]}"
        )
        return {
            "name": package_name,
            "system": target_system,
            "version": default_ver,
            "project_name": project_name,
            "licenses": licenses,
            "github_url": github_url,
            "published_at": published_at,
            "stargazers_count": 0,
            "forks_count": 0,
            "dependents_count": 0
        }

    except urllib.error.HTTPError as e:
        logger.warning(f"   [deps.dev REST Fallback] HTTP {e.code} for '{package_name}' ({target_system}): {e.reason}")
        return None
    except Exception as e:
        logger.warning(f"   [deps.dev REST Fallback] Failed for '{package_name}' ({target_system}): {type(e).__name__}: {e}")
        return None


def query_package_resolution(
    package_name: str,
    system: Optional[str] = None,
    client: Optional[bigquery.Client] = None
) -> Optional[Dict[str, Any]]:
    """
    Query deps.dev BigQuery dataset across ALL ecosystems (PYPI, NPM, CARGO, GO, MAVEN).
    Uses 2-CTE partition pruning with centralized settings for byte limit guardrails.
    Supports PEP 503 PyPI hyphen/underscore normalization and package-level project fallback.
    """
    package_name = package_name.strip().lower()
    target_system = (system or "PYPI").strip().upper()
    bq_client = client or get_bigquery_client()
    candidate_names = get_package_lookup_names(package_name, target_system)
    
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
          AND Name IN UNNEST(@package_names)
          AND VersionInfo.IsRelease = true
          AND SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {settings.DEPS_DEV_PARTITION_DAYS} DAY)
        ORDER BY 
          -- 1. Exact string match preferred
          CASE WHEN LOWER(Name) = LOWER(@primary_name) THEN 0 ELSE 1 END ASC,
          -- 2. Latest ordinal release
          VersionInfo.Ordinal DESC
        LIMIT 1
    ),
    target_project AS (
        SELECT 
            p2p.System, 
            p2p.Name, 
            p2p.ProjectName
        FROM `bigquery-public-data.deps_dev_v1.PackageVersionToProject` p2p
        WHERE p2p.System = @system
          AND p2p.Name IN UNNEST(@package_names)
          AND p2p.SnapshotAt >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {settings.DEPS_DEV_PARTITION_DAYS} DAY)
        ORDER BY 
          -- 1. Exact version match preferred
          CASE WHEN p2p.Version = (SELECT Version FROM target_package) THEN 0 ELSE 1 END ASC,
          -- 2. Prefer official GITHUB project type
          CASE WHEN UPPER(p2p.ProjectType) = 'GITHUB' THEN 0 ELSE 1 END ASC,
          -- 3. Avoid auxiliary build/release repos (e.g. 'numpy/numpy-release')
          CASE WHEN LOWER(p2p.ProjectName) LIKE '%-release' THEN 1 ELSE 0 END ASC,
          -- 4. Latest snapshot recency
          p2p.SnapshotAt DESC
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
            bigquery.ArrayQueryParameter("package_names", "STRING", candidate_names),
            bigquery.ScalarQueryParameter("primary_name", "STRING", package_name),
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
        logger.info(f"   [deps.dev] BigQuery miss for '{package_name}' ({target_system}) - package outside 30-day snapshot window. Trying REST API fallback...")
        return query_package_resolution_rest_fallback(package_name, target_system)
    except Exception as e:
        logger.error(f"   [deps.dev] Resolution query failed for '{package_name}': {e}", exc_info=True)
        logger.info(f"   [deps.dev] Trying REST API fallback after BigQuery exception for '{package_name}'...")
        return query_package_resolution_rest_fallback(package_name, target_system)


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
    output["recommended_pinned_version"] = None

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

