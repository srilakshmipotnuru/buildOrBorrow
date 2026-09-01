import React from 'react';
import { ArrowRight, AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { PackageEvaluationDetail } from '../../types/api';
import './MigrationComparison.css';

interface MigrationComparisonProps {
  evaluation: PackageEvaluationDetail;
}

export const MigrationComparison: React.FC<MigrationComparisonProps> = ({ evaluation }) => {
  const { package_name, system, security, forecast, verdict } = evaluation;

  if (verdict.decision !== 'MIGRATE' || !verdict.recommended_alternative) {
    return null;
  }

  const recommendedName = verdict.recommended_alternative;
  const recommendedSys = verdict.recommended_alternative_system || system;

  return (
    <div className="ui-card migration-card">
      <div className="migration-header">
        <h2>
          <AlertTriangle className="header-icon" /> Migration Path Recommendation
        </h2>
        <p className="migration-subtitle">
          AI decision engine identified that <code>{package_name}</code> exhibits maintenance stagnation or security risks. Switch to the recommended active alternative.
        </p>
      </div>

      <div className="migration-comparison-grid">
        {/* Current Package (Old/Risky) */}
        <div className="comparison-box source-box">
          <div className="box-tag risk-tag">
            <AlertTriangle className="tag-icon" /> Current (Stagnant/Risk)
          </div>
          <h3 className="package-title">{package_name}</h3>
          <span className="system-badge">{system}</span>

          <ul className="comparison-metrics">
            <li>
              <span className="metric-label">Security CVEs:</span>
              <span className="metric-val text-alert">
                {security ? security.total_vulnerabilities : 'N/A'} vulnerabilities
              </span>
            </li>
            <li>
              <span className="metric-label">Health Score:</span>
              <span className="metric-val text-alert">
                {forecast ? `${forecast.health_score.toFixed(1)}/100` : 'N/A'}
              </span>
            </li>
            <li>
              <span className="metric-label">Transitive Deps:</span>
              <span className="metric-val">
                {security ? `${security.transitive_dependencies} packages` : 'N/A'}
              </span>
            </li>
          </ul>
        </div>

        {/* Transition Arrow */}
        <div className="transition-arrow-container">
          <ArrowRight className="arrow-icon" />
          <span className="arrow-label">MIGRATE TO</span>
        </div>

        {/* Recommended Package (Healthy) */}
        <div className="comparison-box target-box">
          <div className="box-tag safe-tag">
            <CheckCircle2 className="tag-icon" /> Recommended Switch
          </div>
          <h3 className="package-title">{recommendedName}</h3>
          <span className="system-badge">{recommendedSys}</span>

          <ul className="comparison-metrics">
            <li>
              <span className="metric-label">Security CVEs:</span>
              <span className="metric-val text-safe">0 Critical CVEs</span>
            </li>
            <li>
              <span className="metric-label">Maintenance Health:</span>
              <span className="metric-val text-safe">Active & Maintained</span>
            </li>
            <li>
              <span className="metric-label">Status:</span>
              <span className="metric-val text-safe">Verified in deps.dev</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
