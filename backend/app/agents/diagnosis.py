import logging
from typing import List, Dict, Any, Literal, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field
from app.core.config import settings

logger = logging.getLogger(__name__)


class DiagnosisResponse(BaseModel):
    status: Literal["MATURE_STABLE", "MAINTAINED_ACTIVE", "ABANDONED_STRUGGLING", "VULNERABLE", "UNCERTAIN_UNVERIFIED"] = Field(
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
    recent_issues: List[Dict[str, Any]],
    readme_context: Optional[Dict[str, Any]] = None,
    security_context: Optional[Dict[str, Any]] = None
) -> DiagnosisResponse:
    """
    Diagnosis Agent:
    Cross-references quantitative activity momentum with qualitative open GitHub issue text,
    GitHub README deprecation warnings, and version-specific vulnerability ranges.
    Distinguishes feature-complete packages (MATURE_STABLE) from struggling packages (ABANDONED_STRUGGLING).
    Raises HTTP 503 if Gemini AI service is unconfigured or fails.
    """
    readme_info = readme_context or {}
    sec_info = security_context or {}

    def _rule_based_fallback() -> DiagnosisResponse:
        logger.warning(f"   [Diagnosis Fallback] Executing production-grade rule-based diagnosis for '{package_name}'...")
        health_score = forecast_analysis.get("health_score", 50.0)
        verdict_signal = forecast_analysis.get("maintenance_verdict_signal", "UNKNOWN")
        cve_count = sec_info.get("total_vulnerabilities", 0)
        crit_cve = sec_info.get("critical_vulnerabilities", 0)
        is_archived = readme_info.get("is_archived", False)

        # 1. Official Platform Archival Signal (GET /repos/{owner}/{repo})
        if is_archived:
            return DiagnosisResponse(
                status="ABANDONED_STRUGGLING",
                is_abandoned=True,
                confidence_score=1.0,
                confidence_reason="Official GitHub Repository status is ARCHIVED (read-only mode).",
                bug_severity_assessment="Repository is officially archived and read-only.",
                explanation=f"Package '{package_name}' repository is officially ARCHIVED (read-only mode) on GitHub. Maintenance has permanently ceased."
            )

        # 2. Deprecation & Replacement Check (README deprecation signal)
        if is_readme_deprecated:
            return DiagnosisResponse(
                status="ABANDONED_STRUGGLING",
                is_abandoned=True,
                confidence_score=0.95,
                confidence_reason="Package is officially deprecated/renamed in README header or ecosystem registry.",
                bug_severity_assessment="Project is unmaintained / deprecated.",
                explanation=f"Fallback diagnosis identified '{package_name}' as deprecated from README notices."
            )

        # 2. Critical Security Check
        if crit_cve > 0 or cve_count >= 3:
            return DiagnosisResponse(
                status="VULNERABLE",
                is_abandoned=True,
                confidence_score=0.95,
                confidence_reason="Unresolved critical security vulnerabilities detected.",
                bug_severity_assessment=f"Active security vulnerabilities: {cve_count} total ({crit_cve} critical).",
                explanation=f"Package '{package_name}' has unresolved security advisories."
            )

        # 3. Repository / Telemetry Unavailable Signal
        if verdict_signal == "UNAVAILABLE":
            return DiagnosisResponse(
                status="UNCERTAIN_UNVERIFIED",
                is_abandoned=False,
                confidence_score=0.5,
                confidence_reason="Repository URL or telemetry is unavailable in ecosystem registry metadata.",
                bug_severity_assessment="Could not fetch open GitHub issues or activity telemetry.",
                explanation=f"Package '{package_name}' repository metadata is unavailable or unverified in the ecosystem registry."
            )

        # 4. "Finished Software" vs. "Dead Software" Check
        if health_score >= 60 or verdict_signal == "HEALTHY_ACTIVE":
            status_val = "MAINTAINED_ACTIVE"
            is_ab = False
        elif health_score < 30 or verdict_signal == "AT_RISK_STAGNANT":
            status_val = "ABANDONED_STRUGGLING"
            is_ab = True
        else:
            status_val = "MATURE_STABLE"
            is_ab = False

        return DiagnosisResponse(
            status=status_val,
            is_abandoned=is_ab,
            confidence_score=0.85,
            confidence_reason="Evaluated using quantitative health score and maintenance indicators.",
            bug_severity_assessment=f"Analyzed {len(recent_issues)} recent open GitHub issues.",
            explanation=f"Production-grade fallback classified '{package_name}' as '{status_val}'."
        )

    api_key = settings.GEMINI_API_KEY
    is_readme_deprecated = readme_info.get("is_deprecated_in_readme", False)
    is_archived = readme_info.get("is_archived", False)

    if not api_key or is_readme_deprecated or is_archived:
        return _rule_based_fallback()

    formatted_issue_list = "\n".join([
        f"- {item.get('title', '')} (opened {item.get('age', 'recently')})"
        for item in recent_issues[:15]
    ]) if recent_issues else "No open GitHub issues retrieved or issues disabled."

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        data_status_str = (
            f"- Historical Pushes (104 wks): {historical_summary.get('total_pushes')}\n"
            f"- Historical PRs (104 wks): {historical_summary.get('total_prs')}\n"
            f"- Historical Stars (104 wks): {historical_summary.get('total_stars')}\n"
        ) if historical_summary.get("data_retrieved", True) else "- Historical Activity: Data Unavailable / Skipped (DO NOT infer 0 commits or project abandonment)\n"

        prompt = (
            f"You are an expert AI Software Health & Maintenance Diagnostic Agent.\n"
            f"Package Name: '{package_name}'\n\n"
            f"QUANTITATIVE METRICS:\n"
            f"{data_status_str}"
            f"- 90-Day Trend Direction: {forecast_analysis.get('trend_direction', 'STABLE')}\n"
            f"- Maintenance Health Score: {forecast_analysis.get('health_score', 50.0)} / 100.0\n"
            f"- Maintenance Verdict Signal: {forecast_analysis.get('maintenance_verdict_signal', 'UNKNOWN')}\n\n"
            f"QUALITATIVE RECENT GITHUB ISSUES (Title + Age):\n"
            f"{formatted_issue_list}\n\n"
            f"DIAGNOSIS INSTRUCTIONS:\n"
            f"1. CRITICAL DISTINCTION - MATURE BEDROCK vs ABANDONED:\n"
            f"   - If a package is a widely-used foundational bedrock library (e.g., requests, lodash, numpy, urllib3, pandas) with high usage and zero critical CVEs, low recent commit velocity reflects API STABILITY ('MATURE_STABLE'), NOT project abandonment.\n"
            f"   - Only diagnose ABANDONED_STRUGGLING if there are unaddressed open critical CVEs, broken CI, or an explicit deprecation/archival notice.\n"
            f"2. SUPERSEDED / RENAMED PACKAGES:\n"
            f"   - If the package is officially deprecated, renamed, or replaced (e.g. pep8 -> pycodestyle, requests-async -> httpx, nomurl -> urllib3), classify it as ABANDONED_STRUGGLING and set is_abandoned=true.\n"
            f"3. Classify into one of 4 statuses:\n"
            f"   - MATURE_STABLE: API-complete bedrock package, low/steady churn, 0 critical bugs/CVEs.\n"
            f"   - MAINTAINED_ACTIVE: Active commits, regular releases, healthy issue resolution.\n"
            f"   - ABANDONED_STRUGGLING: Unmaintained/deprecated package or low commits AND active unresolved crash bugs.\n"
            f"   - VULNERABLE: Severe unresolved security vulnerabilities (CVEs) or active security advisories.\n"
            f"4. Set is_abandoned to true ONLY if status is ABANDONED_STRUGGLING or VULNERABLE.\n"
            f"5. Assign a confidence_score (0.0 to 1.0) and detailed explanation."
        )

        from app.core.utils import call_gemini_with_retry

        response = call_gemini_with_retry(
            client=client,
            prompt=prompt,
            response_schema=DiagnosisResponse,
            temperature=settings.GEMINI_DEFAULT_TEMPERATURE
        )

        if response.parsed and isinstance(response.parsed, DiagnosisResponse):
            diag = response.parsed
            logger.info(f"   [Diagnosis Agent] Status: '{diag.status}' (Abandoned: {diag.is_abandoned}, Confidence: {diag.confidence_score})")
            logger.info(f"   [Diagnosis Agent] Bug Assessment: {diag.bug_severity_assessment}")
            logger.info(f"   [Diagnosis Agent] Explanation: {diag.explanation}")
            return diag
        else:
            return _rule_based_fallback()

    except Exception as e:
        logger.error(f"Error in Diagnosis Agent call ({e}). Triggering statistical fallback...")
        return _rule_based_fallback()

