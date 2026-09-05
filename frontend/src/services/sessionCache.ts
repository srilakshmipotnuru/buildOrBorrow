import type { EvaluationRequest, EvaluationResponse, PackageEvaluationDetail } from '../types/api';

const SESSION_STORAGE_KEY = 'buildorborrow_session_cache_v2';

interface CacheStore {
  evaluations: Record<string, EvaluationResponse>;
  candidates: Record<string, PackageEvaluationDetail>;
}

function getStore(): CacheStore {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (raw) {
      return JSON.parse(raw) as CacheStore;
    }
  } catch (e) {
    console.warn('Failed to read from sessionStorage:', e);
  }
  return { evaluations: {}, candidates: {} };
}

function saveStore(store: CacheStore): void {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(store));
  } catch (e) {
    console.warn('Failed to write to sessionStorage:', e);
  }
}

/**
 * Builds deterministic exact cache key according to the 5 rules:
 * Case 1: Package mode, no requirement -> pkg:<system>:<pkg_name>
 * Case 2: Package mode, with requirement -> pkg:<system>:<pkg_name>:<requirement>
 * Case 3, 4, 5: Task mode -> task:<system>:<requirement>
 */
export function buildExactCacheKey(req: EvaluationRequest): string {
  const sys = (req.system || 'pypi').trim().toLowerCase();
  const pkgName = (req.package_name || '').trim().toLowerCase();
  const userReq = (req.user_requirement || '').trim().toLowerCase();

  if (pkgName) {
    // Package Mode (Case 1, Case 2, Case 5 in Package Mode)
    if (userReq) {
      return `pkg:${sys}:${pkgName}:${userReq}`;
    }
    return `pkg:${sys}:${pkgName}`;
  } else {
    // Task Mode (Case 3, Case 4, Case 5 in Task Mode)
    return `task:${sys}:${userReq}`;
  }
}

/**
 * Key for individual candidate package evaluations in Task Mode (Case 4)
 */
export function buildCandidateCacheKey(system: string, packageName: string, taskReq: string): string {
  const sys = (system || 'pypi').trim().toLowerCase();
  const pkg = packageName.trim().toLowerCase();
  const req = taskReq.trim().toLowerCase();
  return `cand:${sys}:${pkg}:${req}`;
}

export function getEvaluationFromSession(req: EvaluationRequest): EvaluationResponse | null {
  const key = buildExactCacheKey(req);
  const store = getStore();
  return store.evaluations[key] || null;
}

export function saveEvaluationToSession(req: EvaluationRequest, data: EvaluationResponse): void {
  const key = buildExactCacheKey(req);
  const store = getStore();
  store.evaluations[key] = data;

  // If Task Mode (Case 3, 4, 5) or Package Mode with candidates, store candidate cards under cand keys
  if (data.mode === 'task') {
    const sys = (req.system || data.system || 'pypi').trim().toLowerCase();
    const taskReq = (req.user_requirement || data.task_description || '').trim().toLowerCase();

    if (data.primary_evaluation) {
      const candKey = buildCandidateCacheKey(sys, data.primary_evaluation.package_name, taskReq);
      store.candidates[candKey] = data.primary_evaluation;
    }
  }

  saveStore(store);
}

export function getCandidateEvaluationFromSession(
  system: string,
  packageName: string,
  taskReq: string
): PackageEvaluationDetail | null {
  const key = buildCandidateCacheKey(system, packageName, taskReq);
  const store = getStore();
  return store.candidates[key] || null;
}

export function saveCandidateEvaluationToSession(
  system: string,
  packageName: string,
  taskReq: string,
  evalDetail: PackageEvaluationDetail
): void {
  const key = buildCandidateCacheKey(system, packageName, taskReq);
  const store = getStore();
  store.candidates[key] = evalDetail;
  saveStore(store);
}

export function isCandidateCachedInSession(system: string, packageName: string, taskReq: string): boolean {
  const key = buildCandidateCacheKey(system, packageName, taskReq);
  const store = getStore();
  return Boolean(store.candidates[key]);
}
