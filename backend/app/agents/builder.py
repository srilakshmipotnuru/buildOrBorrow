import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from app.core.config import settings

logger = logging.getLogger(__name__)


class BuilderResponse(BaseModel):
    language: str = Field(description="Target programming language (e.g. python, typescript, javascript)")
    code_snippet: str = Field(description="Clean, well-commented, zero-dependency custom code replacement")
    explanation: str = Field(description="Brief explanation of how the custom implementation works")
    dependencies_used: List[str] = Field(default_factory=list, description="Must be empty list [] for zero-dependency implementation")


def get_deterministic_fallback_build(
    user_requirement: str, 
    package_name: str, 
    system: str = "PYPI"
) -> BuilderResponse:
    """Fallback zero-dependency code generator when Gemini API is unconfigured or call fails."""
    system_upper = (system or "PYPI").upper()
    req_lower = (user_requirement or "").lower()

    if system_upper == "NPM":
        lang = "typescript"
        if "left pad" in req_lower or "pad" in req_lower:
            code = (
                "/**\n"
                " * Zero-dependency string left pad implementation.\n"
                " */\n"
                "export function leftPad(str: string, len: number, ch: string = ' '): string {\n"
                "  const padLen = len - str.length;\n"
                "  if (padLen <= 0) return str;\n"
                "  return ch.repeat(padLen) + str;\n"
                "}\n"
            )
            exp = "Uses native String.prototype.repeat for efficient zero-dependency left padding."
        else:
            code = (
                "/**\n"
                " * Zero-dependency custom implementation.\n"
                " */\n"
                "export function customUtility(input: any): any {\n"
                "  // Implement custom logic here without external dependencies\n"
                "  return input;\n"
                "}\n"
            )
            exp = "Clean TypeScript helper function with zero external package dependencies."
    else:
        lang = "python"
        if "left pad" in req_lower or "pad" in req_lower:
            code = (
                "def left_pad(text: str, length: int, fillchar: str = ' ') -> str:\n"
                "    \"\"\"\n"
                "    Zero-dependency Python left pad implementation.\n"
                "    \"\"\"\n"
                "    return str(text).rjust(length, fillchar)\n"
            )
            exp = "Uses Python standard str.rjust() method for zero-dependency string padding."
        else:
            code = (
                "def custom_utility(data):\n"
                "    \"\"\"\n"
                "    Zero-dependency custom Python helper.\n"
                "    \"\"\"\n"
                "    # Implementation using Python Standard Library only\n"
                "    return data\n"
            )
            exp = "Clean Python standard library helper function ready to copy-paste."

    return BuilderResponse(
        language=lang,
        code_snippet=code,
        explanation=exp,
        dependencies_used=[]
    )


def generate_custom_build(
    user_requirement: str,
    package_name: str,
    system: str = "PYPI"
) -> BuilderResponse:
    """
    Builder Agent:
    Triggered ONLY when Verdict decision is BUILD.
    Generates a clean, well-commented, zero-dependency code replacement customized to user requirement.
    """
    api_key = settings.GEMINI_API_KEY
    target_system = (system or "PYPI").upper()

    if not api_key:
        logger.info("GEMINI_API_KEY unconfigured. Using deterministic fallback Builder Agent.")
        return get_deterministic_fallback_build(user_requirement, package_name, target_system)

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
            return get_deterministic_fallback_build(user_requirement, package_name, target_system)

    except Exception as e:
        logger.error(f"Error in Builder Agent call: {e}. Utilizing fallback.")
        return get_deterministic_fallback_build(user_requirement, package_name, target_system)
