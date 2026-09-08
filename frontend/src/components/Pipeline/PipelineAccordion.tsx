import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Package,
  ShieldAlert,
  TrendingUp,
  Microscope,
  Scale,
  Hammer,
  ExternalLink,
  Bug,
  ListFilter,
  ShieldCheck,
  Lock,
  Lightbulb,
  CheckCircle2,
} from 'lucide-react';
import type { PackageEvaluationDetail } from '../../types/api';
import { ForecastChart } from './ForecastChart';
import './PipelineAccordion.css';

const formatAffectedRange = (raw: string) => {
  const matchFixedZero = raw.match(/Introduced:\s*0\s*,\s*Fixed:\s*([0-9a-zA-Z\.\-]+)/i);
  if (matchFixedZero) {
    return {
      vulnerable: `< v${matchFixedZero[1].replace(/^v/, '')}`,
      fixed: `Fixed in v${matchFixedZero[1].replace(/^v/, '')}`,
    };
  }
  const matchBoth = raw.match(/Introduced:\s*([0-9a-zA-Z\.\-]+)\s*,\s*Fixed:\s*([0-9a-zA-Z\.\-]+)/i);
  if (matchBoth) {
    return {
      vulnerable: `v${matchBoth[1].replace(/^v/, '')} to < v${matchBoth[2].replace(/^v/, '')}`,
      fixed: `Fixed in v${matchBoth[2].replace(/^v/, '')}`,
    };
  }
  const matchLt = raw.match(/<\s*v?([0-9a-zA-Z\.\-]+)/);
  if (matchLt) {
    return {
      vulnerable: `< v${matchLt[1].replace(/^v/, '')}`,
      fixed: `Fixed in v${matchLt[1].replace(/^v/, '')}`,
    };
  }
  return {
    vulnerable: raw,
    fixed: null,
  };
};

interface PipelineAccordionProps {
  evaluation: PackageEvaluationDetail;
}

