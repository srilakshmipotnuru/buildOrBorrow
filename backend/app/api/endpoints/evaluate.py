import logging
from typing import Optional, List, Dict, Any, Union
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.core.utils import extract_github_owner_repo, is_micro_utility_requirement
from app.core.bigquery import get_bigquery_client
from app.core.config import settings
from app.models.deps_dev import PackageResolutionResponse, SecurityContextResponse
from app.models.forecast import ForecastAnalysis
from app.queries.deps_dev import query_package_resolution, query_security_and_dependencies
from app.queries.gh_archive import query_github_weekly_activity, query_arima_plus_forecast
from app.services.forecasting import project_weekly_series
from app.services.github_issues import fetch_recent_github_issues
from app.services.alternative_verifier import verify_alternative_package

from app.agents.candidate_finder import find_candidate_packages, CandidateFinderResponse
from app.agents.diagnosis import diagnose_package, DiagnosisResponse
from app.agents.verdict import generate_verdict, VerdictResponse, AlternativeVerification
from app.agents.builder import generate_custom_build, BuilderResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluate", tags=["Full Evaluation Pipeline"])


class EvaluationRequest(BaseModel):
    package_name: Optional[str] = Field(None, description="Exact package name (e.g. 'feedparser', 'requests')")
    task_description: Optional[str] = Field(None, description="Task requirement (e.g. 'Parse RSS feeds in Python')")
    system: str = Field(default="pypi", description="Package ecosystem (pypi, npm, cargo, go, maven)")
    user_requirement: Optional[str] = Field(None, description="Optional specific feature detail")
    cached_github_url: Optional[str] = Field(None, description="Optional pre-screened GitHub repository URL for query reuse")

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        pkg = (self.package_name or "").strip()
        task = (self.task_description or "").strip()
        if not pkg and not task:
            raise ValueError("Either 'package_name' or 'task_description' must be provided.")
        return self


class PackageEvaluationDetail(BaseModel):
    package_name: str
    system: str
    github_url: Optional[str] = None
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    resolution: Optional[PackageResolutionResponse] = None
    security: Optional[SecurityContextResponse] = None
    forecast: Optional[ForecastAnalysis] = None
    recent_issues: List[Dict[str, Any]] = Field(default_factory=list)
    diagnosis: DiagnosisResponse
    verdict: VerdictResponse
    builder: Optional[BuilderResponse] = None


class CandidateScreeningItem(BaseModel):
    name: str
    system: str
    reason: str
    version: Optional[str] = None
    github_url: Optional[str] = None
    licenses: List[str] = Field(default_factory=list)
    verified_exists: bool = True


class EvaluationTaskResponse(BaseModel):
    mode: str = "task"
    task_description: str
    system: str
    primary_evaluation: PackageEvaluationDetail
    candidate_screenings: List[CandidateScreeningItem]


class EvaluationSingleResponse(BaseModel):
    mode: str = "package"
    evaluation: PackageEvaluationDetail


