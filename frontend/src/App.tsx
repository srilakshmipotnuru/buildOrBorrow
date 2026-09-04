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
import type { EvaluationRequest, EvaluationResponse, PackageEvaluationDetail } from './types/api';
import './App.css';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [evaluatingPackageName, setEvaluatingPackageName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluationResponse | null>(null);
  const [globalPackageCache, setGlobalPackageCache] = useState<Record<string, PackageEvaluationDetail>>({});

  const verdictRef = useRef<HTMLDivElement>(null);

  const handleReset = () => {
    setResult(null);
    setError(null);
    setEvaluatingPackageName(null);
  };

  const handleSearch = async (request: EvaluationRequest) => {
    setError(null);
    setEvaluatingPackageName(null);

    const pkgName = (request.package_name || request.user_requirement || "").trim().toLowerCase();
    const system = (request.system || 'pypi').trim().toLowerCase();
    const exactSearchKey = `${system}:${pkgName}`;

    // Optimization 1: Instant Global Cache Lookup for Exact Package Searches
    if (request.package_name && globalPackageCache[exactSearchKey]) {
      setResult({
        mode: 'package',
        evaluation: globalPackageCache[exactSearchKey],
      });
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

      const newEval = data.mode === 'package' ? data.evaluation : data.primary_evaluation;
      if (newEval) {
        const key = `${newEval.system.toLowerCase()}:${newEval.package_name.toLowerCase()}`;
        setGlobalPackageCache((prev) => ({
          ...prev,
          [key]: newEval,
        }));
      }
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
    const cacheKey = `${system.toLowerCase()}:${packageName.toLowerCase()}`;

    // Optimization 2: Instant Global Cache Lookup for Candidate Selection
    if (globalPackageCache[cacheKey]) {
      setResult({
        mode: 'task',
        task_description: currentTaskDescription,
        system: system,
        primary_evaluation: globalPackageCache[cacheKey],
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

      setGlobalPackageCache((prev) => ({
        ...prev,
        [cacheKey]: newEval,
      }));

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

  const evaluatedCacheKeys = new Set(Object.keys(globalPackageCache));


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
                evaluatedCacheKeys={evaluatedCacheKeys}
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

