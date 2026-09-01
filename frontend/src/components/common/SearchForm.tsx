import React, { useState } from 'react';
import { Search, Package, Target, Loader2, Sparkles, Layers, X, RotateCcw } from 'lucide-react';
import { CustomSelect } from './CustomSelect';
import type { EvaluationRequest } from '../../types/api';
import './SearchForm.css';

interface SearchFormProps {
  onSearch: (request: EvaluationRequest) => void;
  onReset?: () => void;
  isLoading: boolean;
}

const ECOSYSTEMS = [
  { label: 'PyPI (Python)', value: 'pypi' },
  { label: 'npm (JS/TS)', value: 'npm' },
  { label: 'Cargo (Rust)', value: 'cargo' },
  { label: 'Go (Golang)', value: 'go' },
  { label: 'Maven (Java)', value: 'maven' },
];

export const SearchForm: React.FC<SearchFormProps> = ({ onSearch, onReset, isLoading }) => {
  const [mode, setMode] = useState<'package' | 'task'>('package');
  const [packageName, setPackageName] = useState('');
  const [taskDescription, setTaskDescription] = useState('');
  const [system, setSystem] = useState('pypi');
  const [userRequirement, setUserRequirement] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const handleModeSwitch = (newMode: 'package' | 'task') => {
    setMode(newMode);
    setErrorMsg('');
    setPackageName('');
    setTaskDescription('');
    setUserRequirement('');
    if (onReset) {
      onReset();
    }
  };

  const handleResetAll = () => {
    setPackageName('');
    setTaskDescription('');
    setSystem('pypi');
    setUserRequirement('');
    setErrorMsg('');
    if (onReset) {
      onReset();
    }
  };

  const handleClearField = (field: 'package' | 'task' | 'feature') => {
    if (field === 'package') setPackageName('');
    if (field === 'task') setTaskDescription('');
    if (field === 'feature') setUserRequirement('');
    setErrorMsg('');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');

    if (mode === 'package' && !packageName.trim()) {
      setErrorMsg('Please enter a package name (e.g. feedparser, requests, axios).');
      return;
    }

    if (mode === 'task' && !taskDescription.trim()) {
      setErrorMsg('Please describe the task requirement (e.g. Parse RSS feeds in Python).');
      return;
    }

    const payload: EvaluationRequest = {
      system,
      user_requirement: userRequirement.trim() || undefined,
    };

    if (mode === 'package') {
      payload.package_name = packageName.trim();
      if (taskDescription.trim()) {
        payload.task_description = taskDescription.trim();
      }
    } else {
      payload.task_description = taskDescription.trim();
    }

    onSearch(payload);
  };

  return (
    <div className="search-form-card">
      {/* Mode Selector Tabs Header */}
      <div className="mode-tabs-header">
        <div className="mode-tabs">
          <button
            type="button"
            className={`mode-tab ${mode === 'package' ? 'active' : ''}`}
            onClick={() => handleModeSwitch('package')}
          >
            <Package className="tab-icon" />
            <span>Exact Package Mode</span>
          </button>
          <button
            type="button"
            className={`mode-tab ${mode === 'task' ? 'active' : ''}`}
            onClick={() => handleModeSwitch('task')}
          >
            <Target className="tab-icon" />
            <span>Task Requirement Mode</span>
          </button>
        </div>

        {/* Top-Right Reset Button */}
        <button
          type="button"
          className="top-reset-btn"
          onClick={handleResetAll}
          disabled={isLoading}
          title="Reset all form fields & ecosystem to PyPI"
        >
          <RotateCcw className="top-reset-icon" />
          <span>Reset</span>
        </button>
      </div>

      {/* Main Search Inputs */}
      <form onSubmit={handleSubmit} className="search-form">
        <div className="form-row">
          {mode === 'package' ? (
            <div className="form-group main-input-group">
              <label htmlFor="package-input" className="form-label">
                <Package className="label-icon" /> Package Name
              </label>
              <div className="input-wrapper">
                <Search className="input-icon" />
                <input
                  id="package-input"
                  type="text"
                  className="form-input"
                  placeholder="e.g. feedparser, requests, axios, numpy"
                  value={packageName}
                  onChange={(e) => setPackageName(e.target.value)}
                  disabled={isLoading}
                />
                {packageName && (
                  <button
                    type="button"
                    className="input-clear-btn"
                    onClick={() => handleClearField('package')}
                    title="Clear package name"
                  >
                    <X className="clear-x-icon" />
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="form-group main-input-group">
              <label htmlFor="task-input" className="form-label">
                <Target className="label-icon" /> Task Requirement
              </label>
              <div className="input-wrapper">
                <Search className="input-icon" />
                <input
                  id="task-input"
                  type="text"
                  className="form-input"
                  placeholder="e.g. I need to parse RSS feeds and extract item titles in Python"
                  value={taskDescription}
                  onChange={(e) => setTaskDescription(e.target.value)}
                  disabled={isLoading}
                />
                {taskDescription && (
                  <button
                    type="button"
                    className="input-clear-btn"
                    onClick={() => handleClearField('task')}
                    title="Clear task requirement"
                  >
                    <X className="clear-x-icon" />
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Ecosystem Selector */}
          <div className="form-group ecosystem-group">
            <label className="form-label">
              <Layers className="label-icon" /> Ecosystem
            </label>
            <CustomSelect
              options={ECOSYSTEMS}
              value={system}
              onChange={(val) => setSystem(val)}
              disabled={isLoading}
            />
          </div>
        </div>

        {/* Optional Feature / Context Input (Shown only in Exact Package Mode) */}
        {mode === 'package' && (
          <div className="form-group secondary-group">
            <label htmlFor="feature-input" className="form-label">
              Specific Feature / Requirement Detail <span className="label-optional">(Optional)</span>
            </label>
            <div className="input-wrapper">
              <input
                id="feature-input"
                type="text"
                className="form-input secondary-input"
                placeholder="e.g. Only extract title & link strings without executing embedded HTML scripts"
                value={userRequirement}
                onChange={(e) => setUserRequirement(e.target.value)}
                disabled={isLoading}
              />
              {userRequirement && (
                <button
                  type="button"
                  className="input-clear-btn"
                  onClick={() => handleClearField('feature')}
                  title="Clear feature detail"
                >
                  <X className="clear-x-icon" />
                </button>
              )}
            </div>
          </div>
        )}

        {errorMsg && <div className="form-error">{errorMsg}</div>}

        {/* Submit Button Row */}
        <button type="submit" className="submit-btn" disabled={isLoading}>
          {isLoading ? (
            <>
              <Loader2 className="btn-icon spinner" />
              <span>Scanning BigQuery & Gemini ADK Pipeline...</span>
            </>
          ) : (
            <>
              <Sparkles className="btn-icon" />
              <span>
                {mode === 'package' ? 'Evaluate Dependency Health' : 'Find & Evaluate Best Package'}
              </span>
            </>
          )}
        </button>
      </form>
    </div>
  );
};
