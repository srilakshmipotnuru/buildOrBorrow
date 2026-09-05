import React from 'react';
import { Package, ExternalLink, CheckCircle2, AlertCircle, PlayCircle, Loader2 } from 'lucide-react';
import type { CandidateScreeningItem } from '../../types/api';
import { isCandidateCachedInSession } from '../../services/sessionCache';
import './CandidateGrid.css';

interface CandidateGridProps {
  taskDescription: string;
  candidates: CandidateScreeningItem[];
  primaryPackageName: string;
  onEvaluateCandidate?: (packageName: string, system: string) => void;
  evaluatingPackageName?: string | null;
}

export const CandidateGrid: React.FC<CandidateGridProps> = ({
  taskDescription,
  candidates,
  primaryPackageName,
  onEvaluateCandidate,
  evaluatingPackageName,
}) => {
  return (
    <div className="candidate-grid-card">
      <div className="candidate-grid-header">
        <h2>
          <Package className="header-icon" /> Candidate Discovery Screening
        </h2>
        <p className="candidate-grid-subtitle">
          Gemini Candidate Finder identified <strong>{candidates.length} candidate packages</strong> for:{' '}
          <em>"{taskDescription}"</em>
        </p>
      </div>

      <div className="candidate-cards-container">
        {candidates.map((cand) => {
          const isPrimary = cand.name.toLowerCase() === primaryPackageName.toLowerCase();
          const isEvaluatingThis =
            evaluatingPackageName && evaluatingPackageName.toLowerCase() === cand.name.toLowerCase();
          const isCached = isCandidateCachedInSession(cand.system, cand.name, taskDescription);

          return (
            <div
              key={cand.name}
              className={`candidate-item-card ${isPrimary ? 'primary-candidate' : ''}`}
            >
              {isPrimary ? (
                <div className="primary-badge">
                  <CheckCircle2 className="badge-icon" /> Selected Candidate
                </div>
              ) : (
                onEvaluateCandidate && (
                  <button
                    className={`re-evaluate-btn ${isCached ? 'cached-btn' : ''}`}
                    disabled={!!evaluatingPackageName}
                    onClick={() => onEvaluateCandidate(cand.name, cand.system)}
                    title={isCached ? `Instant load evaluation for ${cand.name}` : `Analyze package ${cand.name}`}
                  >
                    {isEvaluatingThis ? (
                      <>
                        <Loader2 className="btn-icon spin" /> Evaluating...
                      </>
                    ) : isCached ? (
                      <>
                        <CheckCircle2 className="btn-icon" /> View Evaluation
                      </>
                    ) : (
                      <>
                        <PlayCircle className="btn-icon" /> Analyze Package
                      </>
                    )}
                  </button>
                )
              )}

              <div className="cand-top-row">
                <h3 className="cand-name">{cand.name}</h3>
                <span className="cand-system">{cand.system}</span>
              </div>

              {cand.version && <div className="cand-version">v{cand.version}</div>}

              <p className="cand-reason">{cand.reason}</p>

              <div className="cand-footer">
                <div className="cand-status">
                  {cand.verified_exists ? (
                    <span className="verified-tag">
                      <CheckCircle2 className="tag-icon" /> Verified in deps.dev
                    </span>
                  ) : (
                    <span className="unverified-tag">
                      <AlertCircle className="tag-icon" /> Unverified
                    </span>
                  )}
                </div>

                {cand.github_url && (
                  <a
                    href={cand.github_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="cand-repo-link"
                  >
                    <span>Repo</span>
                    <ExternalLink className="link-icon" />
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

