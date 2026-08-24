from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud import bigquery

from app.core.bigquery import get_bigquery_client
from app.queries.gh_archive import query_github_weekly_activity
from app.models.gh_archive import (
    GitHubArchiveResponse,
    GitHubActivitySummary,
    WeeklyActivity,
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

    total_pushes = sum(
        item["push_events"] for item in raw_weekly_data
    )
    total_prs = sum(
        item["pr_events"] for item in raw_weekly_data
    )
    total_issues = sum(
        item["issue_events"] for item in raw_weekly_data
    )
    total_stars = sum(
        item["star_events"] for item in raw_weekly_data
    )
    avg_contributors = (
        sum(item["active_contributors"] for item in raw_weekly_data) 
        / len(raw_weekly_data)
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