from fastapi import HTTPException
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
    Raises HTTP 503 if Gemini AI service is unconfigured or fails.
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.error("GEMINI_API_KEY unconfigured. Unable to execute Diagnosis Agent.")
        raise HTTPException(
            status_code=503,
            detail="Gemini AI service unavailable: GEMINI_API_KEY is not configured on the server."
        )

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
            raise HTTPException(
                status_code=503,
                detail="Diagnosis Agent failed to parse structured output from Gemini AI."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Diagnosis Agent call: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Diagnosis Agent call failed: {str(e)}"
        )

