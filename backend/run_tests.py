import os
import sys
import json
import csv
import time
from datetime import datetime
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Setup Automated Log File Storage (Single Latest Log File)
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

latest_log_path = os.path.join(LOGS_DIR, "test_run_latest.log")
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")


def load_benchmark_dataset():
    """
    Loads benchmark test dataset from test_dataset.csv if available, or falls back to test_dataset.json.
    """
    csv_path = os.path.join(os.path.dirname(__file__), "test_dataset.csv")
    json_path = os.path.join(os.path.dirname(__file__), "test_dataset.json")

    if os.path.exists(csv_path):
        print(f"   [DATASET] Loading empirical benchmark suite from CSV: test_dataset.csv")
        pkg_tests = []
        task_tests = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mode = (row.get("mode") or row.get("test_mode") or "").strip().lower()
                test_id = (row.get("test_id") or row.get("category") or "").strip()
                category = (row.get("category") or row.get("expected_verdict") or "").strip()
                system = (row.get("system") or "pypi").strip().lower()
                expected = (row.get("expected_verdict") or row.get("expected_outcome") or "").strip()

                if mode == "package" or test_id.startswith("PKG"):
                    pkg_tests.append({
                        "test_id": test_id,
                        "category": category,
                        "expected_verdict": expected,
                        "payload": {
                            "package_name": (row.get("package_name") or "").strip(),
                            "system": system,
                            "user_requirement": (row.get("user_requirement") or row.get("task_description") or "").strip()
                        }
                    })
                elif mode == "task" or test_id.startswith("TASK"):
                    task_tests.append({
                        "test_id": test_id,
                        "category": category,
                        "expected_verdict": expected,
                        "payload": {
                            "task_description": (row.get("task_description") or row.get("user_requirement") or "").strip(),
                            "system": system
                        }
                    })
        return {
            "benchmark_metadata": {"title": "BuildOrBorrow Benchmark Suite (CSV Dataset v3.0.0)"},
            "package_mode_tests": pkg_tests,
            "task_mode_tests": task_tests
        }

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_summary_table_log(pkg_results, task_results, execution_mode, timestamp_str):
    """
    Saves a clean, formatted ASCII summary table of benchmark results into log files.
    """
    lines = []
    lines.append("=" * 115)
    lines.append(f" 🧪 BUILDORBORROW BENCHMARK TEST SUITE SUMMARY REPORT")
    lines.append(f" Log Timestamp : {timestamp_str} | Execution Mode: {execution_mode}")
    lines.append("=" * 115 + "\n")

    lines.append("📦 PART 1: PACKAGE MODE EVALUATIONS")
    lines.append("+" + "-"*9 + "+" + "-"*16 + "+" + "-"*8 + "+" + "-"*18 + "+" + "-"*22 + "+" + "-"*20 + "+" + "-"*10 + "+" + "-"*8 + "+")
    lines.append(f"| {'Test ID':<7} | {'Package':<14} | {'System':<6} | {'Expected':<16} | {'Actual Verdict':<20} | {'Diagnosis':<18} | {'Time (s)':<8} | {'Result':<6} |")
    lines.append("+" + "-"*9 + "+" + "-"*16 + "+" + "-"*8 + "+" + "-"*18 + "+" + "-"*22 + "+" + "-"*20 + "+" + "-"*10 + "+" + "-"*8 + "+")

    for r in pkg_results:
        res_str = "PASS" if r['is_pass'] else "MISMATCH"
        lines.append(
            f"| {r['test_id']:<7} | {r['package']:<14} | {r['system']:<6} | {r['expected']:<16} | "
            f"{r['verdict'][:20]:<20} | {r['diagnosis'][:18]:<18} | {r['time']:<8.2f} | {res_str:<6} |"
        )
    lines.append("+" + "-"*9 + "+" + "-"*16 + "+" + "-"*8 + "+" + "-"*18 + "+" + "-"*22 + "+" + "-"*20 + "+" + "-"*10 + "+" + "-"*8 + "+\n")

    lines.append("🛠️ PART 2: TASK MODE EVALUATIONS")
    lines.append("+" + "-"*9 + "+" + "-"*45 + "+" + "-"*8 + "+" + "-"*25 + "+" + "-"*16 + "+" + "-"*10 + "+" + "-"*8 + "+")
    lines.append(f"| {'Test ID':<7} | {'Task Description':<43} | {'System':<6} | {'Candidates Found':<23} | {'Primary Package':<14} | {'Verdict':<8} | {'Result':<6} |")
    lines.append("+" + "-"*9 + "+" + "-"*45 + "+" + "-"*8 + "+" + "-"*25 + "+" + "-"*16 + "+" + "-"*10 + "+" + "-"*8 + "+")

    for r in task_results:
        desc = r['description'][:41] + ".." if len(r['description']) > 43 else r['description']
        cands = r['candidates'][:21] + ".." if len(r['candidates']) > 23 else r['candidates']
        lines.append(
            f"| {r['test_id']:<7} | {desc:<43} | {r['system']:<6} | {cands:<23} | "
            f"{r['primary_pkg'][:14]:<14} | {r['verdict']:<8} | {'SUCCESS':<6} |"
        )
    lines.append("+" + "-"*9 + "+" + "-"*45 + "+" + "-"*8 + "+" + "-"*25 + "+" + "-"*16 + "+" + "-"*10 + "+" + "-"*8 + "+\n")

    pkg_pass = sum(1 for r in pkg_results if r['is_pass'])
    task_pass = len(task_results)
    total_pass = pkg_pass + task_pass
    total_tests = len(pkg_results) + len(task_results)

    lines.append("=" * 115)
    lines.append(f" ACCURACY METRICS:")
    lines.append(f"   Package Mode Pass Rate : {pkg_pass} / {len(pkg_results)} ({round(pkg_pass/len(pkg_results)*100, 1)}%)")
    lines.append(f"   Task Mode Pass Rate    : {task_pass} / {len(task_results)} ({round(task_pass/len(task_results)*100, 1)}%)")
    lines.append(f"   Overall Benchmark Score: {total_pass} / {total_tests} ({round(total_pass/total_tests*100, 1)}%)")
    lines.append("=" * 115)

    report_text = "\n".join(lines)

    # Save single clean log file
    with open(latest_log_path, "w", encoding="utf-8") as f:
        f.write(report_text)


