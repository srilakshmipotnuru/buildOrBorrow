from datetime import datetime, timedelta
import math
from typing import List, Dict, Any

def calculate_trend_slope(y_values: List[float]) -> float:
    """Calculates linear slope (Ordinary Least Squares) for a series."""
    n = len(y_values)
    if n < 2:
        return 0.0
    x_values = list(range(n))
    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n
    
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    
    return numerator / denominator if denominator != 0 else 0.0

def project_weekly_series(
    historical_timeline: List[Dict[str, Any]], 
    forecast_weeks: int = 13
) -> Dict[str, Any]:
    """
    Projects 90-day (~13 weeks) activity from historical weekly GH Archive data.
    """
    if not historical_timeline:
        return {
            "projected_timeline": [],
            "trend_direction": "UNKNOWN",
            "health_score": 0.0,
            "projected_total_events": 0,
            "maintenance_verdict_signal": "ABANDONED"
        }

    # Sort chronological
    timeline = sorted(historical_timeline, key=lambda x: x["week_start"])
    
    # Use weighted_activity score if available, or compute on the fly
    weighted_events_series = [
        float(item.get("weighted_activity")) if item.get("weighted_activity") is not None else
        (float(item.get("push_events", 0)) * 3.0 + float(item.get("pr_events", 0)) * 2.0 + float(item.get("issue_events", 0)) * 1.0)
        for item in timeline
    ]
    commits_series = [float(item.get("push_events", 0)) for item in timeline]
    prs_series = [float(item.get("pr_events", 0)) for item in timeline]
    
    # Calculate baseline and trajectory
    slope = calculate_trend_slope(weighted_events_series)
    recent_window = weighted_events_series[-4:] if len(weighted_events_series) >= 4 else weighted_events_series
    recent_avg = sum(recent_window) / len(recent_window) if recent_window else 0.0

    # Parse last week start date
    last_week_str = timeline[-1]["week_start"][:10]
    last_week_date = datetime.strptime(last_week_str, "%Y-%m-%d")

    projected_timeline = []
    accumulated_projected = 0

    for i in range(1, forecast_weeks + 1):
        future_week = last_week_date + timedelta(weeks=i)
        
        # Dampen extreme slope projections over time
        damping_factor = math.exp(-0.05 * i)
        projected_val = max(0.0, recent_avg + (slope * i * damping_factor))
        rounded_val = int(round(projected_val))
        
        accumulated_projected += rounded_val
        projected_timeline.append({
            "week_start": future_week.strftime("%Y-%m-%d"),
            "projected_events": rounded_val,
            "confidence_lower": max(0, int(rounded_val * 0.7)),
            "confidence_upper": int(rounded_val * 1.3) + 1
        })

    # Trend categorization
    if slope > 0.5:
        trend_direction = "ACCELERATING"
    elif slope < -0.5:
        trend_direction = "DECLINING"
    else:
        trend_direction = "STABLE"

    # Maintenance Health Score (0 - 100)
    avg_commits = sum(commits_series) / len(commits_series) if commits_series else 0
    avg_prs = sum(prs_series) / len(prs_series) if prs_series else 0
    
    activity_weight = min(50.0, recent_avg * 5)
    momentum_weight = 30.0 if trend_direction == "ACCELERATING" else (20.0 if trend_direction == "STABLE" else 5.0)
    consistency_weight = min(20.0, (avg_commits + avg_prs) * 2)
    
    health_score = round(min(100.0, activity_weight + momentum_weight + consistency_weight), 2)

    # Initial signal classification
    if health_score >= 70:
        verdict_signal = "HEALTHY_ACTIVE"
    elif health_score >= 35:
        verdict_signal = "SLOW_MAINTENANCE"
    else:
        verdict_signal = "AT_RISK_STAGNANT"

    return {
        "projected_timeline": projected_timeline,
        "trend_direction": trend_direction,
        "health_score": health_score,
        "projected_total_events_90d": accumulated_projected,
        "maintenance_verdict_signal": verdict_signal
    }