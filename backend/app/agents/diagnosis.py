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
    security_context: Optional[Dict[str, Any]] = None,
    package_resolution: Optional[Dict[str, Any]] = None
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
    resolution_info = package_resolution or {}
    system_name = resolution_info.get("system", "UNKNOWN")
    github_repo_url = resolution_info.get("github_url", "N/A")
    project_repo_name = resolution_info.get("project_name", package_name)
    stargazers = resolution_info.get("stargazers_count", 0)
    dependents = resolution_info.get("dependents_count", 0)

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI Diagnosis Agent is unavailable (GEMINI_API_KEY not configured)."
        )

    is_archived = readme_info.get("is_archived", False)
    readme_snippet = readme_info.get("readme_snippet", "")

    formatted_issue_list = "\n".join([
        f"- {item.get('title', '')} (opened {item.get('age', 'recently')})"
        for item in recent_issues[:15]
    ]) if recent_issues else "No open GitHub issues retrieved or issues disabled."

    readme_section = (
        f"README CONTEXT & DEPRECATION SIGNALS:\n"
        f"\"\"\"\n{readme_snippet}\n\"\"\"\n"
        f"- Instruction: Carefully read the README excerpt. Evaluate if maintainers officially state the entire package is deprecated, unmaintained, or superseded. Do NOT mark a library as abandoned merely because it mentions deprecating an old parameter or v1 helper.\n\n"
    ) if readme_snippet else ""

    archived_str = "- Official GitHub Platform Status: ARCHIVED (read-only mode, permanent maintenance cessation)\n" if is_archived else ""

    data_status_str = (
        f"- Historical Pushes (104 wks): {historical_summary.get('total_pushes')}\n"
        f"- Historical PRs (104 wks): {historical_summary.get('total_prs')}\n"
        f"- Historical Stars (104 wks): {historical_summary.get('total_stars')}\n"
    ) if historical_summary.get("data_retrieved", True) else "- Historical Activity: Data Unavailable / Skipped (DO NOT infer 0 commits or project abandonment)\n"

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = (
            f"You are the Senior Software Package Health Diagnosis Agent specialized in open-source repository maintenance analysis.\n"
            f"ECOSYSTEM & REPOSITORY GROUNDING:\n"
            f"- Target Ecosystem Registry: {system_name}\n"
            f"- Package Name: '{package_name}'\n"
            f"- Target Repository: {github_repo_url} ({project_repo_name})\n"
            f"- Repository Stars: {stargazers}\n"
            f"- Downstream Dependent Projects: {dependents}\n"
            f"{archived_str}\n"
            f"QUANTITATIVE METRICS:\n"
            f"{data_status_str}"
            f"- 90-Day Trend Direction: {forecast_analysis.get('trend_direction', 'STABLE')}\n"
            f"- Maintenance Health Score: {forecast_analysis.get('health_score', 50.0)} / 100.0\n"
            f"- Maintenance Verdict Signal: {forecast_analysis.get('maintenance_verdict_signal', 'UNKNOWN')}\n\n"
            f"QUALITATIVE RECENT GITHUB ISSUES (Title + Age):\n"
            f"{formatted_issue_list}\n\n"
            f"{readme_section}"
            f"DIAGNOSIS INSTRUCTIONS:\n"
            f"1. CRITICAL DISTINCTION - MATURE BEDROCK vs ABANDONED:\n"
            f"   - Evaluate ONLY the specific target repository '{project_repo_name}' on system '{system_name}'. DO NOT conflate packages across different ecosystems.\n"
            f"   - A package can ONLY be classified as MATURE_STABLE (Bedrock) if it has empirical proof of high adoption (e.g. high dependents count, high star count, or verified foundational usage in system '{system_name}') AND zero critical CVEs/crash bugs.\n"
            f"   - If target repository adoption metrics (stars/dependents) AND commit activity are low or zero, DO NOT excuse zero activity as 'API stability'. Classify as ABANDONED_STRUGGLING or UNCERTAIN_UNVERIFIED.\n"
            f"2. SUPERSEDED / RENAMED / DEPRECATED PACKAGES:\n"
            f"   - If the package is officially deprecated, renamed, archived on GitHub, or maintainers declare it unmaintained in the README, classify it as ABANDONED_STRUGGLING and set is_abandoned=true.\n"
            f"   - Do NOT mark an otherwise active library as abandoned if it merely mentions deprecating an old sub-feature in release notes.\n"
            f"3. Classify into one of 5 statuses:\n"
            f"   - MATURE_STABLE: API-complete bedrock package with verified high adoption, low/steady churn, 0 critical bugs/CVEs.\n"
            f"   - MAINTAINED_ACTIVE: Active commits, regular releases, healthy issue resolution.\n"
            f"   - ABANDONED_STRUGGLING: Unmaintained/deprecated package, or obscure low-usage package with stagnant activity.\n"
            f"   - UNCERTAIN_UNVERIFIED: Unverified telemetry or missing repository metadata.\n"
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
            raise HTTPException(
                status_code=502,
                detail=f"Diagnosis Agent failed to structure diagnosis for '{package_name}'."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Diagnosis Agent call ({e}).")
        raise HTTPException(
            status_code=503,
            detail=f"AI Diagnosis Agent service error ({type(e).__name__}). Please retry."
        )
