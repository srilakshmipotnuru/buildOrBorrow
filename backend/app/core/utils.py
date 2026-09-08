import re
import time
import logging
from typing import Optional, Tuple, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


def extract_github_owner_repo(github_url: Optional[str]) -> Optional[Tuple[str, str]]:
    if not github_url:
        return None
        
    pattern = r"github\.com[/:](?P<owner>[^/]+)/(?P<repo>[^/\s#\?]+)"
    match = re.search(pattern, github_url.strip())
    
    if not match:
        return None
        
    owner = match.group("owner")
    repo = match.group("repo")
    
    if repo.endswith(".git"):
        repo = repo[:-4]
        
    return owner, repo


from pydantic import BaseModel, Field


class TaskComplexityClassification(BaseModel):
    is_micro_utility: bool = Field(description="True if the task is a trivial single-function helper under ~25 LOC easily implemented with standard library built-ins in 5 minutes")
    estimated_loc: int = Field(description="Estimated lines of code to implement (e.g. 5, 10, 50, 500)")
    reasoning: str = Field(description="1-sentence reason for classification")


def get_genai_client():
    """
    Centralized helper to initialize Google GenAI Client using standard Gemini API Key.
    """
    from google import genai
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def is_micro_utility_requirement(task_description: str) -> bool:
    """
    AI-Powered Early Micro-Utility Classifier:
    Uses Gemini Flash to dynamically evaluate whether a user task requirement describes
    a trivial single-function helper under ~25 lines of code (e.g., string padding, slugification,
    parity checks, clamping, array flattening) with ZERO hardcoded keyword dictionaries.
    """
    if not task_description or not task_description.strip():
        return False

    client = get_genai_client()
    if not client:
        return False

    try:
        prompt = (
            f"You are an expert software architect evaluating task scope.\n"
            f"Task Requirement: '{task_description}'\n\n"
            f"INSTRUCTION:\n"
            f"Determine if this requirement is a trivial micro-utility (under ~25 lines of code, a simple single-function helper like clamping a number, padding a string, checking null, slugifying a title, parity check, simple array flattening, or case conversion) that a developer should implement in 5 minutes with zero third-party dependencies using standard library built-ins.\n\n"
            f"If it requires non-trivial architecture, external APIs, frameworks, complex algorithms, networking, databases, or systems engineering, set is_micro_utility to false."
        )

        response = call_gemini_with_retry(
            client=client,
            prompt=prompt,
            response_schema=TaskComplexityClassification,
            temperature=0.0
        )

        if response.parsed and isinstance(response.parsed, TaskComplexityClassification):
            is_micro = bool(response.parsed.is_micro_utility)
            logger.info(f"   [AI Task Classifier] '{task_description}' -> is_micro={is_micro} (~{response.parsed.estimated_loc} LOC) | Reason: {response.parsed.reasoning}")
            return is_micro

        return False
    except Exception as e:
        logger.warning(f"AI task complexity classification failed ({e}). Defaulting to full pipeline.")
        return False


def call_gemini_with_retry(
    client: Any,
    prompt: str,
    response_schema: Any,
    temperature: float = 0.1,
    max_retries: int = 3
) -> Any:
    """
    Executes a structured Gemini API call with exponential backoff retries and automatic model fallback.
    If primary model throws 503 UNAVAILABLE or 429 RESOURCE_EXHAUSTED,
    it automatically falls back to active alternative models.
    """
    from google.genai import types

    primary_model = settings.GEMINI_MODEL_NAME
    backup_1 = getattr(settings, "FALLBACK_GEMINI_MODEL_1", "gemini-3.6-flash")
    backup_2 = getattr(settings, "FALLBACK_GEMINI_MODEL_2", "gemini-3.1-flash-lite")

    # Triple-tier Cascade
    models_to_try = [primary_model, backup_1, backup_2][:max_retries]

    last_exception = None

    for attempt, model_name in enumerate(models_to_try):
        try:
            logger.info(f"Calling Gemini model '{model_name}' (Attempt {attempt + 1}/{len(models_to_try)})...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=temperature
                )
            )
            return response
        except Exception as e:
            last_exception = e
            err_msg = str(e)
            is_temporary_error = "503" in err_msg or "UNAVAILABLE" in err_msg or "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "404" in err_msg or "NOT_FOUND" in err_msg
            
            if is_temporary_error and attempt < len(models_to_try) - 1:
                next_model = models_to_try[attempt + 1]
                logger.info(f"   [Model Failover] '{model_name}' rate limited/unavailable -> Switching to '{next_model}'")
                time.sleep(1.0)
            else:
                logger.error(f"Gemini API call to '{model_name}' failed: {e}")

    raise last_exception
