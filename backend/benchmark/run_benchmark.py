"""
run_benchmark.py
----------------
Executes the BuildOrBorrow validation benchmark against the harvested test suite.
Cross-references verdicts against live OpenSSF Scorecards ground-truth,
runs polyglot zero-dependency code syntax validation,
and computes concordance metrics across all 5 ecosystems.
Outputs: backend/benchmark/benchmark_results.csv & benchmark_results.json
"""

import os
import sys
import csv
import json
import time
import argparse
from datetime import datetime
from typing import Dict, List, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BENCHMARK_DIR = os.path.dirname(__file__)
SUITES_DIR = os.path.join(BENCHMARK_DIR, "suites")
RESULTS_DIR = os.path.join(BENCHMARK_DIR, "results")
os.makedirs(SUITES_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

SUITE_CSV = os.path.join(SUITES_DIR, "benchmark_suite.csv")
RESULTS_CSV = os.path.join(RESULTS_DIR, "benchmark_results.csv")
RESULTS_JSON = os.path.join(RESULTS_DIR, "benchmark_results.json")

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(BENCHMARK_DIR, "..")))

from app.api.endpoints.evaluate import evaluate_single_package_pipeline, EvaluationRequest, evaluate_pipeline
from benchmark.verify_syntax import verify_builder_snippet


from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

print_lock = threading.Lock()


def execute_single_test(idx: int, tc: Dict[str, Any], total_cases: int) -> Dict[str, Any]:
    """Executes a single benchmark test case."""
    test_id = tc.get("test_id", f"TC-{idx:03d}")
    scenario = tc.get("scenario_code", "S1")
    mode = tc.get("mode", "package").lower()
    system = tc.get("system", "pypi").lower()
    pkg_name = tc.get("package_name", "").strip()
    task_desc = tc.get("task_description", "").replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    expected = tc.get("expected_verdict", "BORROW").strip()
    openssf_score = str(tc.get("openssf_score", "N/A")).strip()
    openssf_url = str(tc.get("openssf_viewer_url", "N/A")).strip()
    eco_url = str(tc.get("ecosystems_viewer_url", "N/A")).strip()

    with print_lock:
        print(f"[{idx}/{total_cases}] STARTING {test_id} ({scenario} - {system.upper()}): '{pkg_name or task_desc[:40]}...'")
    t0 = time.time()

    actual_verdict = "ERROR"
    conf_score = 0.0
    conf_level = "LOW"
    diag_status = "UNKNOWN"
    syntax_valid = "N/A"
    zero_dep_valid = "N/A"
    rec_pinned = "None"
    rec_alt = "None"
    api_status = "PENDING"
    error_msg = "None"
    verdict_reasoning = "None"
    diag_explanation = "None"

    try:
        req = EvaluationRequest(
            package_name=pkg_name if mode == "package" and pkg_name else None,
            task_description=task_desc if mode == "task" or not pkg_name else None,
            user_requirement=task_desc if mode == "package" else None,
            system=system
        )
        response = evaluate_pipeline(req)
        
        # Extract evaluation detail
        if hasattr(response, "primary_evaluation"):
            eval_detail = response.primary_evaluation
        else:
            eval_detail = response.evaluation

        actual_verdict = eval_detail.verdict.decision
        conf_score = eval_detail.verdict.confidence_score
        conf_level = eval_detail.verdict.confidence_level
        diag_status = eval_detail.diagnosis.status
        diag_explanation = (eval_detail.diagnosis.explanation or "None").replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        verdict_reasoning = (" | ".join(eval_detail.verdict.reasoning) if eval_detail.verdict.reasoning else "None").replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        rec_pinned = str(eval_detail.verdict.recommended_pinned_version or "None").strip()
        rec_alt = str(eval_detail.verdict.recommended_alternative or "None").strip()
        api_status = "SUCCESS"
        error_msg = "None"

        # Polyglot Syntax Verification for BUILD
        if eval_detail.builder and eval_detail.builder.code_snippet:
            syntax_check = verify_builder_snippet(
                language=eval_detail.builder.language,
                code_snippet=eval_detail.builder.code_snippet,
                dependencies_used=eval_detail.builder.dependencies_used
            )
            syntax_valid = syntax_check.get("syntax_valid", False)
            zero_dep_valid = syntax_check.get("zero_dependencies_valid", False)

    except Exception as e:
        actual_verdict = "ERROR"
        api_status = "ERROR"
        error_msg = str(e).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        verdict_reasoning = f"Exception: {error_msg}"

    latency = round(time.time() - t0, 2)
    expected_options = [e.strip().upper() for e in expected.split("/") if e.strip()]
    is_pass = actual_verdict.upper() in expected_options
    status_symbol = "✔ PASS" if is_pass else f"✖ MISMATCH (Expected: {expected})"

    with print_lock:
        print(f"[{idx}/{total_cases}] FINISHED {test_id}: {status_symbol} | Verdict: {actual_verdict} ({conf_score} {conf_level}) | Time: {latency}s")
        if error_msg != "None":
            print(f"   API Error Response: {error_msg}")
        if syntax_valid != "N/A":
            print(f"   Code Syntax Check: Valid={syntax_valid} | Zero-Dep={zero_dep_valid}")

    repo_name = str(tc.get("repo_name", "")).strip()
    github_url = str(tc.get("github_url", "")).strip()

    return {
        "test_id": test_id,
        "scenario_code": scenario,
        "mode": mode,
        "system": system,
        "package_name": pkg_name,
        "task_description": task_desc,
        "expected_verdict": expected,
        "actual_verdict": actual_verdict,
        "is_pass": is_pass,
        "repo_name": repo_name,
        "github_url": github_url,
        "openssf_score": openssf_score,
        "openssf_viewer_url": openssf_url,
        "ecosystems_viewer_url": eco_url,
        "api_status": api_status,
        "error_message": error_msg,
        "verdict_reasoning": verdict_reasoning,
        "diagnosis_explanation": diag_explanation,
        "confidence_score": conf_score,
        "confidence_level": conf_level,
        "diagnosis_status": diag_status,
        "syntax_valid": syntax_valid,
        "zero_dep_valid": zero_dep_valid,
        "recommended_pinned_version": rec_pinned,
        "recommended_alternative": rec_alt,
        "latency_sec": latency
    }


