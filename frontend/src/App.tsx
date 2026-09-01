import { useState } from 'react';
import {
  SearchForm,
  VerdictCard,
  CandidateGrid,
  PipelineAccordion,
  MigrationComparison,
  CodeViewer,
  RawDataInspector,
} from './components';
import { evaluateDependencyOrTask } from './services/api';
import type { EvaluationRequest, EvaluationResponse } from './types/api';
import './App.css';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluationResponse | null>(null);

  const handleReset = () => {
    setResult(null);
    setError(null);
  };

  const handleSearch = async (request: EvaluationRequest) => {
    setIsLoading(true);
    setError(null);
    setResult(null); // Clear stale results immediately when initiating new search
    try {
      const data = await evaluateDependencyOrTask(request);
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'An error occurred during evaluation.');
    } finally {
      setIsLoading(false);
    }
  };

  const primaryEval = result
    ? result.mode === 'package'
      ? result.evaluation
      : result.primary_evaluation
    : null;

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>BuildOrBorrow</h1>
        <p>AI-Powered Software Dependency Health Evaluator & Decision Engine</p>
      </header>

      <main className="app-main">
        <SearchForm onSearch={handleSearch} onReset={handleReset} isLoading={isLoading} />

        {error && (
          <div className="error-banner">
            <strong>Evaluation Error:</strong> {error}
          </div>
        )}

        {result && primaryEval && (
          <div className="results-wrapper">
            {/* Task Candidate Screening Grid (Rendered in Task Mode) */}
            {result.mode === 'task' && (
              <CandidateGrid
                taskDescription={result.task_description}
                candidates={result.candidate_screenings}
                primaryPackageName={primaryEval.package_name}
              />
            )}

            {/* Verdict Hero Banner Card */}
            <VerdictCard
              verdict={primaryEval.verdict}
              packageName={primaryEval.package_name}
              system={primaryEval.system}
            />

            {/* Migration Alternative Comparison Card (Rendered when Verdict is MIGRATE) */}
            {primaryEval.verdict.decision === 'MIGRATE' && (
              <MigrationComparison evaluation={primaryEval} />
            )}

            {/* Syntax-Highlighted Code Replacement Viewer (Rendered when Verdict is BUILD) */}
            {primaryEval.verdict.decision === 'BUILD' && primaryEval.builder && (
              <CodeViewer builder={primaryEval.builder} packageName={primaryEval.package_name} />
            )}

            {/* Expandable 6-Step Pipeline Accordion & Recharts Forecast Graph */}
            <PipelineAccordion evaluation={primaryEval} />

            {/* Raw JSON Data Transparency Inspector */}
            <RawDataInspector data={result} />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
