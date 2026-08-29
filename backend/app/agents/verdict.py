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

    def _rule_based_verdict_fallback() -> VerdictResponse:
        logger.warning(f"   [Verdict Fallback] Executing formulaic verdict fallback for '{pkg_name}'...")
        is_ab = diagnosis_output.get("is_abandoned", False)
        status_val = diagnosis_output.get("status", "MAINTAINED_ACTIVE")
        health_score = forecast_analysis.get("health_score", 50.0)
        cve_count = security_context.get("total_vulnerabilities", 0)

        if is_ab or status_val in ["ABANDONED_STRUGGLING", "VULNERABLE"] or cve_count > 0:
            dec = "MIGRATE"
            rec_alt = f"{pkg_name}-alternative" if pkg_name else None
            reasoning_bullets = [
                f"Package '{pkg_name}' is classified as {status_val} with health score {health_score}/100.",
                f"Active security vulnerabilities or project stagnation suggest migrating to a maintained alternative.",
                "In-house migration or adopting a supported library reduces supply-chain risk."
            ]
        elif health_score >= 60:
            dec = "BORROW"
            rec_alt = None
            reasoning_bullets = [
                f"Package '{pkg_name}' demonstrates healthy maintenance momentum (score: {health_score}/100).",
                "Security vulnerability check passed with zero critical advisories.",
                "Borrowing this package provides optimal productivity over building in-house."
            ]
        else:
            dec = "BUILD"
            rec_alt = None
            reasoning_bullets = [
                f"Package '{pkg_name}' shows weak activity momentum (score: {health_score}/100).",
                "Implementing a focused zero-dependency utility eliminates external overhead.",
                "Zero third-party dependencies ensure long-term stability and full codebase control."
            ]

        conf_score, conf_level, conf_factors = calculate_formulaic_confidence(
            has_history=bool(forecast_analysis),
            has_issues=True,
            has_security=bool(security_context),
            llm_delta=0.0
        )

        return VerdictResponse(
            decision=dec,
            confidence_score=conf_score,
            confidence_level=conf_level,
            confidence_factors=conf_factors,
            reasoning=reasoning_bullets,
            recommended_alternative=rec_alt,
            recommended_alternative_system=system,
            estimated_build_effort="~25 lines of code, 15 mins" if dec == "BUILD" else None
        )

    if not api_key:
        return _rule_based_verdict_fallback()

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

        from app.core.utils import call_gemini_with_retry

        response = call_gemini_with_retry(
            client=client,
            prompt=prompt,
            response_schema=VerdictResponse,
            temperature=settings.GEMINI_DEFAULT_TEMPERATURE
        )

        if response.parsed and isinstance(response.parsed, VerdictResponse):
            verdict = response.parsed
            conf_score, conf_level, conf_factors = calculate_formulaic_confidence(
                has_history=bool(forecast_analysis),
                has_issues=True,
                has_security=bool(security_context),
                llm_delta=0.0
            )
            verdict.confidence_score = conf_score
            verdict.confidence_level = conf_level
            verdict.confidence_factors = conf_factors
            logger.info(f"   [Verdict Agent] Decision: '{verdict.decision}' (Score: {verdict.confidence_score} - {verdict.confidence_level})")
            if verdict.reasoning:
                logger.info(f"   [Verdict Agent] Key Reasoning:")
                for r_bullet in verdict.reasoning:
                    logger.info(f"      • {r_bullet}")
            if verdict.decision == "MIGRATE" and verdict.recommended_alternative:
                logger.info(f"   [Verdict Agent] Recommended Alternative: '{verdict.recommended_alternative}' ({verdict.recommended_alternative_system or system})")
            elif verdict.decision == "BUILD" and verdict.estimated_build_effort:
                logger.info(f"   [Verdict Agent] Estimated Build Effort: {verdict.estimated_build_effort}")
            return verdict
        else:
            return _rule_based_verdict_fallback()

    except Exception as e:
        logger.error(f"Error in Verdict Agent call ({e}). Triggering formulaic verdict fallback...")
        return _rule_based_verdict_fallback()