def evaluate_single_package_pipeline(
    package_name: str,
    system: str = "pypi",
    user_requirement: Optional[str] = None,
    cached_github_url: Optional[str] = None
) -> PackageEvaluationDetail:
    """
    Executes core evaluation pipeline for a single package:
    deps.dev resolution -> Security scan -> GH Archive forecast -> GitHub issues -> AI Agents.
    """
    import time
    start_time = time.time()
    package_name = package_name.strip().lower()
    system_upper = (system or "pypi").strip().upper()

    logger.info("=" * 80)
    logger.info(f"🚀 [BUILDORBORROW] Starting Evaluation Pipeline")
    logger.info(f"   Target Package : '{package_name}' ({system_upper})")
    if user_requirement:
        logger.info(f"   Requirement    : '{user_requirement}'")
    if cached_github_url:
        logger.info(f"   Cached Repo URL: '{cached_github_url}' (Fast-Path Query Reuse)")
    logger.info("=" * 80)

    # Step 1: deps.dev Resolution & Security
    logger.info("📦 [STEP 1/6] Querying deps.dev Package Resolution & Security Advisories...")
    resolution_dict = None
    security_dict = {
        "critical_vulnerabilities": 0, "high_vulnerabilities": 0, "medium_vulnerabilities": 0,
        "low_vulnerabilities": 0, "unknown_vulnerabilities": 0, "total_vulnerabilities": 0,
        "direct_dependencies": None, "transitive_dependencies": 0, "license": "MIT"
    }

    try:
        resolution_dict = query_package_resolution(package_name=package_name, system=system_upper)
        if resolution_dict:
            system_upper = resolution_dict.get("system", system_upper)
            sec_res = query_security_and_dependencies(
                package_name=package_name,
                system=system_upper,
                version=resolution_dict.get("version")
            )
            if sec_res:
                security_dict.update(sec_res)
    except Exception as e:
        logger.warning(f"deps.dev query skipped or failed for '{package_name}': {e}")

    if not resolution_dict:
        logger.warning(f"⚠️ Package '{package_name}' could not be resolved in deps.dev dataset. Creating standard fallback resolution entry.")
        resolution_dict = {
            "name": package_name,
            "system": system_upper,
            "version": "1.0.0",
            "project_name": package_name,
            "licenses": [],
            "github_url": cached_github_url,
            "published_at": None
        }

    if cached_github_url and not resolution_dict.get("github_url"):
        resolution_dict["github_url"] = cached_github_url


    resolution_model = PackageResolutionResponse(**resolution_dict)
    security_model = SecurityContextResponse(**security_dict)

    logger.info(f"   ✔ Package Resolved : {resolution_dict.get('name')} v{resolution_dict.get('version')} (Project: {resolution_dict.get('project_name')})")
    logger.info(f"   ✔ Security Check   : {security_dict.get('critical_vulnerabilities')} Critical, {security_dict.get('high_vulnerabilities')} High CVEs | {security_dict.get('transitive_dependencies')} Transitive Deps")

    # Step 2: Extract Repo & Query GH Archive + 90-Day Forecast
    logger.info("📊 [STEP 2/6] Querying GH Archive Weekly Activity & 90-Day Forecast...")
    github_url = resolution_dict.get("github_url")
    owner, repo = None, None
    raw_weekly_data = []
    forecast_results = {
        "projected_timeline": [],
        "trend_direction": "UNAVAILABLE",
        "health_score": 0.0,
        "projected_total_events_90d": 0,
        "maintenance_verdict_signal": "UNAVAILABLE"
    }
    recent_issues = []
    readme_context = {}

    if github_url:
        parsed = extract_github_owner_repo(github_url)
        if parsed:
            owner, repo = parsed
            # Fetch recent issues, README summary, and repo metadata via GitHub REST API
            logger.info("🐛 [STEP 3/6] Retrieving Recent GitHub Issues, Repository Metadata & README Deprecation Summary...")
            try:
                from app.services.github_issues import fetch_github_readme_summary, fetch_github_repo_metadata
                recent_issues = fetch_recent_github_issues(owner=owner, repo=repo, max_issues=settings.GITHUB_ISSUES_MAX_COUNT)
                readme_context = fetch_github_readme_summary(owner=owner, repo=repo)
                repo_meta = fetch_github_repo_metadata(owner=owner, repo=repo)
                if repo_meta.get("is_archived"):
                    readme_context["is_archived"] = True
                    logger.warning(f"   ⚠️ GitHub Platform Notice: Repository {owner}/{repo} is officially ARCHIVED (read-only mode).")
                logger.info(f"   ✔ GitHub Issues    : Fetched {len(recent_issues)} recent open issues for {owner}/{repo}")
                if readme_context.get("is_deprecated_in_readme"):
                    logger.warning(f"   ⚠️ GitHub README Warning: Deprecation/renaming keywords detected in README for {owner}/{repo}")
            except Exception as e:
                logger.warning(f"GitHub issue/README/metadata fetch failed for {owner}/{repo}: {e}")

            # Query GH Archive weekly activity from custom warehouse
            try:
                raw_weekly_data = query_github_weekly_activity(
                    client=get_bigquery_client(), repo_owner=owner, repo_name=repo, lookback_weeks=settings.DEFAULT_LOOKBACK_WEEKS
                )
                if raw_weekly_data:
                    # Item 1: Zero-Activity Guard
                    total_maintenance_events = sum(item.get("total_events", 0) for item in raw_weekly_data)
                    if total_maintenance_events == 0:
                        logger.info(f"   [Zero Activity] {owner}/{repo} has 0 events across 104 weeks. Bypassing ARIMA fitting.")
                        forecast_results = {
                            "projected_timeline": [],
                            "trend_direction": "DECLINING",
                            "health_score": 0.0,
                            "projected_total_events_90d": 0,
                            "maintenance_verdict_signal": "AT_RISK_STAGNANT"
                        }
                    else:
                        # Primary Engine: Real BigQuery ML ARIMA_PLUS
                        if getattr(settings, "ENABLE_BQ_ML_ARIMA", True):
                            try:
                                arima_timeline = query_arima_plus_forecast(
                                    client=get_bigquery_client(),
                                    repo_owner=owner,
                                    repo_name=repo,
                                    lookback_weeks=settings.DEFAULT_LOOKBACK_WEEKS,
                                    forecast_weeks=settings.DEFAULT_FORECAST_WEEKS,
                                    weekly_history=raw_weekly_data
                                )
                                if arima_timeline:
                                    projected_total = sum(p.get("projected_events", 0) for p in arima_timeline)
                                    slope = (arima_timeline[-1]["projected_events"] - arima_timeline[0]["projected_events"]) / len(arima_timeline) if len(arima_timeline) > 1 else 0
                                    trend = "ACCELERATING" if slope > 0.5 else ("DECLINING" if slope < -0.5 else "STABLE")
                                    health_score = min(100.0, max(0.0, (projected_total / settings.DEFAULT_FORECAST_WEEKS) * 8.0 + (30.0 if trend == "ACCELERATING" else 15.0)))
                                    signal = "HEALTHY_ACTIVE" if health_score >= 60 else ("SLOW_MAINTENANCE" if health_score >= 30 else "AT_RISK_STAGNANT")
                                    forecast_results = {
                                        "projected_timeline": arima_timeline,
                                        "trend_direction": trend,
                                        "health_score": round(health_score, 1),
                                        "projected_total_events_90d": projected_total,
                                        "maintenance_verdict_signal": signal
                                    }
                                    logger.info(f"   ✔ BQ ML ARIMA_PLUS : Generated 90-day forecast for {owner}/{repo} (Trend: {trend}, Health: {health_score}/100)")
                            except Exception as arima_err:
                                logger.warning(f"BigQuery ML ARIMA_PLUS forecast failed ({arima_err}). Falling back to statistical series.")

                        # Backup Engine: Statistical series forecasting in Python
                        if not forecast_results:
                            forecast_results = project_weekly_series(raw_weekly_data, forecast_weeks=settings.DEFAULT_FORECAST_WEEKS)
                            logger.info(f"   ✔ Statistical Fallback : Trend {forecast_results.get('trend_direction')} | Health Score: {forecast_results.get('health_score')}/100")

                    logger.info(f"   ✔ GH Warehouse Scan: Analyzed {len(raw_weekly_data)} weeks of activity for {owner}/{repo}")
            except Exception as e:
                logger.warning(f"GH Warehouse query skipped or failed for {owner}/{repo}: {e}")

    historical_summary = {
        "data_retrieved": bool(raw_weekly_data),
        "total_pushes": sum(item.get("push_events", 0) for item in raw_weekly_data) if raw_weekly_data else "UNAVAILABLE",
        "total_prs": sum(item.get("pr_events", 0) for item in raw_weekly_data) if raw_weekly_data else "UNAVAILABLE",
        "total_stars": sum(item.get("star_events", 0) for item in raw_weekly_data) if raw_weekly_data else "UNAVAILABLE",
    }
    forecast_model = ForecastAnalysis(**forecast_results)

    # Step 4: AI Diagnosis Agent
    logger.info("🔬 [STEP 4/6] Executing AI Diagnosis Agent...")
    diagnosis_model = diagnose_package(
        package_name=package_name,
        historical_summary=historical_summary,
        forecast_analysis=forecast_results,
        recent_issues=recent_issues,
        readme_context=readme_context,
        security_context=security_dict,
        package_resolution=resolution_dict
    )
    logger.info(f"   ✔ Diagnosis Result : Status '{diagnosis_model.status}' (Abandoned: {diagnosis_model.is_abandoned})")

    # Step 5: AI Verdict Agent
    logger.info("⚖️ [STEP 5/6] Executing AI Verdict Agent & Confidence Engine...")
    verdict_model = generate_verdict(
        user_requirement=user_requirement,
        package_resolution=resolution_dict,
        security_context=security_dict,
        forecast_analysis=forecast_results,
        diagnosis_output=diagnosis_model.model_dump(),
        system=system_upper
    )
    logger.info(f"   ✔ Architectural Verdict : {verdict_model.decision} (Confidence: {verdict_model.confidence_score} - {verdict_model.confidence_level})")

    # Step 6: Lightweight Alternative Package Verification (if MIGRATE)
    if verdict_model.decision == "MIGRATE" and verdict_model.recommended_alternative:
        logger.info(f"🔍 [STEP 6/6] Verifying Recommended Alternative Package '{verdict_model.recommended_alternative}'...")
        alt_system = verdict_model.recommended_alternative_system or system_upper
        alt_res = verify_alternative_package(
            alternative_name=verdict_model.recommended_alternative,
            system=alt_system
        )
        if alt_res:
            verdict_model.alternative_verification = AlternativeVerification(**alt_res)
            logger.info(f"   ✔ Alternative Verified  : '{alt_res.get('name')}' (Exists: {alt_res.get('verified_exists')})")

    # Step 7: AI Builder Agent (Triggered ONLY if BUILD)
    builder_model = None
    if verdict_model.decision == "BUILD":
        logger.info(f"🛠️ [STEP 6/6] Executing AI Builder Agent (Generating Zero-Dep Code Replacement)...")
        builder_model = generate_custom_build(
            user_requirement=user_requirement or f"Custom implementation for {package_name}",
            package_name=package_name,
            system=system_upper
        )
        logger.info(f"   ✔ Code Generation Completed ({builder_model.language})")

    elapsed_sec = round(time.time() - start_time, 2)
    logger.info("=" * 80)
    logger.info(f"✨ [BUILDORBORROW] Pipeline Completed Successfully in {elapsed_sec}s")
    logger.info("=" * 80)

    return PackageEvaluationDetail(
        package_name=package_name,
        system=system_upper,
        github_url=github_url,
        repo_owner=owner,
        repo_name=repo,
        resolution=resolution_model,
        security=security_model,
        forecast=forecast_model,
        recent_issues=recent_issues,
        diagnosis=diagnosis_model,
        verdict=verdict_model,
        builder=builder_model
    )


