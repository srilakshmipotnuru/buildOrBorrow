import { useState, useRef } from 'react';
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
import {
  getEvaluationFromSession,
  saveEvaluationToSession,
  getCandidateEvaluationFromSession,
  saveCandidateEvaluationToSession,
} from './services/sessionCache';
import type { EvaluationRequest, EvaluationResponse } from './types/api';
import './App.css';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [evaluatingPackageName, setEvaluatingPackageName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluationResponse | null>(null);

  const verdictRef = useRef<HTMLDivElement>(null);

  const handleReset = () => {
    setResult(null);
    setError(null);
    setEvaluatingPackageName(null);
  };

  const handleSearch = async (request: EvaluationRequest) => {
    setError(null);
    setEvaluatingPackageName(null);

    // Exact Match Session Cache Check (Handles Case 1, Case 2, Case 3, Case 4, Case 5)
    const cachedResponse = getEvaluationFromSession(request);
    if (cachedResponse) {
      setResult(cachedResponse);
      setTimeout(() => {
        verdictRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 50);
      return;
    }

    setIsLoading(true);
    setResult(null); // Clear active result view during new search

    try {
      const data = await evaluateDependencyOrTask(request);
      setResult(data);
      saveEvaluationToSession(request, data);
    } catch (err: any) {
      setError(err.message || 'An error occurred during evaluation.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleEvaluateCandidate = async (packageName: string, system: string) => {
    if (!result || result.mode !== 'task') return;
    setError(null);

    const currentTaskDescription = result.task_description;
    const currentCandidateScreenings = result.candidate_screenings;

    // Exact Task-Scoped Candidate Session Cache Check (Case 4)
    const cachedCandidateEval = getCandidateEvaluationFromSession(system, packageName, currentTaskDescription);
    if (cachedCandidateEval) {
      setResult({
        mode: 'task',
        task_description: currentTaskDescription,
        system: system,
        primary_evaluation: cachedCandidateEval,
        candidate_screenings: currentCandidateScreenings,
      });
      setTimeout(() => {
        verdictRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 50);
      return;
    }

    setIsLoading(true);
    setEvaluatingPackageName(packageName);

    const candScreening = currentCandidateScreenings.find(
      (c) => c.name.toLowerCase() === packageName.toLowerCase()
    );

    try {
      const data = await evaluateDependencyOrTask({
        package_name: packageName,
        system: system,
        user_requirement: currentTaskDescription,
        cached_github_url: candScreening?.github_url,
      });

      const newEval = data.mode === 'package' ? data.evaluation : data.primary_evaluation;
      saveCandidateEvaluationToSession(system, packageName, currentTaskDescription, newEval);

      setResult({
        mode: 'task',
        task_description: currentTaskDescription,
        system: system,
        primary_evaluation: newEval,
        candidate_screenings: currentCandidateScreenings,
      });

      setTimeout(() => {
        verdictRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 50);
    } catch (err: any) {
      setError(err.message || `An error occurred during evaluation of ${packageName}.`);
    } finally {
      setIsLoading(false);
      setEvaluatingPackageName(null);
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
          <div className="results-wrapper" ref={verdictRef}>
            {/* Task Candidate Screening Grid (Rendered in Task Mode when candidates exist) */}
            {result.mode === 'task' && result.candidate_screenings && result.candidate_screenings.length > 0 && (
              <CandidateGrid
                taskDescription={result.task_description}
                candidates={result.candidate_screenings}
                primaryPackageName={primaryEval.package_name}
                onEvaluateCandidate={handleEvaluateCandidate}
                evaluatingPackageName={evaluatingPackageName}
              />
            )}

            {/* Verdict Hero Banner Card */}
            <VerdictCard
              verdict={primaryEval.verdict}
              packageName={primaryEval.package_name}
              system={primaryEval.system}
              userRequirement={result.mode === 'task' ? result.task_description : undefined}
            />

            {/* Migration Alternative Comparison Card (Rendered when Verdict is MIGRATE) */}
            {primaryEval.verdict.decision === 'MIGRATE' && (
              <MigrationComparison evaluation={primaryEval} />
            )}

            {/* Syntax-Highlighted Code Replacement Viewer (Rendered when Verdict is BUILD) */}
            {primaryEval.verdict.decision === 'BUILD' && primaryEval.builder && (
              <CodeViewer builder={primaryEval.builder} packageName={primaryEval.package_name} />
            )}

            {/* Expandable 6-Step Pipeline Accordion & Recharts Forecast Graph (Suppressed for Task Mode BUILD micro-utilities) */}
            {!(result.mode === 'task' && primaryEval.verdict.decision === 'BUILD' && !primaryEval.resolution) && (
              <PipelineAccordion evaluation={primaryEval} />
            )}

            {/* Raw JSON Data Transparency Inspector */}
            <RawDataInspector data={result} />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;