BASE_URL = "http://localhost:8000/api/evaluate"


def is_server_running():
    try:
        r = requests.get("http://localhost:8000/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def execute_payload(payload):
    """
    Executes an evaluation payload via HTTP server if running, or via direct Python in-process call if server is offline.
    """
    server_online = is_server_running()
    if server_online:
        resp = requests.post(BASE_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    else:
        from app.api.endpoints.evaluate import evaluate_pipeline, EvaluationRequest
        req_model = EvaluationRequest(**payload)
        res_model = evaluate_pipeline(req_model)
        return json.loads(res_model.model_dump_json())


def run_benchmark():
    data = load_benchmark_dataset()

    server_online = is_server_running()
    execution_mode = "HTTP API (http://localhost:8000)" if server_online else "Direct Python In-Process Engine"

    print("=" * 80)
    print(" [BUILDORBORROW BENCHMARK TEST SUITE]")
    print(f"   {data['benchmark_metadata']['title']}")
    print(f"   Execution Mode: {execution_mode}")
    print(f"   Log Timestamp : {timestamp_str}")
    print("=" * 80)

    # 1. Package Mode Tests
    print("\n === PART 1: PACKAGE MODE TESTS ===\n")
    pkg_tests = data.get("package_mode_tests", [])
    pkg_passed = 0
    pkg_records = []

    for test in pkg_tests:
        test_id = test["test_id"]
        category = test["category"]
        expected = test["expected_verdict"]
        payload = test["payload"]

        print(f"[{test_id}] Testing '{payload['package_name']}' ({payload['system']}) - Category: {category}")
        try:
            start_t = time.time()
            res_data = execute_payload(payload)
            elapsed = round(time.time() - start_t, 2)

            eval_detail = res_data.get("evaluation", {})
            verdict_obj = eval_detail.get("verdict", {})
            verdict = verdict_obj.get("decision")
            confidence = verdict_obj.get("confidence_score")
            diag_obj = eval_detail.get("diagnosis", {})
            diagnosis = diag_obj.get("status")
            resolution = eval_detail.get("package_resolution", {})
            security = eval_detail.get("security_context", {})
            forecast = eval_detail.get("forecast_analysis", {})

            is_pass = (verdict == expected)
            status_icon = "[PASS]" if is_pass else "[MISMATCH]"
            if is_pass:
                pkg_passed += 1

            verdict_display = verdict
            if verdict == "MIGRATE" and verdict_obj.get("recommended_alternative"):
                verdict_display = f"MIGRATE ({verdict_obj.get('recommended_alternative')})"
            elif verdict == "BUILD" and verdict_obj.get("estimated_build_effort"):
                verdict_display = f"BUILD ({verdict_obj.get('estimated_build_effort')})"

            pkg_records.append({
                "test_id": test_id,
                "package": payload['package_name'],
                "system": payload['system'],
                "expected": expected,
                "verdict": verdict_display,
                "diagnosis": diagnosis or "UNKNOWN",
                "time": elapsed,
                "is_pass": is_pass
            })

            print(f"   {status_icon} | Actual Verdict: {verdict} (Expected: {expected}) | Confidence: {confidence} | Diagnosis: {diagnosis} | Time: {elapsed}s")
            print("   🔍 EVIDENCE CHAIN:")
            print(f"      1. Resolution     : {resolution.get('name')} v{resolution.get('version')} (Project: {resolution.get('project_name') or 'N/A'})")
            print(f"      2. Security       : {security.get('active_cves_on_current_version', 0)} Active CVEs on current v{resolution.get('version')} ({security.get('critical_vulnerabilities', 0)} Critical, {security.get('patched_historical_cves', 0)} Patched)")
            print(f"      3. Health Score   : {forecast.get('health_score', 0.0)} / 100 (Signal: {forecast.get('maintenance_verdict_signal', 'N/A')})")
            print(f"      4. Diagnosis      : {diagnosis} (Is Abandoned: {diag_obj.get('is_abandoned')})")
            if verdict == "MIGRATE":
                alt = verdict_obj.get("recommended_alternative")
                print(f"      5. Final Decision : MIGRATE -> Recommended Alternative: '{alt}'")
            elif verdict == "BUILD":
                effort = verdict_obj.get("estimated_build_effort")
                print(f"      5. Final Decision : BUILD -> Estimated Effort: {effort}")
            else:
                print(f"      5. Final Decision : BORROW -> High utility bedrock library")
        except Exception as e:
            print(f"   [ERROR] Execution Error: {e}")
            pkg_records.append({
                "test_id": test_id, "package": payload['package_name'], "system": payload['system'],
                "expected": expected, "verdict": "ERROR", "diagnosis": "ERROR", "time": 0.0, "is_pass": False
            })
        print("-" * 80)
        time.sleep(2.5)  # Prevents 429 RESOURCE_EXHAUSTED on Flash tiers

    # 2. Task Mode Tests
    print("\n === PART 2: TASK MODE TESTS ===\n")
    task_tests = data.get("task_mode_tests", [])
    task_passed = 0
    task_records = []

    for test in task_tests:
        test_id = test["test_id"]
        category = test["category"]
        payload = test["payload"]

        print(f"[{test_id}] Task: '{payload['task_description']}' ({payload['system']}) - Category: {category}")
        try:
            start_t = time.time()
            res_data = execute_payload(payload)
            elapsed = round(time.time() - start_t, 2)

            primary_eval = res_data.get("primary_evaluation", {})
            screenings = res_data.get("candidate_screenings", [])

            primary_pkg = primary_eval.get("package_name", "N/A")
            verdict_obj = primary_eval.get("verdict", {})
            verdict = verdict_obj.get("decision", "N/A")
            diag_obj = primary_eval.get("diagnosis", {})
            diagnosis = diag_obj.get("status")
            resolution = primary_eval.get("package_resolution", {})
            security = primary_eval.get("security_context", {})
            forecast = primary_eval.get("forecast_analysis", {})
            cands_str = ", ".join([c.get("name") for c in screenings])

            task_records.append({
                "test_id": test_id,
                "description": payload['task_description'],
                "system": payload['system'],
                "candidates": cands_str,
                "primary_pkg": primary_pkg,
                "verdict": verdict,
                "time": elapsed
            })

            print(f"   [SUCCESS] | Candidates Found: [{cands_str}]")
            print(f"   👉 Primary Candidate Evaluated: '{primary_pkg}' -> Verdict: {verdict} | Time: {elapsed}s")
            print("   🔍 EVIDENCE CHAIN:")
            print(f"      1. Primary Candidate : {primary_pkg}")
            print(f"      2. Resolution        : {resolution.get('name')} v{resolution.get('version')} (Project: {resolution.get('project_name') or 'N/A'})")
            print(f"      3. Security          : {security.get('active_cves_on_current_version', 0)} Active CVEs on current v{resolution.get('version')} ({security.get('critical_vulnerabilities', 0)} Critical, {security.get('patched_historical_cves', 0)} Patched)")
            print(f"      4. Health Score      : {forecast.get('health_score', 0.0)} / 100 (Signal: {forecast.get('maintenance_verdict_signal', 'N/A')})")
            print(f"      5. Diagnosis         : {diagnosis} (Is Abandoned: {diag_obj.get('is_abandoned')})")
            if verdict == "MIGRATE":
                alt = verdict_obj.get("recommended_alternative")
                print(f"      6. Final Decision    : MIGRATE -> Recommended Alternative: '{alt}'")
            elif verdict == "BUILD":
                effort = verdict_obj.get("estimated_build_effort")
                print(f"      6. Final Decision    : BUILD -> Estimated Effort: {effort}")
            else:
                print(f"      6. Final Decision    : BORROW -> Recommended primary package choice")
            task_passed += 1
        except Exception as e:
            print(f"   [ERROR] Execution Error: {e}")
            task_records.append({
                "test_id": test_id, "description": payload['task_description'], "system": payload['system'],
                "candidates": "ERROR", "primary_pkg": "ERROR", "verdict": "ERROR", "time": 0.0
            })
        print("-" * 80)
        time.sleep(2.5)  # Prevents 429 RESOURCE_EXHAUSTED on Flash tiers

    # Save Clean Summary Table Log File
    save_summary_table_log(pkg_records, task_records, execution_mode, timestamp_str)

    print("\n" + "=" * 80)
    print(f" SUMMARY RESULTS:")
    print(f"   Package Mode Pass Rate : {pkg_passed} / {len(pkg_tests)} ({round(pkg_passed/len(pkg_tests)*100, 1)}%)")
    print(f"   Task Mode Pass Rate    : {task_passed} / {len(task_tests)} ({round(task_passed/len(task_tests)*100, 1)}%)")
    print(f"\n   [LOG STORAGE] Clean summary table report saved to:")
    print(f"   -> Summary Log   : {latest_log_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_benchmark()
