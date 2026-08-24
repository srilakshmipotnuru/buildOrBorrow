from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud import bigquery
from app.core.bigquery import get_bigquery_client
from app.core.utils import extract_github_owner_repo
from app.queries.deps_dev import query_package_resolution
from app.queries.gh_archive import query_github_weekly_activity
from app.models.gh_archive import (
    GitHubArchiveResponse,
    GitHubActivitySummary,
    WeeklyActivity,
    PackageActivityBridgeResponse
)

router = APIRouter(
    prefix="/gh-archive",
    tags=["GitHub Activity"],
)


@router.get("/activity", response_model=GitHubArchiveResponse)
def get_repo_activity(
    owner: str = Query(..., description="Repository owner, e.g. psf"),
    repo: str = Query(..., description="Repository name, e.g. requests"),
    lookback_weeks: int = Query(
        4,
        ge=1,
        le=104,
        description="Weeks of historical data",
    ),
    client: bigquery.Client = Depends(get_bigquery_client),
):
    try:
        raw_weekly_data = query_github_weekly_activity(
            client=client,
            repo_owner=owner,
            repo_name=repo,
            lookback_weeks=lookback_weeks,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"BigQuery Error: {str(e)}",
        )

    if not raw_weekly_data:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No activity records found for "
                f"{owner}/{repo} in the specified timeframe."
            ),
        )

    total_pushes = sum(item["push_events"] for item in raw_weekly_data)
    total_prs = sum(item["pr_events"] for item in raw_weekly_data)
    total_issues = sum(item["issue_events"] for item in raw_weekly_data)
    total_stars = sum(item["star_events"] for item in raw_weekly_data)
    
    # Calculate contributor average safely (falls back to 0 if field is not in query)
    avg_contributors = (
        sum(item.get("active_contributors", 0) for item in raw_weekly_data) / len(raw_weekly_data)
        if raw_weekly_data else 0.0
    )

    summary = GitHubActivitySummary(
        total_pushes=total_pushes,
        total_prs=total_prs,
        total_issues=total_issues,
        total_stars=total_stars,
        active_weeks_count=len(raw_weekly_data),
        average_weekly_contributors=round(avg_contributors, 2)
    )

    return GitHubArchiveResponse(
        repo_name=f"{owner}/{repo}",
        lookback_weeks=lookback_weeks,
        summary=summary,
        weekly_timeline=[
            WeeklyActivity(**item)
            for item in raw_weekly_data
        ],
    )


@router.get("/package-activity", response_model=PackageActivityBridgeResponse)
def get_package_activity_by_name(
    package_name: str = Query(..., description="Name of the package (e.g., requests, fastapi)"),
    system: str = Query("pypi", description="Package ecosystem (e.g., pypi, npm, cargo)"),
    lookback_weeks: int = Query(12, ge=1, le=104, description="Weeks of historical data to scan"),
    client: bigquery.Client = Depends(get_bigquery_client)
):
    # Step 1: Query deps.dev to resolve metadata & GitHub repository URL
    try:
        pkg_resolution = query_package_resolution(
            client=client, 
            system=system, 
            package_name=package_name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"deps.dev resolution error: {str(e)}")
        
    if not pkg_resolution or not pkg_resolution.get("github_url"):
        raise HTTPException(
            status_code=404, 
            detail=f"Could not find a valid GitHub repository for package '{package_name}' in {system}."
        )

    # Step 2: Extract owner and repo name from GitHub URL
    parsed_repo = extract_github_owner_repo(pkg_resolution["github_url"])
    if not parsed_repo:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse valid owner/repo from URL: {pkg_resolution['github_url']}"
        )
        
    owner, repo = parsed_repo

    # Step 3: Query GH Archive BigQuery for the resolved repository
    try:
        raw_weekly_data = query_github_weekly_activity(
            client=client,
            repo_owner=owner,
            repo_name=repo,
            lookback_weeks=lookback_weeks
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GH Archive error: {str(e)}")

    if not raw_weekly_data:
        raise HTTPException(
            status_code=404, 
            detail=f"No activity records found in GH Archive for repository {owner}/{repo}."
        )

    # Step 4: Calculate aggregate activity statistics
    total_pushes = sum(item["push_events"] for item in raw_weekly_data)
    total_prs = sum(item["pr_events"] for item in raw_weekly_data)
    total_issues = sum(item["issue_events"] for item in raw_weekly_data)
    total_stars = sum(item["star_events"] for item in raw_weekly_data)
    
    avg_contributors = (
        sum(item.get("active_contributors", 0) for item in raw_weekly_data) / len(raw_weekly_data)
        if raw_weekly_data else 0.0
    )

    summary = GitHubActivitySummary(
        total_pushes=total_pushes,
        total_prs=total_prs,
        total_issues=total_issues,
        total_stars=total_stars,
        active_weeks_count=len(raw_weekly_data),
        average_weekly_contributors=round(avg_contributors, 2)
    )

    return PackageActivityBridgeResponse(
        package_name=package_name,
        system=system,
        github_url=pkg_resolution["github_url"],
        repo_owner=owner,
        repo_name=repo,
        lookback_weeks=lookback_weeks,
        summary=summary,
        weekly_timeline=[WeeklyActivity(**item) for item in raw_weekly_data]
    )