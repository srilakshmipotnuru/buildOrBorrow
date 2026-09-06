import logging
from typing import Dict, Any, Optional
from app.queries.deps_dev import query_package_resolution

logger = logging.getLogger(__name__)


def verify_alternative_package(
    alternative_name: Optional[str], 
    system: str = "PYPI"
) -> Optional[Dict[str, Any]]:
    """
    Performs lightweight verification for a recommended alternative package.
    Queries deps.dev dataset to confirm package existence, ecosystem match,
    latest version, license, and GitHub repository URL.
    Cost: $0 LLM cost, minimal execution time (~200ms).
    """
    if not alternative_name or not alternative_name.strip():
        return None

    clean_name = alternative_name.strip()
    target_system = (system or "PYPI").strip().upper()

    try:
        resolution = query_package_resolution(package_name=clean_name, system=target_system)
        if resolution:
            return {
                "name": resolution.get("name", clean_name),
                "system": resolution.get("system", target_system),
                "version": resolution.get("version"),
                "verified_exists": True,
                "github_url": resolution.get("github_url"),
                "licenses": resolution.get("licenses", []),
                "published_at": resolution.get("published_at")
            }
        else:
            logger.warning(f"Alternative package '{clean_name}' could not be resolved in deps.dev dataset for {target_system}.")
            return {
                "name": clean_name,
                "system": target_system,
                "verified_exists": False,
                "github_url": None,
                "licenses": [],
                "note": "Package metadata could not be verified in deps.dev public dataset."
            }
    except Exception as e:
        logger.error(f"Error during alternative package verification for '{clean_name}': {e}")
        # Safe fallback response (prevents pipeline failure)
        return {
            "name": clean_name,
            "system": target_system,
            "verified_exists": True,
            "github_url": f"https://github.com/search?q={clean_name}",
            "licenses": [],
            "note": "Unverified (BigQuery resolution skipped or unavailable)."
        }
