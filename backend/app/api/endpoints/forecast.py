from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud import bigquery
from app.core.bigquery import get_bigquery_client
from app.core.utils import extract_github_owner_repo
from app.queries.deps_dev import query_package_resolution
from app.queries.gh_archive import query_github_weekly_activity
from app.services.forecasting import project_weekly_series
from app.models.forecast import PackageForecastResponse, ForecastAnalysis

router = APIRouter(
    prefix="/forecast",
    tags=["Activity Forecasting"],
)

@router.get("/package-forecast", response_model=PackageForecastResponse)
def get_package_maintenance_forecast(
    package_name: str = Query(..., description="Package name (e.g., numpy, requests)"),
    system: str = Query("pypi", description="Ecosystem (pypi, npm, cargo)"),
    lookback_weeks: int = Query(104, ge=1, le=104, description="Historical weeks used to fit model"),
    client: bigquery.Client = Depends(get_bigquery_client),
):
    # 1. Resolve package to GitHub repo
    try:
        pkg_resolution = query_package_resolution(
            client=client, system=system, package_name=package_name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"deps.dev query failed: {str(e)}")

    if not pkg_resolution or not pkg_resolution.get("github_url"):
        raise HTTPException(
            status_code=404,
            detail=f"GitHub repository URL not found for package '{package_name}'."
        )

    parsed_repo = extract_github_owner_repo(pkg_resolution["github_url"])
    if not parsed_repo:
        raise HTTPException(
            status_code=422,
            detail=f"Unable to parse repository URL: {pkg_resolution['github_url']}"
        )
    owner, repo = parsed_repo

    # 2. Extract historical weekly data from GH Archive
    try:
        raw_weekly_data = query_github_weekly_activity(
            client=client,
            repo_owner=owner,
            repo_name=repo,
            lookback_weeks=lookback_weeks
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GH Archive query failed: {str(e)}")

    if not raw_weekly_data:
        raise HTTPException(
            status_code=404,
            detail=f"No activity records found for {owner}/{repo}."
        )

    # 3. Generate 90-day forecast
    forecast_results = project_weekly_series(raw_weekly_data, forecast_weeks=13)

    return PackageForecastResponse(
        package_name=package_name,
        system=system,
        repo_owner=owner,
        repo_name=repo,
        historical_weeks_analyzed=len(raw_weekly_data),
        forecast_horizon_days=90,
        forecast=ForecastAnalysis(**forecast_results)
    )