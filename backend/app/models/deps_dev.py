from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PackageResolutionResponse(BaseModel):
    name: str
    system: str
    version: str
    project_name: Optional[str] = None
    licenses: List[str] = []
    github_url: Optional[str] = None
    published_at: Optional[str] = None


class SecurityContextResponse(BaseModel):
    critical_vulnerabilities: int = 0
    high_vulnerabilities: int = 0
    medium_vulnerabilities: int = 0
    low_vulnerabilities: int = 0
    unknown_vulnerabilities: int = 0
    total_vulnerabilities: int = 0
    direct_dependencies: Optional[int] = None
    transitive_dependencies: int = 0
    license: str = "Unknown"
    affected_version_ranges: List[str] = Field(default_factory=list)
    active_cves_on_current_version: int = 0
    patched_historical_cves: int = 0
    is_current_version_vulnerable: bool = False


class DepsDevVerificationResponse(BaseModel):
    package_name: str
    system: Optional[str] = None
    resolution: Optional[PackageResolutionResponse] = None
    security: SecurityContextResponse
