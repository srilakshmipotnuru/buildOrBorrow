import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check, Hammer, Code } from 'lucide-react';
import type { BuilderResponse } from '../../types/api';
import './CodeViewer.css';

interface CodeViewerProps {
  builder: BuilderResponse;
  packageName: string;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({ builder, packageName }) => {
  const [copied, setCopied] = useState(false);

  const handleCopyCode = () => {
    navigator.clipboard.writeText(builder.code_snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="ui-card code-viewer-card">
      <div className="code-viewer-header">
        <div className="header-title-group">
          <Hammer className="header-icon" />
          <div>
            <h3>
              {packageName.includes(' ')
                ? 'Zero-Dependency In-House Code Replacement'
                : `Zero-Dependency Code Replacement for ${packageName}`}
            </h3>
            <p className="header-subtitle">{builder.explanation}</p>
          </div>
        </div>

        <button type="button" className="ui-action-btn copy-code-btn" onClick={handleCopyCode}>
          {copied ? (
            <>
              <Check className="btn-icon" />
              <span>Copied Code!</span>
            </>
          ) : (
            <>
              <Copy className="btn-icon" />
              <span>Copy Code</span>
            </>
          )}
        </button>
      </div>

      <div className="code-viewer-body">
        <div className="code-lang-bar">
          <Code className="lang-icon" />
          <span className="lang-text">{builder.language.toUpperCase()}</span>
          {builder.dependencies_used.length === 0 && (
            <span className="zero-dep-badge">0 External Dependencies</span>
          )}
        </div>

        <SyntaxHighlighter
          language={builder.language.toLowerCase()}
          style={vscDarkPlus}
          customStyle={{
            margin: 0,
            borderRadius: '0 0 12px 12px',
            fontSize: '0.9rem',
            padding: '1.25rem',
          }}
        >
          {builder.code_snippet}
        </SyntaxHighlighter>
      </div>
    </div>
  );
};
