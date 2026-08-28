from typing import List, Optional
from pydantic import BaseModel, Field

class ProjectedWeek(BaseModel):
    week_start: str
    projected_events: int
    confidence_lower: int
    confidence_upper: int

class ForecastAnalysis(BaseModel):
    trend_direction: str
    health_score: float
    projected_total_events_90d: int
    maintenance_verdict_signal: str
    projected_timeline: List[ProjectedWeek]

class PackageForecastResponse(BaseModel):
    package_name: str
    system: str
    repo_owner: str
    repo_name: str
    historical_weeks_analyzed: int
    forecast_horizon_days: int = 90
    forecast: ForecastAnalysis