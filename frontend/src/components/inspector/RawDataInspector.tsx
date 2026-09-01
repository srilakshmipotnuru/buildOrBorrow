import React, { useState } from 'react';
import { Terminal, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';
import type { EvaluationResponse } from '../../types/api';
import './RawDataInspector.css';

interface RawDataInspectorProps {
  data: EvaluationResponse;
}

export const RawDataInspector: React.FC<RawDataInspectorProps> = ({ data }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const jsonString = JSON.stringify(data, null, 2);

  const handleCopyJSON = () => {
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="ui-card raw-inspector-card">
      <div className="raw-inspector-header" onClick={() => setIsOpen(!isOpen)}>
        <div className="title-group">
          <Terminal className="terminal-icon" />
          <span>Raw API Pipeline Data Inspector (JSON Response)</span>
        </div>
        <div className="header-actions">
          <span className="raw-tag">FastAPI Response Payload</span>
          {isOpen ? <ChevronUp className="chevron" /> : <ChevronDown className="chevron" />}
        </div>
      </div>

      {isOpen && (
        <div className="raw-inspector-body">
          <div className="raw-toolbar">
            <span className="raw-meta">Total payload size: {jsonString.length} bytes</span>
            <button type="button" className="ui-action-btn copy-json-btn" onClick={handleCopyJSON}>
              {copied ? (
                <>
                  <Check className="btn-icon" />
                  <span>Copied JSON!</span>
                </>
              ) : (
                <>
                  <Copy className="btn-icon" />
                  <span>Copy JSON</span>
                </>
              )}
            </button>
          </div>

          <pre className="raw-json-block">
            <code>{jsonString}</code>
          </pre>
        </div>
      )}
    </div>
  );
};
