from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud import bigquery
from app.core.bigquery import get_bigquery_client
from app.core.config import settings
from app.core.utils import extract_github_owner_repo
from app.queries.deps_dev import query_package_resolution
from app.queries.gh_archive import query_github_weekly_activity, query_arima_plus_forecast
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
    lookback_weeks: int = Query(settings.DEFAULT_LOOKBACK_WEEKS, ge=1, le=settings.MAX_LOOKBACK_WEEKS, description="Historical weeks used to fit model"),
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

    # 2. Extract historical weekly data from custom data warehouse
    try:
        raw_weekly_data = query_github_weekly_activity(
            client=client,
            repo_owner=owner,
            repo_name=repo,
            lookback_weeks=lookback_weeks
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GH Warehouse query failed: {str(e)}")

    if not raw_weekly_data:
        raise HTTPException(
            status_code=404,
            detail=f"No activity records found for {owner}/{repo}."
        )

    # 3. Item 1 Zero-Activity Guard & Dual Forecasting Engine
    total_maintenance_events = sum(item.get("total_events", 0) for item in raw_weekly_data)
    forecast_results = None

    if total_maintenance_events == 0:
        forecast_results = {
            "projected_timeline": [],
            "trend_direction": "DECLINING",
            "health_score": 0.0,
            "projected_total_events_90d": 0,
            "maintenance_verdict_signal": "AT_RISK_STAGNANT"
        }
    else:
        # Primary: Real BigQuery ML ARIMA_PLUS
        if getattr(settings, "ENABLE_BQ_ML_ARIMA", True):
            try:
                arima_timeline = query_arima_plus_forecast(
                    client=client,
                    repo_owner=owner,
                    repo_name=repo,
                    lookback_weeks=lookback_weeks,
                    forecast_weeks=settings.DEFAULT_FORECAST_WEEKS,
                    weekly_history=raw_weekly_data
                )
                if arima_timeline:
                    projected_total = sum(p.get("projected_events", 0) for p in arima_timeline)
                    slope = (arima_timeline[-1]["projected_events"] - arima_timeline[0]["projected_events"]) / len(arima_timeline) if len(arima_timeline) > 1 else 0
                    trend = "ACCELERATING" if slope > 0.5 else ("DECLINING" if slope < -0.5 else "STABLE")
                    health_score = min(100.0, max(0.0, (projected_total / settings.DEFAULT_FORECAST_WEEKS) * 8.0 + (30.0 if trend == "ACCELERATING" else 15.0)))
                    signal = "HEALTHY_ACTIVE" if health_score >= 60 else ("SLOW_MAINTENANCE" if health_score >= 30 else "AT_RISK_STAGNANT")
                    forecast_results = {
                        "projected_timeline": arima_timeline,
                        "trend_direction": trend,
                        "health_score": round(health_score, 1),
                        "projected_total_events_90d": projected_total,
                        "maintenance_verdict_signal": signal
                    }
            except Exception:
                forecast_results = None

        # Backup: Statistical series forecasting in Python
        if not forecast_results:
            forecast_results = project_weekly_series(raw_weekly_data, forecast_weeks=settings.DEFAULT_FORECAST_WEEKS)

    return PackageForecastResponse(
        package_name=package_name,
        system=system,
        repo_owner=owner,
        repo_name=repo,
        historical_weeks_analyzed=len(raw_weekly_data),
        forecast_horizon_days=90,
        forecast=ForecastAnalysis(**forecast_results)
    )