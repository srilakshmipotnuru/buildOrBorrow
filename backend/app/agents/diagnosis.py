import logging
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel, Field
from app.core.config import settings

logger = logging.getLogger(__name__)


class DiagnosisResponse(BaseModel):
    status: Literal["MATURE_STABLE", "MAINTAINED_ACTIVE", "ABANDONED_STRUGGLING", "VULNERABLE"] = Field(
        description="Qualitative package maintenance status"
    )
    is_abandoned: bool = Field(description="True if package is abandoned or struggling with unresolved bugs")
    confidence_score: float = Field(description="Confidence rating between 0.0 and 1.0 based on data completeness")
    confidence_reason: str = Field(description="Explanation of confidence rating")
    bug_severity_assessment: str = Field(description="Summary of open GitHub issue titles and severity")
    explanation: str = Field(description="Detailed qualitative analysis cross-referencing activity momentum with bug text")


def get_deterministic_fallback_diagnosis(
    package_name: str, 
    historical_summary: Dict[str, Any], 
    forecast_analysis: Dict[str, Any],
    recent_issues: List[Dict[str, Any]]
) -> DiagnosisResponse:
    """Fallback rule-based diagnosis when Gemini API is unconfigured or unavailable."""
    health_score = forecast_analysis.get("health_score", 50.0)
    trend = forecast_analysis.get("trend_direction", "STABLE")
    total_pushes = historical_summary.get("total_pushes", 0)
    issue_count = len(recent_issues)

    # Check for crash/vulnerability keywords in issue titles
    has_critical_bugs = any(
        any(k in item.get("title", "").lower() for k in ["crash", "segfault", "security", "cve", "vulnerability", "broken"])
        for item in recent_issues
    )

    if has_critical_bugs and health_score < 40:
        status = "VULNERABLE"
        is_abandoned = True
        bug_sev = "Critical: Open crash or vulnerability reports detected in issue titles with low maintenance activity."
        exp = f"Package '{package_name}' shows active unresolved critical bugs and a low health score ({health_score}/100)."
    elif health_score >= 70:
        status = "MAINTAINED_ACTIVE"
        is_abandoned = False
        bug_sev = f"Normal: {issue_count} open issues under active maintenance."
        exp = f"Package '{package_name}' is actively maintained with a strong health score ({health_score}/100) and steady momentum ({trend})."
    elif health_score >= 35 and not has_critical_bugs:
        status = "MATURE_STABLE"
        is_abandoned = False
        bug_sev = f"Low: {issue_count} open feature requests or minor issues; no critical crash reports."
        exp = f"Package '{package_name}' shows lower commit activity but zero critical bug reports. It is functionally mature and stable."
    else:
        status = "ABANDONED_STRUGGLING"
        is_abandoned = True
        bug_sev = f"High: {issue_count} open unaddressed issues."
        exp = f"Package '{package_name}' shows declining momentum ({trend}) and low health score ({health_score}/100) with unaddressed issue reports."

    confidence = 0.85 if recent_issues else 0.65
    reason = "Rule-based fallback calculation based on health score and issue keywords."

    return DiagnosisResponse(
        status=status,
        is_abandoned=is_abandoned,
        confidence_score=confidence,
        confidence_reason=reason,
        bug_severity_assessment=bug_sev,
        explanation=exp
    )


def diagnose_package(
    package_name: str,
    historical_summary: Dict[str, Any],
    forecast_analysis: Dict[str, Any],
    recent_issues: List[Dict[str, Any]]
) -> DiagnosisResponse:
    """
    Diagnosis Agent:
    Cross-references quantitative activity momentum with qualitative open GitHub issue text.
    Distinguishes feature-complete packages (MATURE_STABLE) from struggling packages (ABANDONED_STRUGGLING).
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.info("GEMINI_API_KEY unconfigured. Using fallback diagnosis agent.")
        return get_deterministic_fallback_diagnosis(package_name, historical_summary, forecast_analysis, recent_issues)

    formatted_issue_list = "\n".join([
        f"- {item.get('title', '')} (opened {item.get('age', 'recently')})"
        for item in recent_issues[:15]
    ]) if recent_issues else "No open GitHub issues retrieved or issues disabled."

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"You are an expert AI Software Health & Maintenance Diagnostic Agent.\n"
            f"Package Name: '{package_name}'\n\n"
            f"QUANTITATIVE METRICS:\n"
            f"- Historical Pushes (104 wks): {historical_summary.get('total_pushes', 0)}\n"
            f"- Historical PRs (104 wks): {historical_summary.get('total_prs', 0)}\n"
            f"- Historical Stars (104 wks): {historical_summary.get('total_stars', 0)}\n"
            f"- 90-Day Trend Direction: {forecast_analysis.get('trend_direction', 'STABLE')}\n"
            f"- Maintenance Health Score: {forecast_analysis.get('health_score', 50.0)} / 100.0\n"
            f"- Maintenance Verdict Signal: {forecast_analysis.get('maintenance_verdict_signal', 'UNKNOWN')}\n\n"
            f"QUALITATIVE RECENT GITHUB ISSUES (Title + Age):\n"
            f"{formatted_issue_list}\n\n"
            f"DIAGNOSIS INSTRUCTIONS:\n"
            f"1. Interpret whether the package is:\n"
            f"   - MATURE_STABLE: Low commits, but 0 crash/security bugs (feature-complete, rock-solid).\n"
            f"   - MAINTAINED_ACTIVE: Regular commits, steady updates, normal bug resolution.\n"
            f"   - ABANDONED_STRUGGLING: Low commits AND active unresolved crash reports or unaddressed bugs.\n"
            f"   - VULNERABLE: Severe unresolved security vulnerabilities or critical crash reports.\n"
            f"2. Set is_abandoned to true if status is ABANDONED_STRUGGLING or VULNERABLE.\n"
            f"3. Assign a confidence_score (0.0 to 1.0) based on data completeness.\n"
            f"4. Provide a clear bug_severity_assessment and detailed explanation."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DiagnosisResponse,
                temperature=0.1
            )
        )

        if response.parsed and isinstance(response.parsed, DiagnosisResponse):
            logger.info(f"Diagnosis Agent successfully diagnosed status '{response.parsed.status}' for {package_name}")
            return response.parsed
        else:
            return get_deterministic_fallback_diagnosis(package_name, historical_summary, forecast_analysis, recent_issues)

    except Exception as e:
        logger.error(f"Error in Diagnosis Agent call: {e}. Utilizing fallback.")
        return get_deterministic_fallback_diagnosis(package_name, historical_summary, forecast_analysis, recent_issues)
