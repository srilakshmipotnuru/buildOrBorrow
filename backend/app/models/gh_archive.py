# app/models/gh_archive.py
from typing import List, Optional
from pydantic import BaseModel, Field


class WeeklyActivity(BaseModel):
    week_start: str = ""
    push_events: int = Field(default=0, ge=0)
    pr_events: int = Field(default=0, ge=0)
    issue_events: int = Field(default=0, ge=0)
    star_events: int = Field(default=0, ge=0)
    active_contributors: int = Field(default=0, ge=0)
    total_events: int = Field(default=0, ge=0)


class GitHubActivitySummary(BaseModel):
    total_pushes: int = Field(default=0, ge=0)
    total_prs: int = Field(default=0, ge=0)
    total_issues: int = Field(default=0, ge=0)
    total_stars: int = Field(default=0, ge=0)
    average_weekly_contributors: float = Field(default=0.0, ge=0.0)
    active_weeks_count: int = Field(default=0, ge=0)


class GitHubArchiveResponse(BaseModel):
    repo_name: str = ""
    lookback_weeks: int = Field(default=104, ge=0)
    summary: GitHubActivitySummary = Field(
        default_factory=GitHubActivitySummary
    )
    weekly_timeline: List[WeeklyActivity] = Field(
        default_factory=list
    )


class PackageActivityBridgeResponse(BaseModel):
    package_name: str
    system: str
    github_url: Optional[str] = None
    repo_owner: str
    repo_name: str
    lookback_weeks: int
    summary: GitHubActivitySummary
    weekly_timeline: List[WeeklyActivity]