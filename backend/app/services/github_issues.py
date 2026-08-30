import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)


def calculate_relative_age(created_at_str: str) -> str:
    """Calculates human-readable relative age (e.g. '12 days ago', '2 years ago')."""
    try:
        # ISO 8601 parsing (e.g. "2024-01-15T12:34:56Z")
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - created_at
        
        days = diff.days
        if days == 0:
            hours = diff.seconds // 3600
            return f"{hours} hours ago" if hours > 0 else "just now"
        elif days == 1:
            return "1 day ago"
        elif days < 30:
            return f"{days} days ago"
        elif days < 365:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
    except Exception:
        return "recently"


def fetch_recent_github_issues(
    owner: str, 
    repo: str, 
    max_issues: int = settings.GITHUB_ISSUES_MAX_COUNT
) -> List[Dict[str, Any]]:
    """
    Fetches recent open GitHub issue titles and creation timestamps via GitHub Search API.
    Primary: GitHub Search API with 'type:issue' direct filtering.
    Fallback: Standard REST repo issues endpoint with in-memory 'pull_request' key filtering.
    """
    owner = owner.strip()
    repo = repo.strip()
    full_repo = f"{owner}/{repo}"

    headers = {
        "User-Agent": "BuildOrBorrow/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    
    if hasattr(settings, "GITHUB_TOKEN") and settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    # Attempt 1: GitHub Search API (Directly filters out PRs with type:issue)
    search_url = (
        f"https://api.github.com/search/issues"
        f"?q=repo:{full_repo}+type:issue+state:open"
        f"&sort=created&order=desc&per_page={max_issues}"
    )

    try:
        response = requests.get(search_url, headers=headers, timeout=settings.GITHUB_API_TIMEOUT_SECONDS)
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            results = []
            for item in items[:max_issues]:
                created_at = item.get("created_at", "")
                age_str = calculate_relative_age(created_at) if created_at else "unknown"
                results.append({
                    "title": item.get("title", ""),
                    "created_at": created_at,
                    "age": age_str,
                    "formatted_text": f"{item.get('title', '')} (opened {age_str})"
                })
            logger.info(f"   [GitHub Issues API] Successfully fetched {len(results)} open issues for '{full_repo}' via Search API:")
            for issue in results[:5]:  # Log top 5 issue titles for details
                logger.info(f"      • {issue['title']} (opened {issue['age']})")
            if len(results) > 5:
                logger.info(f"      • ... and {len(results) - 5} more issues.")
            return results
        else:
            logger.warning(f"GitHub Search API returned HTTP {response.status_code} for {full_repo}, falling back to REST endpoint.")
    except Exception as e:
        logger.warning(f"GitHub Search API request failed for {full_repo}: {e}. Trying REST fallback.")

    # Attempt 2: REST Repo Issues Endpoint Fallback
    rest_url = f"https://api.github.com/repos/{full_repo}/issues?state=open&per_page={settings.GITHUB_ISSUES_REST_PER_PAGE}"
    try:
        response = requests.get(rest_url, headers=headers, timeout=settings.GITHUB_API_TIMEOUT_SECONDS)
        if response.status_code == 200:
            items = response.json()
            results = []
            for item in items:
                # Exclude Pull Requests (PRs contain 'pull_request' key)
                if isinstance(item, dict) and "pull_request" not in item:
                    created_at = item.get("created_at", "")
                    age_str = calculate_relative_age(created_at) if created_at else "unknown"
                    results.append({
                        "title": item.get("title", ""),
                        "created_at": created_at,
                        "age": age_str,
                        "formatted_text": f"{item.get('title', '')} (opened {age_str})"
                    })
                    if len(results) >= max_issues:
                        break
            logger.info(f"   [GitHub Issues REST] Successfully fetched {len(results)} open issues for '{full_repo}' via REST fallback:")
            for issue in results[:5]:
                logger.info(f"      • {issue['title']} (opened {issue['age']})")
            if len(results) > 5:
                logger.info(f"      • ... and {len(results) - 5} more issues.")
            return results
        else:
            logger.error(f"GitHub REST Repo issues endpoint returned HTTP {response.status_code} for {full_repo}")
            return []
    except Exception as e:
        logger.error(f"GitHub REST Repo issues endpoint failed for {full_repo}: {e}")
        return []


def fetch_github_readme_summary(owner: str, repo: str) -> Dict[str, Any]:
    """
    Fetches the repository README.md header via GitHub REST API.
    Scans for deprecation/renaming keywords: 'deprecated', 'renamed to', 'superseded by', 'no longer maintained'.
    """
    owner = owner.strip()
    repo = repo.strip()
    full_repo = f"{owner}/{repo}"

    headers = {
        "User-Agent": "BuildOrBorrow/1.0",
        "Accept": "application/vnd.github.v3.raw",
    }
    if hasattr(settings, "GITHUB_TOKEN") and settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    url = f"https://api.github.com/repos/{full_repo}/readme"
    try:
        response = requests.get(url, headers=headers, timeout=settings.GITHUB_API_TIMEOUT_SECONDS)
        if response.status_code == 200:
            readme_text = response.text[:2500]
            lower_text = readme_text.lower()

            deprecation_keywords = [
                "deprecated", "renamed to", "superseded by", "moved to",
                "no longer maintained", "archived", "unmaintained"
            ]
            is_deprecated_flag = any(kw in lower_text for kw in deprecation_keywords)
            
            logger.info(f"   [GitHub README] Retrieved README header for '{full_repo}' (Deprecation Warning Signal: {is_deprecated_flag})")
            return {
                "has_readme": True,
                "is_deprecated_in_readme": is_deprecated_flag,
                "readme_snippet": readme_text[:600]
            }
    except Exception as e:
        logger.warning(f"GitHub README fetch failed for {full_repo}: {e}")

    return {"has_readme": False, "is_deprecated_in_readme": False, "readme_snippet": ""}

