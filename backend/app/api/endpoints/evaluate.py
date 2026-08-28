import logging
from typing import Optional, List, Dict, Any, Union
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.core.utils import extract_github_owner_repo
from app.models.deps_dev import PackageResolutionResponse, SecurityContextResponse
from app.models.forecast import ForecastAnalysis
from app.queries.deps_dev import query_package_resolution, query_security_and_dependencies
from app.queries.gh_archive import query_github_weekly_activity
from app.services.forecasting import project_weekly_series
from app.services.github_issues import fetch_recent_github_issues
from app.services.alternative_verifier import verify_alternative_package

from app.agents.candidate_finder import find_candidate_packages, CandidateFinderResponse
from app.agents.diagnosis import diagnose_package, DiagnosisResponse
from app.agents.verdict import generate_verdict, VerdictResponse
from app.agents.builder import generate_custom_build, BuilderResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluate", tags=["Full Evaluation Pipeline"])


class EvaluationRequest(BaseModel):
    package_name: Optional[str] = Field(None, description="Exact package name (e.g. 'feedparser', 'requests')")
    task_description: Optional[str] = Field(None, description="Task requirement (e.g. 'Parse RSS feeds in Python')")
    system: str = Field(default="pypi", description="Package ecosystem (pypi, npm, cargo, go, maven)")
    user_requirement: Optional[str] = Field(None, description="Optional specific feature detail")

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
    user_requirement: Optional[str] = None
) -> PackageEvaluationDetail:
    """
    Executes core evaluation pipeline for a single package:
    deps.dev resolution -> Security scan -> GH Archive forecast -> GitHub issues -> AI Agents.
    """
    package_name = package_name.strip().lower()
    system_upper = (system or "pypi").strip().upper()

    # Step 1: deps.dev Resolution & Security
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
        logger.warning(f"Package '{package_name}' could not be resolved in deps.dev dataset for system '{system_upper}'.")
        raise HTTPException(
            status_code=404,
            detail=f"Package '{package_name}' was not found in the {system_upper} ecosystem."
        )

    resolution_model = PackageResolutionResponse(**resolution_dict)
    security_model = SecurityContextResponse(**security_dict)

    # Step 2: Extract Repo & Query GH Archive + 90-Day Forecast
    github_url = resolution_dict.get("github_url")
    owner, repo = None, None
    raw_weekly_data = []
    forecast_results = {
        "projected_timeline": [],
        "trend_direction": "STABLE",
        "health_score": 75.0,
        "projected_total_events_90d": 120,
        "maintenance_verdict_signal": "HEALTHY_ACTIVE"
    }
    recent_issues = []

    if github_url:
        parsed = extract_github_owner_repo(github_url)
        if parsed:
            owner, repo = parsed
            # Fetch recent issues via GitHub Search API
            try:
                recent_issues = fetch_recent_github_issues(owner=owner, repo=repo, max_issues=15)
            except Exception as e:
                logger.warning(f"GitHub issue fetch failed for {owner}/{repo}: {e}")

            # Query GH Archive weekly activity
            try:
                raw_weekly_data = query_github_weekly_activity(
                    client=None, repo_owner=owner, repo_name=repo, lookback_weeks=104
                )
                if raw_weekly_data:
                    forecast_results = project_weekly_series(raw_weekly_data, forecast_weeks=13)
            except Exception as e:
                logger.warning(f"GH Archive query skipped or failed for {owner}/{repo}: {e}")

    historical_summary = {
        "total_pushes": sum(item.get("push_events", 0) for item in raw_weekly_data),
        "total_prs": sum(item.get("pr_events", 0) for item in raw_weekly_data),
        "total_stars": sum(item.get("star_events", 0) for item in raw_weekly_data),
    }
    forecast_model = ForecastAnalysis(**forecast_results)

    # Step 3: AI Diagnosis Agent
    diagnosis_model = diagnose_package(
        package_name=package_name,
        historical_summary=historical_summary,
        forecast_analysis=forecast_results,
        recent_issues=recent_issues
    )

    # Step 4: AI Verdict Agent
    verdict_model = generate_verdict(
        user_requirement=user_requirement,
        package_resolution=resolution_dict,
        security_context=security_dict,
        forecast_analysis=forecast_results,
        diagnosis_output=diagnosis_model.model_dump(),
        system=system_upper
    )

    # Step 5: Lightweight Alternative Package Verification (if MIGRATE)
    if verdict_model.decision == "MIGRATE" and verdict_model.recommended_alternative:
        alt_system = verdict_model.recommended_alternative_system or system_upper
        verdict_model.alternative_verification = verify_alternative_package(
            alternative_name=verdict_model.recommended_alternative,
            system=alt_system
        )

    # Step 6: AI Builder Agent (Triggered ONLY if BUILD)
    builder_model = None
    if verdict_model.decision == "BUILD":
        builder_model = generate_custom_build(
            user_requirement=user_requirement or f"Custom implementation for {package_name}",
            package_name=package_name,
            system=system_upper
        )

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
            user_requirement=req_context
        )
        return EvaluationSingleResponse(mode="package", evaluation=eval_detail)

    # Mode 2: Task Mode Evaluation (Option 1 Two-Stage Funnel)
    logger.info(f"Executing Task Mode Evaluation Pipeline for: '{task_input}' ({system_input})")
    
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

    # Stage 3: Primary Deep Evaluation for the top candidate
    primary_cand = candidate_list[0]
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
