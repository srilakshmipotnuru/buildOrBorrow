export interface EvaluationRequest {
  package_name?: string;
  task_description?: string;
  system: string; // 'pypi', 'npm', 'cargo', 'go', 'maven'
  user_requirement?: string;
  cached_github_url?: string;
}

export interface PackageResolutionResponse {
  name: string;
  system: string;
  version: string;
  project_name?: string;
  licenses: string[];
  github_url?: string;
  published_at?: string;
}

export interface SecurityContextResponse {
  critical_vulnerabilities: number;
  high_vulnerabilities: number;
  medium_vulnerabilities: number;
  low_vulnerabilities: number;
  unknown_vulnerabilities: number;
  total_vulnerabilities: number;
  direct_dependencies?: number | null;
  transitive_dependencies: number;
  license: string;
}

export interface ProjectedWeek {
  week_start: string;
  projected_events: number;
  confidence_lower: number;
  confidence_upper: number;
}

export interface ForecastAnalysis {
  projected_timeline: ProjectedWeek[];
  trend_direction: 'ACCELERATING' | 'STABLE' | 'DECLINING' | 'UNKNOWN';
  health_score: number;
  projected_total_events_90d: number;
  maintenance_verdict_signal: 'HEALTHY_ACTIVE' | 'SLOW_MAINTENANCE' | 'AT_RISK_STAGNANT' | 'ABANDONED' | string;
}

export interface RecentGitHubIssue {
  title: string;
  created_at: string;
  age: string;
  formatted_text: string;
}

export interface DiagnosisResponse {
  status: 'MATURE_STABLE' | 'MAINTAINED_ACTIVE' | 'ABANDONED_STRUGGLING' | 'VULNERABLE';
  is_abandoned: boolean;
  confidence_score: number;
  confidence_reason: string;
  bug_severity_assessment: string;
  explanation: string;
}

export interface AlternativeVerification {
  name: string;
  system: string;
  version?: string;
  verified_exists: boolean;
  github_url?: string;
  licenses: string[];
  published_at?: string;
  note?: string;
}

export interface VerdictResponse {
  decision: 'BORROW' | 'MIGRATE' | 'BUILD';
  confidence_score: number;
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW';
  confidence_factors: string[];
  reasoning: string[];
  recommended_alternative?: string;
  recommended_alternative_system?: string;
  alternative_verification?: AlternativeVerification;
  estimated_build_effort?: string;
}

export interface BuilderResponse {
  language: string;
  code_snippet: string;
  explanation: string;
  dependencies_used: string[];
}

export interface PackageEvaluationDetail {
  package_name: string;
  system: string;
  github_url?: string;
  repo_owner?: string;
  repo_name?: string;
  resolution?: PackageResolutionResponse;
  security?: SecurityContextResponse;
  forecast?: ForecastAnalysis;
  recent_issues: RecentGitHubIssue[];
  diagnosis: DiagnosisResponse;
  verdict: VerdictResponse;
  builder?: BuilderResponse;
}

export interface CandidateScreeningItem {
  name: string;
  system: string;
  reason: string;
  version?: string;
  github_url?: string;
  licenses: string[];
  verified_exists: boolean;
}

export interface EvaluationSingleResponse {
  mode: 'package';
  evaluation: PackageEvaluationDetail;
}

export interface EvaluationTaskResponse {
  mode: 'task';
  task_description: string;
  system: string;
  primary_evaluation: PackageEvaluationDetail;
  candidate_screenings: CandidateScreeningItem[];
}

export type EvaluationResponse = EvaluationSingleResponse | EvaluationTaskResponse;