export const PipelineAccordion: React.FC<PipelineAccordionProps> = ({ evaluation }) => {
  // Manage expanded state for each of the 6 steps (Step 3 Forecast open by default)
  const [openSteps, setOpenSteps] = useState<{ [key: number]: boolean }>({
    1: false,
    2: false,
    3: true, // Step 3 (Forecast Graph) expanded by default
    4: true, // Step 4 (Diagnosis & Issues) expanded by default
    5: false,
    6: true,
  });

  const toggleStep = (stepNumber: number) => {
    setOpenSteps((prev) => ({ ...prev, [stepNumber]: !prev[stepNumber] }));
  };

  const setAllSteps = (isOpen: boolean) => {
    setOpenSteps({ 1: isOpen, 2: isOpen, 3: isOpen, 4: isOpen, 5: isOpen, 6: isOpen });
  };

  const { resolution, security, forecast, recent_issues, diagnosis, verdict, builder } = evaluation;
  const isFastPath = forecast?.trend_direction === 'NOT_APPLICABLE' || verdict?.confidence_factors?.some((f) => f.includes('Bypassed BigQuery'));

  return (
    <div className="pipeline-accordion-card">
      {isFastPath && (
        <div className="fastpath-accordion-banner">
          ⚡ <strong>Fast-Path Execution Active:</strong> BigQuery warehouse scans and ML forecasting were bypassed for this single-function micro-utility requirement (&lt; 25 LOC). Zero external third-party dependencies were queried or required.
        </div>
      )}

      {/* Accordion Master Bar */}
      <div className="accordion-master-bar">
        <h3>
          <ListFilter className="bar-icon" /> Pipeline Stage Breakdown & Empirical Evidence
        </h3>
        <div className="master-controls">
          <button type="button" className="control-btn" onClick={() => setAllSteps(true)}>
            Expand All
          </button>
          <span className="control-divider">|</span>
          <button type="button" className="control-btn" onClick={() => setAllSteps(false)}>
            Collapse All
          </button>
        </div>
      </div>

      {/* Step 1: Package Resolution */}
      <div className={`accordion-step ${openSteps[1] ? 'expanded' : ''}`}>
        <div className="step-header" onClick={() => toggleStep(1)}>
          <div className="step-title-group">
            <span className="step-number">1</span>
            <Package className="step-icon" />
            <span className="step-title">Package Resolution</span>
          </div>
          <div className="step-header-meta">
            {resolution && (
              <span className="meta-pill">
                {resolution.name} v{resolution.version} [{resolution.licenses.join(', ') || 'Unknown'}]
              </span>
            )}
            {openSteps[1] ? <ChevronUp className="chevron" /> : <ChevronDown className="chevron" />}
          </div>
        </div>

        {openSteps[1] && (
          <div className="step-content">
            {resolution ? (
              <div className="content-grid">
                <div className="content-item">
                  <span className="item-label">Package Name:</span>
                  <span className="item-value font-mono">{resolution.name}</span>
                </div>
                <div className="content-item">
                  <span className="item-label">Ecosystem:</span>
                  <span className="item-value uppercase">{resolution.system}</span>
                </div>
                <div className="content-item">
                  <span className="item-label">Latest Version:</span>
                  <span className="item-value font-mono">v{resolution.version}</span>
                </div>
                <div className="content-item">
                  <span className="item-label">Licenses:</span>
                  <span className="item-value">{resolution.licenses.join(', ') || 'Unknown'}</span>
                </div>
                {resolution.github_url && (
                  <div className="content-item full-width">
                    <span className="item-label">GitHub Repository:</span>
                    <a
                      href={resolution.github_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="repo-link-btn"
                    >
                      <span>{resolution.project_name || resolution.github_url}</span>
                      <ExternalLink className="link-icon" />
                    </a>
                  </div>
                )}
              </div>
            ) : (
              <p className="missing-msg">Package resolution data unavailable in deps.dev dataset.</p>
            )}
          </div>
        )}
      </div>

      {/* Step 2: Security & Dependency Burden */}
      <div className={`accordion-step ${openSteps[2] ? 'expanded' : ''}`}>
        <div className="step-header" onClick={() => toggleStep(2)}>
          <div className="step-title-group">
            <span className="step-number">2</span>
            <ShieldAlert className="step-icon" />
            <span className="step-title">Security Advisories & Dependency Burden</span>
          </div>
          <div className="step-header-meta">
            {security && (
              <span
                className={`meta-pill ${
                  security.is_current_version_vulnerable || (security.active_cves_on_current_version ?? 0) > 0
                    ? 'alert-pill'
                    : 'safe-pill'
                }`}
              >
                {security.is_current_version_vulnerable || (security.active_cves_on_current_version ?? 0) > 0
                  ? `⚠️ ${security.active_cves_on_current_version ?? security.total_vulnerabilities} Active CVEs`
                  : `🛡️ Clean Release: 0 Active CVEs (${security.patched_historical_cves ?? security.total_vulnerabilities} Patched)`}
              </span>
            )}
            {openSteps[2] ? <ChevronUp className="chevron" /> : <ChevronDown className="chevron" />}
          </div>
        </div>

        {openSteps[2] && (
          <div className="step-content">
            {security ? (
              <div className="security-content">
                {/* Active vs Historical CVE Scoped Banner */}
                {security.is_current_version_vulnerable || (security.active_cves_on_current_version ?? 0) > 0 ? (
                  <div className="cve-status-banner vulnerable">
                    <div className="banner-icon-badge vulnerable-icon">
                      <ShieldAlert className="w-5 h-5" />
                    </div>
                    <div className="banner-text">
                      <h4>Current Release Contains Active Unpatched Vulnerabilities</h4>
                      <p>
                        <strong>{security.active_cves_on_current_version ?? security.total_vulnerabilities} active CVE(s)</strong>{' '}
                        affect this release.
                        {security.recommended_pinned_version && (
                          <> Recommended safe pinned release:{' '}
                            <strong className="safe-pin-highlight">v{security.recommended_pinned_version.replace(/^v/, '')}</strong>
                          </>
                        )}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="cve-status-banner clean">
                    <div className="banner-icon-badge clean-icon">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                    <div className="banner-text">
                      <h4>Current Release {resolution?.version ? `v${resolution.version}` : ''} is Clean (0 Active CVEs)</h4>
                      <p>
                        Zero unpatched security vulnerabilities detected on this version. All{' '}
                        <strong>{security.patched_historical_cves ?? security.total_vulnerabilities} historical CVEs</strong>{' '}
                        have been responsibly patched by project maintainers across earlier release cycles.
                      </p>
                    </div>
                  </div>
                )}

                {/* 3-Column Scoped Metrics */}
                <div className="cve-metric-cards-row">
                  <div className={`cve-metric-card ${security.is_current_version_vulnerable ? 'alert' : 'clean'}`}>
                    <span className="metric-number">{security.active_cves_on_current_version ?? 0}</span>
                    <span className="metric-label">Active CVEs on Current Release</span>
                  </div>
                  <div className="cve-metric-card neutral">
                    <span className="metric-number">{security.patched_historical_cves ?? security.total_vulnerabilities}</span>
                    <span className="metric-label">Patched Historical Advisories</span>
                  </div>
                  <div className="cve-metric-card neutral">
                    <span className="metric-number">{security.transitive_dependencies}</span>
                    <span className="metric-label">Transitive Dependency Burden</span>
                  </div>
                </div>

                {/* Historical Severity Breakdown */}
                <div className="historical-breakdown-section">
                  <span className="section-subtitle">Historical Vulnerability Breakdown (Patched in Earlier Releases):</span>
                  <div className="cve-breakdown-row">
                    <div className="cve-tag critical">
                      <span className="cve-count">{security.critical_vulnerabilities}</span>
                      <span className="cve-label">Critical</span>
                    </div>
                    <div className="cve-tag high">
                      <span className="cve-count">{security.high_vulnerabilities}</span>
                      <span className="cve-label">High</span>
                    </div>
                    <div className="cve-tag medium">
                      <span className="cve-count">{security.medium_vulnerabilities}</span>
                      <span className="cve-label">Medium</span>
                    </div>
                    <div className="cve-tag low">
                      <span className="cve-count">{security.low_vulnerabilities}</span>
                      <span className="cve-label">Low</span>
                    </div>
                  </div>
                </div>

                {/* Affected Version Ranges */}
                {security.affected_version_ranges && security.affected_version_ranges.length > 0 && (
                  <div className="affected-ranges-container">
                    <div className="affected-ranges-title-row">
                      <span className="section-subtitle">
                        Historical Affected Versions & Upstream Fixes:
                      </span>
                      <span className="section-subtext">
                        Legacy releases impacted prior to current release v{resolution?.version || ''} (All patched in this version)
                      </span>
                    </div>
                    <div className="ranges-pills-wrap">
                      {security.affected_version_ranges.map((range, idx) => {
                        const { vulnerable, fixed } = formatAffectedRange(range);
                        return (
                          <div key={idx} className="range-pill-card">
                            <span className="range-vuln-part">
                              <Lock className="range-icon" />
                              <span className="range-vuln-label">Vulnerable:</span>
                              <code>{vulnerable}</code>
                            </span>
                            {fixed && (
                              <span className="range-fixed-part">
                                <CheckCircle2 className="fixed-icon" />
                                <span>{fixed}</span>
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="missing-msg">Security advisory data unavailable.</p>
            )}
          </div>
        )}
      </div>

      {/* Step 3: Activity & 90-Day Forecast */}
      <div className={`accordion-step ${openSteps[3] ? 'expanded' : ''}`}>
        <div className="step-header" onClick={() => toggleStep(3)}>
          <div className="step-title-group">
            <span className="step-number">3</span>
            <TrendingUp className="step-icon" />
            <span className="step-title">104-Week Activity & 90-Day Forecast</span>
          </div>
          <div className="step-header-meta">
            {forecast && (
              <span className="meta-pill">
                Health Score: {forecast.health_score.toFixed(1)}/100 | {forecast.trend_direction}
              </span>
            )}
            {openSteps[3] ? <ChevronUp className="chevron" /> : <ChevronDown className="chevron" />}
          </div>
        </div>

        {openSteps[3] && (
          <div className="step-content">
            {forecast ? (
              <ForecastChart forecast={forecast} />
            ) : (
              <p className="missing-msg">Activity forecast data unavailable.</p>
            )}
          </div>
        )}
      </div>

      {/* Step 4: AI Qualitative Diagnosis & GitHub Issues */}
      <div className={`accordion-step ${openSteps[4] ? 'expanded' : ''}`}>
        <div className="step-header" onClick={() => toggleStep(4)}>
          <div className="step-title-group">
            <span className="step-number">4</span>
            <Microscope className="step-icon" />
            <span className="step-title">AI Qualitative Maintenance Diagnosis</span>
          </div>
          <div className="step-header-meta">
            <span
              className={`meta-pill ${diagnosis.is_abandoned ? 'alert-pill' : 'safe-pill'}`}
            >
              {diagnosis.status}
            </span>
            {openSteps[4] ? <ChevronUp className="chevron" /> : <ChevronDown className="chevron" />}
          </div>
        </div>

        {openSteps[4] && (
          <div className="step-content">
            <div className="diagnosis-box">
              <div className="diag-header-row">
                <span className={`status-badge ${diagnosis.status.toLowerCase()}`}>
                  {diagnosis.status}
                </span>
                <span className="diag-conf">
                  AI Confidence: {(diagnosis.confidence_score * 100).toFixed(0)}%
                </span>
              </div>

              {/* Heuristic & Semantic Reconciliation Notice */}
              {forecast && forecast.maintenance_verdict_signal === 'AT_RISK_STAGNANT' && diagnosis.status === 'MATURE_STABLE' && (
                <div className="diag-reconciliation-card">
                  <div className="reconciliation-header">
                    <Scale className="recon-icon" />
                    <strong>Heuristic & Semantic Reconciliation:</strong>
                  </div>
                  <p>
                    Automated activity heuristics flagged recent commit frequency as{' '}
                    <span className="signal-badge stagnant">AT_RISK_STAGNANT</span> (Score: {forecast.health_score.toFixed(0)}/100).
                    However, semantic AI issue analysis confirms this is a <strong>mature, stable bedrock library</strong> with active release roadmaps and responsible maintenance triage.
                  </p>
                </div>
              )}

              {/* Dedicated AI Confidence Justification Callout */}
              {diagnosis.confidence_reason && (
                <div className="diag-confidence-reason-card">
                  <div className="confidence-reason-header">
                    <Lightbulb className="reason-icon" />
                    <strong>AI Confidence Justification:</strong>
                  </div>
                  <p className="confidence-reason-text">{diagnosis.confidence_reason}</p>
                </div>
              )}

              <div className="diag-explanation">
                <strong>Diagnosis Analysis:</strong> {diagnosis.explanation}
              </div>

              <div className="diag-bug-assessment">
                <div className="bug-assessment-header">
                  <Bug className="bug-icon" />
                  <strong>Open Issue & Bug Severity Assessment:</strong>
                </div>
                <p>{diagnosis.bug_severity_assessment}</p>
              </div>

              {/* Evaluated Recent GitHub Issue Titles */}
              {recent_issues && recent_issues.length > 0 && (
                <div className="issues-evaluated-container">
                  <h4>
                    <Bug className="issue-heading-icon" /> Evaluated Open GitHub Issues ({recent_issues.length}):
                  </h4>
                  <ul className="issues-list">
                    {recent_issues.map((issue, idx) => (
                      <li key={idx} className="issue-item">
                        <span className="issue-title">{issue.title}</span>
                        <span className="issue-age">{issue.age}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Step 5: Verdict Details */}
      <div className={`accordion-step ${openSteps[5] ? 'expanded' : ''}`}>
        <div className="step-header" onClick={() => toggleStep(5)}>
          <div className="step-title-group">
            <span className="step-number">5</span>
            <Scale className="step-icon" />
            <span className="step-title">Architectural Verdict Details</span>
          </div>
          <div className="step-header-meta">
            <span className="meta-pill">{verdict.decision}</span>
            {openSteps[5] ? <ChevronUp className="chevron" /> : <ChevronDown className="chevron" />}
          </div>
        </div>

        {openSteps[5] && (
          <div className="step-content">
            <div className="verdict-details-content">
              <h4>Formulaic Evidence Factors:</h4>
              <ul className="factors-list">
                {verdict.confidence_factors.map((f, idx) => (
                  <li key={idx}>{f}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Step 6: Code Replacement Snippet (Only if Verdict is BUILD) */}
      {builder && (
        <div className={`accordion-step ${openSteps[6] ? 'expanded' : ''}`}>
          <div className="step-header" onClick={() => toggleStep(6)}>
            <div className="step-title-group">
              <span className="step-number">6</span>
              <Hammer className="step-icon" />
              <span className="step-title">Generated Zero-Dependency Code Replacement</span>
            </div>
            <div className="step-header-meta">
              <span className="meta-pill uppercase">{builder.language}</span>
              {openSteps[6] ? <ChevronUp className="chevron" /> : <ChevronDown className="chevron" />}
            </div>
          </div>

          {openSteps[6] && (
            <div className="step-content">
              <div className="builder-snippet-box">
                <p className="builder-explanation">{builder.explanation}</p>
                <pre className="builder-code-block">
                  <code>{builder.code_snippet}</code>
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
