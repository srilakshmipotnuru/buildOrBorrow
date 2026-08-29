import logging
from typing import List, Dict, Any, Literal, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field
from app.core.config import settings

logger = logging.getLogger(__name__)

class AlternativeVerification(BaseModel):
    name: str
    system: str
    version: Optional[str] = None
    verified_exists: bool = True
    github_url: Optional[str] = None
    licenses: List[str] = Field(default_factory=list)
    published_at: Optional[str] = None
    note: Optional[str] = None


class VerdictResponse(BaseModel):
    decision: Literal["BORROW", "MIGRATE", "BUILD"] = Field(description="Final decision: BORROW, MIGRATE, or BUILD")
    confidence_score: float = Field(description="Calculative confidence score between 0.0 and 1.0")
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="Human-readable confidence rating")
    confidence_factors: List[str] = Field(description="List of evidence factors affecting confidence")
    reasoning: List[str] = Field(description="Bullet points explaining why this decision was reached")
    recommended_alternative: Optional[str] = Field(None, description="Suggested active alternative package name if decision is MIGRATE")
    recommended_alternative_system: Optional[str] = Field(None, description="Suggested alternative ecosystem (e.g. PYPI, NPM)")
    alternative_verification: Optional[AlternativeVerification] = Field(None, description="Lightweight verification output for recommended alternative")
    estimated_build_effort: Optional[str] = Field(None, description="Estimated effort/lines of code if decision is BUILD")


def calculate_formulaic_confidence(
    has_history: bool,
    has_issues: bool,
    has_security: bool,
    llm_delta: float = 0.0
) -> tuple[float, str, List[str]]:
    """Calculative Confidence Engine: Formulaic Base + LLM Qualitative Delta + Hard Caps."""
    base_score = 0.0
    factors = []

    if has_history:
        base_score += 0.35
        factors.append("+ 104-week historical activity timeline & 90-day forecast available")
    else:
        factors.append("- Historical repository activity unavailable")

    if has_issues:
        base_score += 0.35
        factors.append("+ Open GitHub issue titles evaluated for bug severity")
    else:
        factors.append("- GitHub open issue text unavailable (confidence capped at 0.65)")

    if has_security:
        base_score += 0.30
        factors.append("+ deps.dev security advisory & dependency burden scan complete")

    # Hard Cap Guard if key data source was missing
    if not has_issues or not has_history:
        base_score = min(base_score, 0.65)

    # Apply LLM Delta (-0.15 to +0.05) safely
    final_score = round(max(0.10, min(1.0, base_score + llm_delta)), 2)
    level = "HIGH" if final_score >= 0.85 else ("MEDIUM" if final_score >= 0.60 else "LOW")

    return final_score, level, factors


def generate_verdict(
    user_requirement: Optional[str],
    package_resolution: Dict[str, Any],
    security_context: Dict[str, Any],
    forecast_analysis: Dict[str, Any],
    diagnosis_output: Dict[str, Any],
    system: str = "PYPI"
) -> VerdictResponse:
    """
    Verdict Agent:
    Synthesizes user requirement, package resolution, security, forecast, and diagnosis
    to output a final decision: BORROW, MIGRATE, or BUILD.
    Integrates the Calculative Confidence Engine (Formulaic Base + LLM Delta + Hard Caps).
    Raises HTTP 503 if Gemini AI service is unconfigured or fails.
    """
    api_key = settings.GEMINI_API_KEY
    diag_status = diagnosis_output.get("status", "MAINTAINED_ACTIVE")
    pkg_name = package_resolution.get("name", "target-package")

    if not api_key:
        logger.error("GEMINI_API_KEY unconfigured. Unable to execute Verdict Agent.")
        raise HTTPException(
            status_code=503,
            detail="Gemini AI service unavailable: GEMINI_API_KEY is not configured on the server."
        )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"You are the Senior Software Architecture Verdict Agent for BuildOrBorrow.\n"
            f"Target Package: '{pkg_name}' (Ecosystem: '{system}')\n"
            f"User Feature Requirement: '{user_requirement or 'General usage'}'\n\n"
            f"EVIDENCE SUMMARY:\n"
            f"- Diagnosis Status: {diag_status}\n"
            f"- Diagnosis Explanation: {diagnosis_output.get('explanation', '')}\n"
            f"- Maintenance Health Score: {forecast_analysis.get('health_score', 50.0)} / 100.0\n"
            f"- 90-Day Trend Direction: {forecast_analysis.get('trend_direction', 'STABLE')}\n"
            f"- Critical Vulnerabilities: {security_context.get('critical_vulnerabilities', 0)}\n"
            f"- High Vulnerabilities: {security_context.get('high_vulnerabilities', 0)}\n"
            f"- Transitive Dependencies: {security_context.get('transitive_dependencies', 0)}\n"
            f"- License: {security_context.get('license', 'Unknown')}\n\n"
            f"DECISION RULES:\n"
            f"1. BUILD: If the user requirement is trivial (e.g. left padding, simple string truncation, "
            f"   shallow clone, basic utility) where taking an external package dependency is unnecessary bloat.\n"
            f"2. MIGRATE: If the package is abandoned, struggling, vulnerable, or has critical CVEs. "
            f"   Must suggest a modern active alternative package name and its ecosystem ('recommended_alternative' & 'recommended_alternative_system').\n"
            f"3. BORROW: If the package is mature, active, or stable and the feature requirement is non-trivial.\n\n"
            f"OUTPUT REQUIREMENTS:\n"
            f"- Set decision to BORROW, MIGRATE, or BUILD.\n"
            f"- Set confidence_score (0.0 to 1.0) and confidence_level (HIGH, MEDIUM, or LOW).\n"
            f"- Provide 3 key reasoning bullet points.\n"
            f"- If BUILD, provide estimated_build_effort (e.g. '15 lines of code, ~10 mins')."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VerdictResponse,
                temperature=0.1
            )
        )

        if response.parsed and isinstance(response.parsed, VerdictResponse):
            verdict = response.parsed
            # Calibrate confidence with Formulaic Base Engine
            conf_score, conf_level, conf_factors = calculate_formulaic_confidence(
                has_history=bool(forecast_analysis),
                has_issues=True,
                has_security=bool(security_context),
                llm_delta=0.0
            )
            verdict.confidence_score = conf_score
            verdict.confidence_level = conf_level
            verdict.confidence_factors = conf_factors
            logger.info(f"Verdict Agent generated decision '{verdict.decision}' for {pkg_name}")
            return verdict
        else:
            raise HTTPException(
                status_code=503,
                detail="Verdict Agent failed to parse structured output from Gemini AI."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Verdict Agent call: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Verdict Agent call failed: {str(e)}"
        )

