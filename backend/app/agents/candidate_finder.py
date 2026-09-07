import logging
from typing import List, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field
from app.core.config import settings

logger = logging.getLogger(__name__)


class CandidatePackage(BaseModel):
    name: str = Field(description="Package name, e.g. 'feedparser'")
    system: str = Field(description="Ecosystem string: PYPI, NPM, CARGO, GO, MAVEN")
    reason: str = Field(description="Brief reason why this candidate fits the task requirement")


class CandidateFinderResponse(BaseModel):
    confidence_score: float = Field(default=0.90, description="Confidence in candidate selection (0.0 to 1.0)")
    candidates: List[CandidatePackage] = Field(description="Exactly 3 top candidate packages")


def find_candidate_packages(task_description: str, system: str = "PYPI") -> CandidateFinderResponse:
    """
    Candidate Finder Agent:
    Uses Gemini AI (google-genai) to identify exactly 3 standard, active, modern candidate package names
    in the specified ecosystem (PYPI, NPM, CARGO, GO) for the given task.
    Raises HTTP 503 if Gemini AI service is unconfigured or fails.
    """
    if not task_description or not task_description.strip():
        raise HTTPException(status_code=400, detail="Task description cannot be empty.")

    target_system = (system or "PYPI").upper()
    api_key = settings.GEMINI_API_KEY

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI Candidate Finder service is unavailable (GEMINI_API_KEY not configured). Please evaluate by exact package name."
        )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = (
            f"You are an expert software package ecosystem architect and exact registry name resolver.\n"
            f"Task Requirement: '{task_description}'\n"
            f"Target Ecosystem: '{target_system}'\n\n"
            f"Instructions:\n"
            f"1. Identify EXACTLY {settings.CANDIDATE_FINDER_COUNT} popular, modern, well-maintained candidate packages in the '{target_system}' ecosystem that solve this task.\n"
            f"2. For each package, return its EXACT published package name as registered on '{target_system}' (e.g., output 'python-dateutil' rather than 'dateutil', 'argon2-cffi' rather than 'argon2', 'pillow' rather than 'PIL', 'org.springframework.boot:spring-boot' rather than 'springboot', 'github.com/gin-gonic/gin' rather than 'gin').\n"
            f"3. Assign a confidence_score between 0.0 and 1.0 for your candidate selection."
        )

        from app.core.utils import call_gemini_with_retry

        response = call_gemini_with_retry(
            client=client,
            prompt=prompt,
            response_schema=CandidateFinderResponse,
            temperature=settings.GEMINI_DEFAULT_TEMPERATURE
        )

        if response.parsed and isinstance(response.parsed, CandidateFinderResponse):
            logger.info(f"Candidate Finder Agent successfully selected {len(response.parsed.candidates)} packages for task in {target_system}")
            return response.parsed
        else:
            raise HTTPException(
                status_code=502,
                detail=f"Candidate Finder failed to structure packages for task '{task_description}'. Please evaluate by exact package name."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Candidate Finder Agent call ({e}).")
        raise HTTPException(
            status_code=503,
            detail=f"AI Candidate Finder service error ({type(e).__name__}). Please evaluate by exact package name."
        )

