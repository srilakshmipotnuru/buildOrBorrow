from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.queries.deps_dev import query_package_resolution, query_security_and_dependencies
from app.models.deps_dev import (
    DepsDevVerificationResponse,
    PackageResolutionResponse,
    SecurityContextResponse
)

router = APIRouter(prefix="/deps-dev", tags=["deps.dev Verification"])


@router.get("/package-info", response_model=DepsDevVerificationResponse)
def get_package_info(
    package_name: str = Query(..., description="Package name to resolve (e.g. 'feedparser', 'axios', 'requests')"),
    system: Optional[str] = Query(None, description="Optional ecosystem (e.g. 'PYPI', 'NPM', 'CARGO', 'GO')")
):
    """
    Verification Endpoint:
    Queries BigQuery deps.dev dataset to return:
    1. Dynamic Package Resolution (ecosystem, latest version, GitHub repo URL, publication date)
    2. Security Vulnerabilities breakdown (CRITICAL, HIGH, MEDIUM, LOW) & Transitive Dependency count
    """
    # 1. Query Package Resolution
    resolution_data = query_package_resolution(package_name=package_name, system=system)
    
    if not resolution_data:
        raise HTTPException(
            status_code=404, 
            detail=f"Package '{package_name}' could not be resolved in deps.dev dataset."
        )

    resolved_system = resolution_data["system"]
    resolved_version = resolution_data["version"]

    # 2. Query Security & Dependencies using resolved ecosystem & version
    security_data = query_security_and_dependencies(
        package_name=package_name,
        system=resolved_system,
        version=resolved_version
    )

    return DepsDevVerificationResponse(
        package_name=package_name,
        system=resolved_system,
        resolution=PackageResolutionResponse(**resolution_data),
        security=SecurityContextResponse(**security_data)
    )
