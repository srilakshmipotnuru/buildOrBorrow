import logging
from typing import List, Optional
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


def get_deterministic_fallback_candidates(task_description: str, system: str = "PYPI") -> CandidateFinderResponse:
    """Returns rule-based candidate packages if Gemini API key is unconfigured or call fails."""
    task_lower = task_description.lower()
    system_upper = (system or "PYPI").upper()

    if "rss" in task_lower or "feed" in task_lower:
        if system_upper == "NPM":
            candidates = [
                CandidatePackage(name="rss-parser", system="NPM", reason="Standard Node.js RSS feed parser"),
                CandidatePackage(name="feedparser-promised", system="NPM", reason="Promise-wrapped RSS/Atom parser"),
                CandidatePackage(name="fast-xml-parser", system="NPM", reason="High performance XML/RSS parser")
            ]
        else:
            candidates = [
                CandidatePackage(name="feedparser", system="PYPI", reason="Standard Python RSS and Atom parsing library"),
                CandidatePackage(name="atoma", system="PYPI", reason="Fast Python RSS, Atom and JSON feed parser"),
                CandidatePackage(name="htmldate", system="PYPI", reason="Extracts publication dates from web feeds")
            ]
    elif "http" in task_lower or "request" in task_lower or "api" in task_lower:
        if system_upper == "NPM":
            candidates = [
                CandidatePackage(name="axios", system="NPM", reason="Promise based HTTP client for node.js"),
                CandidatePackage(name="node-fetch", system="NPM", reason="Lightweight window.fetch compatible HTTP client"),
                CandidatePackage(name="got", system="NPM", reason="Human-friendly HTTP request library")
            ]
        else:
            candidates = [
                CandidatePackage(name="requests", system="PYPI", reason="Standard Python HTTP library for human beings"),
                CandidatePackage(name="httpx", system="PYPI", reason="Next-generation HTTP client with async support"),
                CandidatePackage(name="urllib3", system="PYPI", reason="User-friendly HTTP client with connection pooling")
            ]
    else:
        # Default fallback candidates
        if system_upper == "NPM":
            candidates = [
                CandidatePackage(name="lodash", system="NPM", reason="Utility library for JavaScript"),
                CandidatePackage(name="express", system="NPM", reason="Fast, unopinionated web framework"),
                CandidatePackage(name="moment", system="NPM", reason="Date parsing and formatting utility")
            ]
        else:
            candidates = [
                CandidatePackage(name="requests", system="PYPI", reason="Popular HTTP and networking library"),
                CandidatePackage(name="pydantic", system="PYPI", reason="Data validation and settings management"),
                CandidatePackage(name="urllib3", system="PYPI", reason="Low-level HTTP library")
            ]

    return CandidateFinderResponse(confidence_score=0.85, candidates=candidates)


def find_candidate_packages(task_description: str, system: str = "PYPI") -> CandidateFinderResponse:
    """
    Candidate Finder Agent:
    Uses Gemini AI (google-genai) to identify exactly 3 standard, active, modern candidate package names
    in the specified ecosystem (PYPI, NPM, CARGO, GO) for the given task.
    """
    if not task_description or not task_description.strip():
        return get_deterministic_fallback_candidates(task_description="general utility", system=system)

    target_system = (system or "PYPI").upper()
    api_key = settings.GEMINI_API_KEY

    if not api_key:
        logger.info("GEMINI_API_KEY not configured. Using deterministic fallback candidate finder.")
        return get_deterministic_fallback_candidates(task_description=task_description, system=target_system)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"You are an expert software package ecosystem architect.\n"
            f"Task Requirement: '{task_description}'\n"
            f"Target Ecosystem: '{target_system}'\n\n"
            f"Instructions:\n"
            f"1. Identify EXACTLY 3 popular, modern, well-maintained candidate packages in the '{target_system}' ecosystem "
            f"that solve this task.\n"
            f"2. For each package, return its exact package name as published in the '{target_system}' registry, "
            f"its system string ('{target_system}'), and a brief 1-sentence reason.\n"
            f"3. Assign a confidence_score between 0.0 and 1.0 for your candidate selection."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CandidateFinderResponse,
                temperature=0.1
            )
        )

        if response.parsed and isinstance(response.parsed, CandidateFinderResponse):
            logger.info(f"Candidate Finder Agent successfully selected 3 packages for task in {target_system}")
            return response.parsed
        else:
            logger.warning("Gemini did not return structured CandidateFinderResponse. Falling back to rule-based finder.")
            return get_deterministic_fallback_candidates(task_description=task_description, system=target_system)

    except Exception as e:
        logger.error(f"Error in Candidate Finder Agent call: {e}. Utilizing fallback.")
        return get_deterministic_fallback_candidates(task_description=task_description, system=target_system)
