import logging
from typing import List, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field
from app.core.config import settings

logger = logging.getLogger(__name__)


class BuilderResponse(BaseModel):
    language: str = Field(description="Target programming language (e.g. python, typescript, javascript)")
    code_snippet: str = Field(description="Clean, well-commented, zero-dependency custom code replacement")
    explanation: str = Field(description="Brief explanation of how the custom implementation works")
    dependencies_used: List[str] = Field(default_factory=list, description="Must be empty list [] for zero-dependency implementation")


def generate_custom_build(
    user_requirement: str,
    package_name: str,
    system: str = "PYPI"
) -> BuilderResponse:
    """
    Builder Agent:
    Triggered ONLY when Verdict decision is BUILD.
    Generates a clean, well-commented, zero-dependency code replacement customized to user requirement.
    Raises HTTP 503 if Gemini AI service is unconfigured or fails.
    """
    api_key = settings.GEMINI_API_KEY
    target_system = (system or "PYPI").upper()
    SYSTEM_LANGUAGE_MAP = {
        "NPM": "typescript",
        "CARGO": "rust",
        "GO": "go",
        "MAVEN": "java",
        "PYPI": "python"
    }
    lang = SYSTEM_LANGUAGE_MAP.get(target_system, "python")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI Builder service is unavailable (GEMINI_API_KEY not configured)."
        )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = (
            f"You are the Senior Software Engineer Builder Agent specialized in implementing zero-dependency utilities.\n"
            f"User Requirement: '{user_requirement}'\n"
            f"Package Being Replaced: '{package_name}'\n"
            f"Target Ecosystem: '{target_system}' (Language: '{lang}')\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Generate a clean, well-commented, production-ready code snippet in '{lang}' that implements "
            f"   the user's specific feature requirement.\n"
            f"2. MUST BE ZERO-DEPENDENCY! Do NOT use third-party libraries (only Standard Library features).\n"
            f"3. dependencies_used array MUST be empty [].\n"
            f"4. Provide a brief explanation of how the code works."
        )

        from app.core.utils import call_gemini_with_retry

        response = call_gemini_with_retry(
            client=client,
            prompt=prompt,
            response_schema=BuilderResponse,
            temperature=settings.GEMINI_BUILDER_TEMPERATURE
        )

        if response.parsed and isinstance(response.parsed, BuilderResponse):
            builder_res = response.parsed
            builder_res.dependencies_used = []  # Force zero-dependency guarantee
            logger.info(f"Builder Agent generated zero-dependency code snippet for {package_name} ({lang})")
            return builder_res
        else:
            raise HTTPException(
                status_code=502,
                detail=f"Builder Agent failed to parse code snippet for '{package_name}'."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Builder Agent call ({e}).")
        raise HTTPException(
            status_code=503,
            detail=f"AI Builder service error ({type(e).__name__})."
        )

