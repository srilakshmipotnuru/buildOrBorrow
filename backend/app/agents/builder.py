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

    if not api_key:
        logger.error("GEMINI_API_KEY unconfigured. Unable to execute Builder Agent.")
        raise HTTPException(
            status_code=503,
            detail="Gemini AI service unavailable: GEMINI_API_KEY is not configured on the server."
        )

    lang = "typescript" if target_system == "NPM" else "python"

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"You are the Builder Agent for BuildOrBorrow.\n"
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

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BuilderResponse,
                temperature=0.2
            )
        )

        if response.parsed and isinstance(response.parsed, BuilderResponse):
            builder_res = response.parsed
            builder_res.dependencies_used = []  # Force zero-dependency guarantee
            logger.info(f"Builder Agent generated zero-dependency code snippet for {package_name}")
            return builder_res
        else:
            raise HTTPException(
                status_code=503,
                detail="Builder Agent failed to parse structured output from Gemini AI."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Builder Agent call: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Builder Agent call failed: {str(e)}"
        )

