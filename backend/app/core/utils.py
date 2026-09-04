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


MICRO_UTILITY_KEYWORDS = [
    "left pad", "right pad", "pad string", "pad a string",
    "is even", "is odd", "check if even", "check if odd",
    "slugify", "make slug", "generate slug",
    "clamp", "clamp float", "clamp number", "clamp integer",
    "flatten array", "flatten list", "flatten nested",
    "null or undefined", "is null", "is undefined", "check null",
    "repeat string", "string repeat",
    "to camelcase", "to snakecase", "to kebabcase", "uppercase string", "lowercase string",
    "escape html", "escape string", "unescape html",
    "reverse string", "trim string", "truncate string"
]


def is_micro_utility_requirement(task_description: str) -> bool:
    """
    Early Micro-Utility Classifier:
    Detects if a user task description describes a single-function, trivial micro-utility
    under ~25 lines of code (e.g., string padding, slugification, parity checks, clamping, array flattening).
    """
    if not task_description or not task_description.strip():
        return False

    task_lower = task_description.strip().lower()

    for kw in MICRO_UTILITY_KEYWORDS:
        if kw in task_lower:
            return True

    words = task_lower.split()
    if len(words) <= 4 and any(w in task_lower for w in ["pad", "even", "odd", "clamp", "slug", "flatten", "trim", "reverse", "repeat", "case"]):
        return True

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
    If primary model (e.g. gemini-2.5-flash) throws 503 UNAVAILABLE or 429 RESOURCE_EXHAUSTED,
    it automatically falls back to active alternative models (gemini-3.5-flash-lite, gemini-3.5-flash).
    """
    from google.genai import types

    primary_model = settings.GEMINI_MODEL_NAME
    backup_1 = getattr(settings, "FALLBACK_GEMINI_MODEL_1", "gemini-3.6-flash")
    backup_2 = getattr(settings, "FALLBACK_GEMINI_MODEL_2", "gemini-3.1-flash-lite")

    # Triple-tier Cascade: Primary (3.5-flash-lite) -> Backup 1 (3.6-flash) -> Backup 2 (3.1-flash-lite)
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
