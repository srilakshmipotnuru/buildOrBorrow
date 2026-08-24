import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and/or .env file.
    Follows 12-factor app principles for dev/prod environment portability.
    """
    PROJECT_NAME: str = "BuildOrBorrow API"
    API_V1_STR: str = "/api/v1"
    
    # GCP Configuration
    GCP_PROJECT: Optional[str] = None
    
    # API Keys & Credentials
    GEMINI_API_KEY: Optional[str] = None
    GITHUB_TOKEN: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_gcp_project(self) -> Optional[str]:
        """
        Resolves active GCP Project ID with fallbacks:
        1. Explicit settings.GCP_PROJECT
        2. System env var GOOGLE_CLOUD_PROJECT
        3. System env var GCP_PROJECT
        """
        return (
            self.GCP_PROJECT
            or os.getenv("GCP_PROJECT")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
        )


settings = Settings()
