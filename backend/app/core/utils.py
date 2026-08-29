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
    fallback_1 = getattr(settings, "FALLBACK_GEMINI_MODEL_NAME", "gemini-3.5-flash-lite")
    fallback_2 = "gemini-3.5-flash"

    # Cascade order: Primary model -> Fallback Lite -> Fallback 3.5 Flash
    models_to_try = [primary_model, fallback_1, fallback_2][:max_retries]

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
            is_temporary_error = "503" in err_msg or "UNAVAILABLE" in err_msg or "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
            
            if is_temporary_error and attempt < len(models_to_try) - 1:
                next_model = models_to_try[attempt + 1]
                sleep_seconds = 1.0
                logger.warning(
                    f"Gemini call to '{model_name}' failed with rate limit/capacity error ({err_msg[:120]}...). "
                    f"Switching to fallback model '{next_model}' (Attempt {attempt + 2}/{len(models_to_try)})..."
                )
                time.sleep(sleep_seconds)
            else:
                logger.error(f"Gemini API call to '{model_name}' failed: {e}")

    raise last_exception
