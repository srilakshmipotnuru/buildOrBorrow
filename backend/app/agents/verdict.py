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
    decision: Literal["BORROW", "MIGRATE", "BUILD", "UNVERIFIED_CANDIDATES"] = Field(description="Final decision: BORROW, MIGRATE, BUILD, or UNVERIFIED_CANDIDATES")
    confidence_score: float = Field(description="Calculative confidence score between 0.0 and 1.0")
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="Human-readable confidence rating")
    confidence_factors: List[str] = Field(description="List of evidence factors affecting confidence")
    reasoning: List[str] = Field(description="Bullet points explaining why this decision was reached")
    recommended_alternative: Optional[str] = Field(None, description="Suggested active alternative package name if decision is MIGRATE")
    recommended_alternative_system: Optional[str] = Field(None, description="Suggested alternative ecosystem (e.g. PYPI, NPM)")
    recommended_pinned_version: Optional[str] = Field(None, description="Recommended safe pinned release version if latest has active CVEs")
    alternative_verification: Optional[AlternativeVerification] = Field(None, description="Lightweight verification output for recommended alternative")
    estimated_build_effort: Optional[str] = Field(None, description="Estimated effort/lines of code if decision is BUILD")


def calculate_formulaic_confidence(
    has_history: bool,
    has_issues: bool,
    has_security: bool,
    llm_delta: float = 0.0,
    is_archived: bool = False
) -> tuple[float, str, List[str]]:
    """Calculative Confidence Engine: Formulaic Base + LLM Qualitative Delta + Hard Caps."""
    base_score = 0.0
    factors = []

    if is_archived:
        base_score = 1.0
        factors.append("+ Official GitHub Repository status is ARCHIVED (read-only mode)")
    else:
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
    if not is_archived and (not has_issues or not has_history):
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
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. AI verdict synthesis service is unavailable."
        )

    diag_status = diagnosis_output.get("status", "MAINTAINED_ACTIVE")
    pkg_name = package_resolution.get("name") or package_resolution.get("package_name") or package_resolution.get("project_name") or "target-package"

    try:
        from google import genai
        from google.genai import types
        from app.core.utils import call_gemini_with_retry

        client = genai.Client(api_key=api_key)

        github_url = package_resolution.get("github_url", "N/A")
        project_name = package_resolution.get("project_name", pkg_name)
        stargazers = package_resolution.get("stargazers_count", 0)
        dependents = package_resolution.get("dependents_count", 0)

        prompt = (
            f"You are the Senior Software Architecture Verdict Agent specialized in open-source dependency evaluation.\n"
            f"TARGET REPOSITORY GROUNDING:\n"
            f"- Ecosystem Registry: '{system}'\n"
            f"- Package Name: '{pkg_name}'\n"
            f"- Resolved Repository: {github_url} ({project_name})\n"
            f"- Repository Stars: {stargazers}\n"
            f"- Downstream Dependent Projects: {dependents}\n"
            f"User Feature Requirement: '{user_requirement or 'General usage'}'\n\n"
            f"EVIDENCE SUMMARY:\n"
            f"- Diagnosis Status: {diag_status}\n"
            f"- Diagnosis Explanation: {diagnosis_output.get('explanation', '')}\n"
            f"- Maintenance Health Score: {forecast_analysis.get('health_score', 50.0)} / 100.0\n"
            f"- 90-Day Trend Direction: {forecast_analysis.get('trend_direction', 'STABLE')}\n"
            f"- Active Unpatched CVEs on Current Release: {security_context.get('active_cves_on_current_version', 0)}\n"
            f"- Recommended Safe Pinned Version: {security_context.get('recommended_pinned_version') or 'None'}\n"
            f"- Historical Patched CVEs: {security_context.get('patched_historical_cves', 0)}\n"
            f"- Transitive Dependencies: {security_context.get('transitive_dependencies', 0)}\n"
            f"- License: {security_context.get('license', 'Unknown')}\n\n"
            f"ARCHITECTURAL DECISION GUIDELINES:\n"
            f"1. SECURITY EVALUATION & SAFE PINNING (BORROW / MIGRATE):\n"
            f"   - Historical patched CVEs with 0 active vulnerabilities on the current release indicate responsible security stewardship; recommend BORROW.\n"
            f"   - If active unpatched vulnerabilities exist on the latest release:\n"
            f"     * If the library is abandoned, archived, or struggling, recommend MIGRATE to a healthy alternative.\n"
            f"     * If the library is actively maintained and a safe pinned version is available in evidence, recommend BORROW with recommended_pinned_version set to that version string. Provide dual advice: pin to that clean version for existing codebases, while suggesting recommended_alternative for fresh projects.\n"
            f"     * If active vulnerabilities exist with no safe compatible pinned version, recommend MIGRATE.\n"
            f"2. TASK COMPLEXITY & UTILITY SCOPE (BUILD):\n"
            f"   - Evaluate whether '{pkg_name}' is a single-function micro-utility or the requested requirement is a trivial task (< 25 lines of code, e.g. scalar clamp, string padding, null check).\n"
            f"   - If so, recommend BUILD with an estimated_build_effort. Acknowledge the library's stability if it is a major package (e.g. numpy, lodash), but recommend building an inline helper to avoid unnecessary binary/dependency bloat unless the project already uses the library broadly.\n"
            f"3. DEPRECATION & SUPERSEDED PACKAGES (MIGRATE):\n"
            f"   - If '{pkg_name}' is deprecated, unmaintained, or superseded by modern industry standards (e.g. passlib -> argon2-cffi, pep8 -> pycodestyle, moment -> dayjs, request -> axios, pycrypto -> pycryptodome), recommend MIGRATE and specify the EXACT published registry package name in recommended_alternative (e.g. 'argon2-cffi' rather than 'argon2', 'pycryptodome' rather than 'pycrypto', 'python-dateutil' rather than 'dateutil', 'dayjs' rather than 'moment').\n"
            f"4. DOMAIN RELEVANCE & ANTI-OVERKILL:\n"
            f"   - If '{pkg_name}' is completely mismatched to the requested requirement (e.g. video rendering engine for web caching), do not recommend BORROW. Recommend BUILD with standard library primitives or specify a domain-appropriate library in recommended_alternative.\n"
            f"5. GENERAL STABILITY (BORROW):\n"
            f"   - If the package is healthy, stable, active, domain-relevant, and the requirement represents non-trivial software functionality, recommend BORROW.\n\n"
            f"OUTPUT REQUIREMENTS:\n"
            f"- Set decision to BORROW, MIGRATE, BUILD, or UNVERIFIED_CANDIDATES.\n"
            f"- Set confidence_score (0.0 to 1.0) and confidence_level (HIGH, MEDIUM, or LOW).\n"
            f"- Provide concise, authoritative reasoning bullet points.\n"
            f"- If BUILD, provide estimated_build_effort (e.g. '15 lines of code, ~10 mins').\n"
            f"- If MIGRATE, set recommended_alternative and recommended_alternative_system.\n"
            f"- If BORROW with version pin, set recommended_pinned_version to the safe release version string."
        )

        response = call_gemini_with_retry(
            client=client,
            prompt=prompt,
            response_schema=VerdictResponse,
            temperature=settings.GEMINI_DEFAULT_TEMPERATURE
        )

        if response.parsed and isinstance(response.parsed, VerdictResponse):
            verdict = response.parsed
            is_archived_flag = "ARCHIVED" in diagnosis_output.get("confidence_reason", "").upper() or "ARCHIVED" in diagnosis_output.get("explanation", "").upper() or bool(diagnosis_output.get("is_archived"))
            
            # Dynamic Qualitative Delta from Gemini (bounded between -0.15 and 0.0)
            raw_llm_score = verdict.confidence_score if verdict.confidence_score is not None else 1.0
            llm_delta = max(-0.15, min(0.0, raw_llm_score - 1.0))

            conf_score, conf_level, conf_factors = calculate_formulaic_confidence(
                has_history=bool(forecast_analysis),
                has_issues=True,
                has_security=bool(security_context),
                llm_delta=llm_delta,
                is_archived=is_archived_flag
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
            raise HTTPException(
                status_code=503,
                detail="Gemini AI verdict synthesis failed to generate a valid structured verdict response."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Verdict Agent call: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"AI verdict generation service failed: {e}"
        )
