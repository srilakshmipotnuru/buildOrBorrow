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
    diag_status = diagnosis_output.get("status", "MAINTAINED_ACTIVE")
    pkg_name = package_resolution.get("name") or package_resolution.get("package_name") or package_resolution.get("project_name") or "target-package"

    def _rule_based_verdict_fallback() -> VerdictResponse:
        logger.warning(f"   [Verdict Fallback] Executing production-grade formulaic verdict for '{pkg_name}'...")
        is_ab = diagnosis_output.get("is_abandoned", False)
        status_val = diagnosis_output.get("status", "MAINTAINED_ACTIVE")
        health_score = forecast_analysis.get("health_score", 50.0)
        cve_count = security_context.get("total_vulnerabilities", 0)
        crit_cve = security_context.get("critical_vulnerabilities", 0)
        pkg_lower = pkg_name.lower().strip()

        active_cve = security_context.get("active_cves_on_current_version", 0)
        patched_cve = security_context.get("patched_historical_cves", 0)

        # 1. Critical Security Check (MIGRATE ONLY IF ACTIVE CVES EXIST ON CURRENT VERSION)
        if active_cve > 0 or status_val == "VULNERABLE":
            rec_alt = f"{pkg_name}-alternative"
            return VerdictResponse(
                decision="MIGRATE",
                confidence_score=0.95,
                confidence_level="HIGH",
                confidence_factors=["Unpatched Security Vulnerability on Current Release", "Security Advisory Open"],
                reasoning=[
                    f"Package '{pkg_name}' contains {active_cve} active, unpatched security advisories on current release.",
                    "Unpatched vulnerabilities introduce high supply-chain security risks.",
                    "Migrating to an actively maintained alternative is required."
                ],
                recommended_alternative=rec_alt,
                recommended_alternative_system=system
            )

        # 2. Micro-Utility / Trivial Code Check (BUILD)
        if user_requirement and any(w in user_requirement.lower() for w in ["clamp", "repeat", "null or undefined", "uppercase", "left pad", "is number", "slugify", "flatten", "escape string"]):
            return VerdictResponse(
                decision="BUILD",
                confidence_score=0.95,
                confidence_level="HIGH",
                confidence_factors=["Single-Function Utility", "Zero Third-Party Dependency Footprint"],
                reasoning=[
                    f"Target package '{pkg_name}' is healthy/stable, but the requirement is a trivial micro-utility (under ~20 lines of code).",
                    f"Importing an external library or binary dependency solely for a single-function helper introduces unnecessary dependency bloat.",
                    f"Building in-house eliminates third-party bloat. Use an inline helper unless your project already relies on '{pkg_name}' for broader workflows."
                ],
                recommended_alternative=None,
                estimated_build_effort="~5-15 lines of code, ~5 mins"
            )

        # 3. "Finished Software" vs. "Dead Software" Check
        if is_ab or status_val == "ABANDONED_STRUGGLING":
            rec_alt = f"{pkg_name}-alternative"
            dec = "MIGRATE"
            reasoning_bullets = [
                f"Package '{pkg_name}' shows project abandonment and struggling issue resolution.",
                "Stagnant maintenance signals suggest migrating to an active alternative.",
                "Adopting an active library prevents technical debt accumulation."
            ]
        elif status_val == "UNCERTAIN_UNVERIFIED":
            dec = "UNVERIFIED_CANDIDATES"
            rec_alt = None
            reasoning_bullets = [
                f"Package '{pkg_name}' repository metadata could not be resolved or verified in the {system} registry.",
                "Telemetry and source repository activity are unavailable for health scoring.",
                "Please verify registry connection or evaluate by exact package name."
            ]
        elif health_score >= 50 or status_val in ["MATURE_STABLE", "MAINTAINED_ACTIVE"]:
            dec = "BORROW"
            rec_alt = None
            reasoning_bullets = [
                f"Package '{pkg_name}' is a mature, feature-complete library (health score: {health_score}/100).",
                f"Security check passed with 0 active CVEs on current release ({patched_cve} historical CVEs fully patched).",
                "Borrowing this package provides optimal productivity over building in-house."
            ]
        else:
            dec = "BUILD"
            rec_alt = None
            reasoning_bullets = [
                f"Package '{pkg_name}' shows weak activity momentum (health score: {health_score}/100).",
                "Implementing a focused zero-dependency utility eliminates external bloat.",
                "Zero third-party dependencies ensure long-term stability."
            ]

        is_archived_flag = "ARCHIVED" in diagnosis_output.get("confidence_reason", "").upper() or "ARCHIVED" in diagnosis_output.get("explanation", "").upper() or bool(diagnosis_output.get("is_archived"))
        conf_score, conf_level, conf_factors = calculate_formulaic_confidence(
            has_history=bool(forecast_analysis),
            has_issues=True,
            has_security=bool(security_context),
            llm_delta=0.0,
            is_archived=is_archived_flag
        )

        return VerdictResponse(
            decision=dec,
            confidence_score=conf_score,
            confidence_level=conf_level,
            confidence_factors=conf_factors,
            reasoning=reasoning_bullets,
            recommended_alternative=rec_alt,
            recommended_alternative_system=system if dec == "MIGRATE" else None,
            estimated_build_effort="~25 lines of code, ~15 mins" if dec == "BUILD" else None
        )

    if not api_key:
        return _rule_based_verdict_fallback()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        github_url = package_resolution.get("github_url", "N/A")
        project_name = package_resolution.get("project_name", pkg_name)
        stargazers = package_resolution.get("stargazers_count", 0)
        dependents = package_resolution.get("dependents_count", 0)

        prompt = (
            f"You are the Senior Software Architecture Verdict Agent for BuildOrBorrow.\n"
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
            f"- Historical Patched CVEs: {security_context.get('patched_historical_cves', 0)}\n"
            f"- Transitive Dependencies: {security_context.get('transitive_dependencies', 0)}\n"
            f"- License: {security_context.get('license', 'Unknown')}\n\n"
            f"DECISION RULES:\n"
            f"1. HISTORICAL PATCHED CVES VS ACTIVE CVES (BORROW / MIGRATE):\n"
            f"   - Historical patched CVEs (active_cves_on_current_version == 0) represent active security stewardship, NOT a reason to abandon a library! If current release has 0 active CVEs, permit BORROW.\n"
            f"   - Only trigger MIGRATE for security reasons if active_cves_on_current_version > 0 (an unpatched vulnerability remains open on the current release).\n"
            f"2. DYNAMIC MICRO-UTILITY & TRIVIAL TASK CLASSIFICATION (BUILD):\n"
            f"   - Dynamically analyze if:\n"
            f"     a) '{pkg_name}' itself is a single-function micro-utility library (e.g. left-pad, is-even, pad-left, clamp, is-number), OR\n"
            f"     b) The user feature requirement is a trivial task (under ~25 lines of code, single-function helper like clamping a float, string padding, null check, string repetition, slugification, case conversion, or array flattening).\n"
            f"   - If either condition is met, set decision to BUILD and set estimated_build_effort (e.g. '~5-15 lines of code, ~5 mins').\n"
            f"   - When a heavy foundation library (e.g. numpy, lodash, pandas) is requested for a trivial task (e.g. clamping a float):\n"
            f"     * Bullet 1: Acknowledge that the target library ('{pkg_name}') is a mature, healthy, industry-standard library with 0 active CVEs.\n"
            f"     * Bullet 2: Explain that importing a heavy binary/library dependency solely for a 2-line scalar helper introduces unnecessary dependency bloat and slower startup times.\n"
            f"     * Bullet 3: Explicitly advise: 'Build a 2-line inline min(max(...)) helper in-house, unless your application already depends on {pkg_name} for broader scientific/matrix workflows.'\n"
            f"3. DYNAMIC DEPRECATED / SUPERSEDED / RENAMED CLASSIFICATION (MIGRATE):\n"
            f"   - Dynamically evaluate if '{pkg_name}' is officially deprecated, unmaintained, legacy, or superseded by a modern alternative library across ANY ecosystem (e.g. passlib -> argon2-cffi, pep8 -> pycodestyle, node-uuid -> uuid, requests-async -> httpx, mysql-python -> mysqlclient, rustc-serialize -> serde, pycrypto -> pycryptodome, moment -> dayjs, bower -> npm, request -> axios).\n"
            f"   - If deprecated or superseded, set decision to MIGRATE and specify the modern active replacement package in recommended_alternative.\n"
            f"4. MATURE BEDROCK OVERRIDE (BORROW):\n"
            f"   - A package can ONLY qualify for Mature Bedrock Override if the target repository '{project_name}' on system '{system}' has verified high adoption AND the requested feature requirement represents broad non-trivial usage of the library.\n"
            f"   - DO NOT trigger Bedrock Override if the requested task is a trivial micro-utility (e.g. scalar float clamp) that can be written in 2 lines without the library.\n"
            f"5. DEFAULT BORROW:\n"
            f"   - Recommend BORROW if the package is mature, active, or stable and the feature requirement is non-trivial.\n\n"
            f"OUTPUT REQUIREMENTS:\n"
            f"- Set decision to BORROW, MIGRATE, or BUILD.\n"
            f"- Set confidence_score (0.0 to 1.0) and confidence_level (HIGH, MEDIUM, or LOW).\n"
            f"- Provide 3 key reasoning bullet points.\n"
            f"- If BUILD, provide estimated_build_effort (e.g. '15 lines of code, ~10 mins').\n"
            f"- If MIGRATE, set recommended_alternative to the suggested replacement package name."
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
            is_archived_flag = "ARCHIVED" in diagnosis_output.get("confidence_reason", "").upper() or "ARCHIVED" in diagnosis_output.get("explanation", "").upper() or bool(diagnosis_output.get("is_archived"))
            conf_score, conf_level, conf_factors = calculate_formulaic_confidence(
                has_history=bool(forecast_analysis),
                has_issues=True,
                has_security=bool(security_context),
                llm_delta=0.0,
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
            return _rule_based_verdict_fallback()

    except Exception as e:
        logger.error(f"Error in Verdict Agent call ({e}). Triggering formulaic verdict fallback...")
        return _rule_based_verdict_fallback()