def run_benchmark(suite_idx: int = 1, sample_size: int = 0, target_scenario: str = None, max_workers: int = 3):
    """Executes the validation benchmark suite with concurrent worker threads."""
    target_csv = os.path.join(SUITES_DIR, f"benchmark_suite_{suite_idx}.csv")
    if not os.path.exists(target_csv):
        target_csv = os.path.join(BENCHMARK_DIR, f"benchmark_suite_{suite_idx}.csv")
    if not os.path.exists(target_csv):
        target_csv = SUITE_CSV
    if not os.path.exists(target_csv):
        target_csv = os.path.join(BENCHMARK_DIR, "benchmark_suite.csv")

    if not os.path.exists(target_csv):
        print(f"❌ Error: Benchmark suite CSV not found at {target_csv}.")
        print("   Run generate_dynamic_suites.py first.")
        return

    test_cases = []
    with open(target_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if target_scenario and row.get("scenario_code") != target_scenario:
                continue
            test_cases.append(row)

    if not test_cases:
        print(f"No test cases matched filter (scenario={target_scenario}).")
        return

    if sample_size > 0:
        test_cases = test_cases[:sample_size]

    print("=" * 110)
    print(f"🚀 [BENCHMARK RUNNER] Executing BuildOrBorrow Multi-Ecosystem Benchmark (Suite {suite_idx})")
    print(f"   Suite File: {os.path.basename(target_csv)} | Total Test Cases: {len(test_cases)} | Workers: {max_workers}")
    print("=" * 110)

    start_all = time.time()
    fieldnames = [
        "test_id",
        "scenario_code",
        "mode",
        "system",
        "package_name",
        "task_description",
        "expected_verdict",
        "actual_verdict",
        "is_pass",
        "repo_name",
        "github_url",
        "openssf_score",
        "openssf_viewer_url",
        "ecosystems_viewer_url",
        "api_status",
        "error_message",
        "verdict_reasoning",
        "diagnosis_explanation",
        "confidence_score",
        "confidence_level",
        "diagnosis_status",
        "syntax_valid",
        "zero_dep_valid",
        "recommended_pinned_version",
        "recommended_alternative",
        "latency_sec"
    ]

    total_count = len(test_cases)
    results = [None] * total_count

    # Concurrent execution pool with deterministic slot assignment
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(execute_single_test, idx, tc, total_count): idx
            for idx, tc in enumerate(test_cases, 1)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                res = future.result()
                results[idx - 1] = res
            except Exception as e:
                tc = test_cases[idx - 1]
                results[idx - 1] = {
                    "test_id": tc.get("test_id", f"TC-{idx:03d}"),
                    "scenario_code": tc.get("scenario_code", "S1"),
                    "mode": tc.get("mode", "package"),
                    "system": tc.get("system", "pypi"),
                    "package_name": tc.get("package_name", ""),
                    "task_description": tc.get("task_description", ""),
                    "expected_verdict": tc.get("expected_verdict", "BORROW"),
                    "actual_verdict": "ERROR",
                    "is_pass": False,
                    "repo_name": "N/A",
                    "github_url": "N/A",
                    "openssf_score": "N/A",
                    "openssf_viewer_url": "N/A",
                    "ecosystems_viewer_url": "N/A",
                    "api_status": "FAILED",
                    "error_message": str(e),
                    "verdict_reasoning": "None",
                    "diagnosis_explanation": "None",
                    "confidence_score": 0.0,
                    "confidence_level": "LOW",
                    "diagnosis_status": "UNKNOWN",
                    "syntax_valid": "N/A",
                    "zero_dep_valid": "N/A",
                    "recommended_pinned_version": "None",
                    "recommended_alternative": "None",
                    "latency_sec": 0.0
                }

    # Strict Alignment Verification: Guarantee 1:1 row alignment with benchmark_suite.csv
    pass_count = 0
    for i, (tc, res) in enumerate(zip(test_cases, results)):
        assert res is not None, f"Consolidation Error: Slot {i} is None!"
        assert tc["test_id"] == res["test_id"], f"Consolidation Error: Row {i} test_id mismatch: '{tc['test_id']}' vs '{res['test_id']}'"
        assert tc.get("package_name", "").strip() == res["package_name"].strip(), f"Consolidation Error: Row {i} package_name mismatch: '{tc.get('package_name')}' vs '{res['package_name']}'"
        if res.get("is_pass"):
            pass_count += 1

    total_time = round(time.time() - start_all, 2)
    accuracy = round((pass_count / total_count) * 100, 1) if total_count else 0.0

    res_csv_path = os.path.join(RESULTS_DIR, f"benchmark_results_{suite_idx}.csv")
    res_json_path = os.path.join(RESULTS_DIR, f"benchmark_results_{suite_idx}.json")

    # Save to CSV
    with open(res_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Save to JSON
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "suite_index": suite_idx,
        "total_tests": total_count,
        "passed_tests": pass_count,
        "accuracy_percentage": accuracy,
        "total_execution_seconds": total_time,
        "workers": max_workers,
        "results": results
    }
    with open(res_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Print Summary Table
    print("\n" + "=" * 115)
    print(f" 📊 BENCHMARK SUMMARY REPORT (SUITE {suite_idx})")
    print(f" Tests Run: {len(test_cases)} | Passed: {pass_count} | Accuracy: {accuracy}% | Duration: {total_time}s | Workers: {max_workers}")
    print("=" * 115)
    print(f"| {'Test ID':<12} | {'System':<6} | {'Scenario':<6} | {'Expected':<15} | {'Actual':<10} | {'Score':<5} | {'Result':<8} |")
    print("-" * 80)
    for r in results:
        res_str = "PASS" if r["is_pass"] else "FAIL"
        print(f"| {r['test_id']:<12} | {r['system'].upper():<6} | {r['scenario_code']:<6} | {r['expected_verdict']:<15} | {r['actual_verdict']:<10} | {r['confidence_score']:<5} | {res_str:<8} |")
    print("-" * 80)
    print(f"✔ Saved full results to: {res_csv_path}")
    print(f"✔ Saved full JSON to:    {res_json_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BuildOrBorrow Validation Benchmark Runner")
    parser.add_argument("suite", type=int, nargs="?", default=1, help="Suite number to run (1 to 5)")
    parser.add_argument("--sample", type=int, default=0, help="Run a sample of N test cases")
    parser.add_argument("--scenario", type=str, default=None, help="Filter by scenario code (e.g. S1, S8)")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent worker threads (default: 3)")
    args = parser.parse_args()

    run_benchmark(suite_idx=args.suite, sample_size=args.sample, target_scenario=args.scenario, max_workers=args.workers)