@router.post("", response_model=Union[EvaluationSingleResponse, EvaluationTaskResponse])
def evaluate_pipeline(request: EvaluationRequest):
    """
    Main Full Evaluation Pipeline Endpoint (POST /api/evaluate).
    Supports:
    1. Single Package Mode: 'package_name' provided.
    2. Option 1 Task Mode: 'task_description' provided (Candidate Finder -> Screening -> Deep Primary Evaluation).
    """
    pkg_input = (request.package_name or "").strip()
    task_input = (request.task_description or "").strip()
    system_input = (request.system or "pypi").strip().upper()
    req_context = request.user_requirement or task_input

    # Mode 1: Single Package Evaluation
    if pkg_input:
        logger.info(f"Executing Single Package Evaluation Pipeline for: {pkg_input} ({system_input})")
        eval_detail = evaluate_single_package_pipeline(
            package_name=pkg_input,
            system=system_input,
            user_requirement=req_context,
            cached_github_url=request.cached_github_url
        )
        return EvaluationSingleResponse(mode="package", evaluation=eval_detail)

    # Mode 2: Task Mode Evaluation (Option 1 Two-Stage Funnel)
    logger.info(f"Executing Task Mode Evaluation Pipeline for: '{task_input}' ({system_input})")
    
    # Early Fast-Path Bypass for Micro-Utilities (< 25 LOC)
    if is_micro_utility_requirement(task_input):
        logger.info(f"⚡ [Fast-Path Bypass] Detected micro-utility task requirement (< 25 LOC): '{task_input}'. Bypassing BigQuery scans.")
        
        builder_res = generate_custom_build(
            user_requirement=task_input,
            package_name=task_input,
            system=system_input
        )
        
        fast_path_eval = PackageEvaluationDetail(
            package_name=task_input,
            system=system_input,
            github_url=None,
            repo_owner=None,
            repo_name=None,
            resolution=None,
            security=SecurityContextResponse(
                critical_vulnerabilities=0,
                high_vulnerabilities=0,
                medium_vulnerabilities=0,
                low_vulnerabilities=0,
                unknown_vulnerabilities=0,
                total_vulnerabilities=0,
                direct_dependencies=0,
                transitive_dependencies=0,
                license="Zero External Dependencies",
                is_current_version_vulnerable=False
            ),
            forecast=ForecastAnalysis(
                projected_timeline=[],
                trend_direction="NOT_APPLICABLE",
                health_score=100.0,
                projected_total_events_90d=0,
                maintenance_verdict_signal="IN_HOUSE_BUILD"
            ),
            recent_issues=[],
            diagnosis=DiagnosisResponse(
                status="MAINTAINED_ACTIVE",
                is_abandoned=False,
                confidence_score=1.0,
                confidence_reason="Single-function micro-utility requirement (< 25 LOC). In-house zero-dependency code generated.",
                bug_severity_assessment="Zero third-party open issue dependency footprint.",
                explanation=f"Task requirement '{task_input}' is a lightweight micro-utility (under ~25 lines of code). Building in-house eliminates external supply-chain dependency bloat and vulnerability exposure."
            ),
            verdict=VerdictResponse(
                decision="BUILD",
                confidence_score=1.0,
                confidence_level="HIGH",
                confidence_factors=["Single-Function Micro-Utility (< 25 LOC)", "Zero Third-Party Dependency Footprint", "Bypassed BigQuery ML & Heavy Registry Queries"],
                reasoning=[
                    f"Feature requirement '{task_input}' is a lightweight single-function utility (< 25 lines of code).",
                    "Building directly in-house avoids third-party dependency bloat, transitive dependencies, and supply-chain vulnerability risks.",
                    "Zero external dependencies guarantee maximum execution performance and complete codebase control."
                ],
                recommended_alternative=None,
                estimated_build_effort="~5-15 lines of code, ~5 mins"
            ),
            builder=builder_res
        )

        return EvaluationTaskResponse(
            mode="task",
            task_description=task_input,
            system=system_input,
            primary_evaluation=fast_path_eval,
            candidate_screenings=[]
        )

    # Stage 1: Candidate Finder Agent returns 3 candidates with ecosystems
    candidates_res = find_candidate_packages(task_description=task_input, system=system_input)
    candidate_list = candidates_res.candidates

    if not candidate_list:
        raise HTTPException(status_code=404, detail="Could not identify candidate packages for the given task.")

    # Stage 2: Lightweight deps.dev screening for all 3 candidates
    screenings = []
    for cand in candidate_list:
        ver = verify_alternative_package(alternative_name=cand.name, system=cand.system)
        screenings.append(CandidateScreeningItem(
            name=cand.name,
            system=cand.system,
            reason=cand.reason,
            version=ver.get("version") if ver else None,
            github_url=ver.get("github_url") if ver else None,
            licenses=ver.get("licenses", []) if ver else [],
            verified_exists=ver.get("verified_exists", True) if ver else True
        ))

    # Stage 3: Primary Deep Evaluation for the top candidate (selects first candidate that passed deps.dev verification)
    verified_candidates = [
        cand for cand, screen in zip(candidate_list, screenings)
        if screen.verified_exists
    ]

    if not verified_candidates:
        logger.warning(f"None of the suggested candidates for task '{task_input}' were verified in {system_input} registry.")
        
        # Task Scale Guard: Distinguish Micro-Tasks from Complex Tasks
        if is_micro_utility_requirement(task_input):
            logger.info(f"⚡ [Task Scale Guard] Unverified candidates for micro-utility task '{task_input}'. Issuing BUILD verdict.")
            builder_res = generate_custom_build(
                user_requirement=task_input,
                package_name=task_input,
                system=system_input
            )
            unverified_eval = PackageEvaluationDetail(
                package_name=task_input,
                system=system_input,
                github_url=None,
                repo_owner=None,
                repo_name=None,
                resolution=None,
                security=SecurityContextResponse(
                    critical_vulnerabilities=0,
                    high_vulnerabilities=0,
                    medium_vulnerabilities=0,
                    low_vulnerabilities=0,
                    unknown_vulnerabilities=0,
                    total_vulnerabilities=0,
                    direct_dependencies=0,
                    transitive_dependencies=0,
                    license="Zero External Dependencies",
                    is_current_version_vulnerable=False
                ),
                forecast=ForecastAnalysis(
                    projected_timeline=[],
                    trend_direction="UNAVAILABLE",
                    health_score=0.0,
                    projected_total_events_90d=0,
                    maintenance_verdict_signal="UNAVAILABLE"
                ),
                recent_issues=[],
                diagnosis=DiagnosisResponse(
                    status="UNCERTAIN_UNVERIFIED",
                    is_abandoned=False,
                    confidence_score=0.5,
                    confidence_reason="Candidate packages could not be verified in registry. Micro-utility requirement detected.",
                    bug_severity_assessment="No verified registry telemetry.",
                    explanation=f"Suggested candidate packages were unverified in the {system_input} registry. Because '{task_input}' is a lightweight micro-utility, building an in-house zero-dependency helper is recommended."
                ),
                verdict=VerdictResponse(
                    decision="BUILD",
                    confidence_score=0.9,
                    confidence_level="HIGH",
                    confidence_factors=["Unverified Registry Candidates", "Single-Function Micro-Utility (< 25 LOC)", "Zero Third-Party Dependency Footprint"],
                    reasoning=[
                        f"Could not verify suggested candidate packages in the {system_input} registry for '{task_input}'.",
                        "Because this requirement is a lightweight micro-utility (< 25 lines of code), building directly in-house avoids third-party dependency bloat.",
                        "Zero external dependencies guarantee maximum performance and codebase security."
                    ],
                    recommended_alternative=None,
                    estimated_build_effort="~5-15 lines of code, ~5 mins"
                ),
                builder=builder_res
            )
        else:
            logger.warning(f"⚠️ [Task Scale Guard] Complex task requirement '{task_input}' has 0 verified candidate packages. Issuing UNVERIFIED_CANDIDATES notice.")
            unverified_eval = PackageEvaluationDetail(
                package_name=f"unverified-{system_input.lower()}-candidates",
                system=system_input,
                github_url=None,
                repo_owner=None,
                repo_name=None,
                resolution=PackageResolutionResponse(
                    name=f"unverified-{system_input.lower()}-candidates",
                    system=system_input,
                    version="0.0.0",
                    project_name=f"unverified-{system_input.lower()}-candidates",
                    licenses=[],
                    github_url=None,
                    published_at=None
                ),
                security=SecurityContextResponse(
                    critical_vulnerabilities=0,
                    high_vulnerabilities=0,
                    medium_vulnerabilities=0,
                    low_vulnerabilities=0,
                    unknown_vulnerabilities=0,
                    total_vulnerabilities=0,
                    direct_dependencies=0,
                    transitive_dependencies=0,
                    license="Unknown",
                    is_current_version_vulnerable=False
                ),
                forecast=ForecastAnalysis(
                    projected_timeline=[],
                    trend_direction="UNAVAILABLE",
                    health_score=0.0,
                    projected_total_events_90d=0,
                    maintenance_verdict_signal="UNAVAILABLE"
                ),
                recent_issues=[],
                diagnosis=DiagnosisResponse(
                    status="UNCERTAIN_UNVERIFIED",
                    is_abandoned=False,
                    confidence_score=0.0,
                    confidence_reason="None of the suggested candidate packages were found in ecosystem package resolution table.",
                    bug_severity_assessment="Telemetry unavailable.",
                    explanation=f"Could not verify candidate packages in the {system_input} registry for requirement '{task_input}'."
                ),
                verdict=VerdictResponse(
                    decision="UNVERIFIED_CANDIDATES",
                    confidence_score=0.0,
                    confidence_level="LOW",
                    confidence_factors=["Unverified Registry Candidates", "High Architectural Task Complexity"],
                    reasoning=[
                        f"Could not verify candidate packages in the {system_input} registry for this requirement.",
                        "Because this task requires significant architectural complexity, building a custom implementation from scratch is non-trivial.",
                        "Please verify registry connection or evaluate by exact package name."
                    ],
                    recommended_alternative=None
                ),
                builder=None
            )
        
        return EvaluationTaskResponse(
            mode="task",
            task_description=task_input,
            system=system_input,
            primary_evaluation=unverified_eval,
            candidate_screenings=screenings
        )

    primary_cand = verified_candidates[0]

    logger.info(f"Selected primary candidate '{primary_cand.name}' ({primary_cand.system}) for deep evaluation.")

    primary_eval = evaluate_single_package_pipeline(
        package_name=primary_cand.name,
        system=primary_cand.system,
        user_requirement=task_input
    )

    return EvaluationTaskResponse(
        mode="task",
        task_description=task_input,
        system=system_input,
        primary_evaluation=primary_eval,
        candidate_screenings=screenings
    )
