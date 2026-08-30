# BuildOrBorrow Architecture & Pipeline Follow-Ups

This document outlines key technical follow-ups and architectural enhancements identified for the **BuildOrBorrow** decision engine pipeline.

---

## 1. ⚡ GH Archive Zero-Activity Pre-Check Before Running ARIMA Model

### **Problem Statement:**
Currently, when a repository has 0 commits or 0 developer events across the historical lookback window (e.g. 104 weeks), the pipeline still attempts to fit Statsmodels / BigQuery ML ARIMA forecasting models. Running time-series models on zero-variance or empty arrays wastes CPU execution time, incurs unnecessary BigQuery ML query costs, and produces convergence warnings.

### **Proposed Enhancement:**
- **Pre-Check Filter**: Before invoking ARIMA model training or forecasting routines (`query_arima_plus_forecast()` / statistical fallback), inspect the retrieved weekly activity array.
- **Bypass Rule**: If `sum(total_events) == 0` or if historical data points are empty across the lookback period:
  1. Bypass ARIMA model fitting immediately.
  2. Directly set `health_score = 0.0`, `trend_direction = 'DECLINING'`, and `maintenance_verdict_signal = 'AT_RISK_STAGNANT'`.
  3. Inject an explicit `zero_activity_stagnant: True` boolean flag directly into the payload sent to the **Diagnosis Agent** and **Verdict Agent**.

---

## 2. 🏷️ GitHub Public "Archived" Tag Detection (`archived == True`)

### **Problem Statement:**
GitHub allows repository owners to mark a repository as officially **Archived** (read-only mode). An archived repository is a 100% definitive, deterministic signal that the project has stopped maintenance permanently and will never receive security patches or feature updates.

### **Proposed Enhancement:**
- **REST Metadata Inspection**: Include a check for the `archived` property from the GitHub API repository endpoint (`GET /repos/{owner}/{repo}`).
- **Deterministic Signal Injection**: If `archived == True`:
  1. Set `is_abandoned = True` and status `ABANDONED_STRUGGLING` immediately.
  2. Override standard confidence calculations to enforce a 100% confidence factor: `"+ Official GitHub Repository status is ARCHIVED (read-only)"`.
  3. Force the **Verdict Agent** decision to **`MIGRATE`** (if an active alternative exists) or **`BUILD`** (if requirement is light).

---

## 3. 🔍 GH Archive Event Tracking Audit & Weighting Analysis

### **Current Event Query Audit ([`gh_archive.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/queries/gh_archive.py)):**
The BigQuery query currently scans the following event types:

```sql
SELECT
  TIMESTAMP_TRUNC(created_at, WEEK) AS week_start,
  COUNTIF(type = 'PushEvent') AS push_events,
  COUNTIF(type = 'PullRequestEvent') AS pr_events,
  COUNTIF(type = 'IssuesEvent') AS issue_events,
  COUNTIF(type = 'WatchEvent') AS star_events,
  COUNT(DISTINCT actor.id) AS active_contributors,
  COUNT(1) AS total_events,
  CAST(
    (COUNTIF(type = 'PushEvent') * 3.0) +
    (COUNTIF(type = 'PullRequestEvent') * 2.0) +
    (COUNTIF(type = 'IssuesEvent') * 1.0)
    AS FLOAT64
  ) AS weighted_activity
FROM `githubarchive.month.*`
WHERE type IN ('PushEvent', 'PullRequestEvent', 'IssuesEvent', 'WatchEvent')
```

### **Audit Findings & Proposed Refinements:**

1. **Current Weights**:
   - **`PushEvent` (Weight: 3.0)**: Represents direct code commits pushed to repository branches.
   - **`PullRequestEvent` (Weight: 2.0)**: Represents PR openings, merges, and reviews.
   - **`IssuesEvent` (Weight: 1.0)**: Represents issue creation and management.
   - **`WatchEvent` (Weight: 0.0)**: Tracks repository star activity (excluded from weighted activity calculation to avoid vanity star inflation).

2. **Additional Maintenance Events to Track**:
   - **`CreateEvent` (Tag / Release Creations)**: Creating git tags/releases is a high-value signal of maintainer activity. Recommend adding `CreateEvent` with weight `3.0`.
   - **`IssueCommentEvent` / `PullRequestReviewCommentEvent`**: Maintainer discussions on open issues and PR reviews reflect active community triage. Recommend adding with weight `1.0`.

3. **Automated Bot Filtering**:
   - Filter out automated bot activity (e.g., Dependabot, Renovate, GitHub Actions bots) by applying `AND actor.login NOT LIKE '%[bot]'` in the BigQuery `WHERE` clause so bot dependency bumps do not inflate genuine human maintenance scores.

---

## 4. 📅 Direct 104-Week Lookback Horizon (No Custom Dataset / No Batch Jobs Needed)

### **Rationale:**
- **Why 104 Weeks (2 Years) is Required**: Short lookback windows (e.g. 5–12 weeks) fail for stable, mature packages (like `tone.js` or `feedparser`) where recent 3-month activity happens to be 0. A short lookback returns 0 events and causes the forecasting engine to output 0 activity.
- **Direct Query Model**: No custom BigQuery dataset and no monthly batch cron jobs are required.
- **Execution Plan**: Configure `DEFAULT_LOOKBACK_WEEKS = 104` directly in `config.py` for direct GH Archive querying (`githubarchive.month.*`), retrieving the full 2-year maintenance history so forecasting accurately captures long-term health without needing extra database infrastructure.

---

## 5. 👆 Interactive Candidate Re-Evaluation Action in Candidate Discovery Grid

### **Feature Intent:**
In **Task Requirement Mode**, the AI Candidate Finder selects 3 package candidates (1 primary candidate selected for deep pipeline evaluation + 2 runner-up candidates displayed as screening cards).

### **Proposed Enhancement:**
- **"Run Evaluation Pipeline" Chip/Button**: Add a 1-click **`"Run Evaluation Pipeline for this Package"`** action button to the screening cards of the non-selected runner-up candidates in [`CandidateGrid.tsx`](file:///d:/Downloads/patchamomma/buildOrBorrow/frontend/src/components/verdict/CandidateGrid.tsx).
- **Execution Payload**:
  - `package_name` = Candidate package name (e.g., `faster-whisper`).
  - `system` = Current ecosystem (e.g., `pypi`).
  - `user_requirement` = Original task requirement entered by the user (e.g., `translate audio files`).
- **User UX Flow**: Clicking the button immediately triggers `evaluate_single_package_pipeline` for that specific candidate package without requiring the user to manually re-type the package name into Exact Package Mode!

---

## 6. 🛡️ Distinguish Active Unpatched CVEs (Latest Release) vs Historical Patched CVEs

### **Problem & Industry Context:**
Popular, foundational libraries (like `axios`, `express`, `lodash`, `requests`, `urllib3`) have been maintained for 10+ years. Over a decade, security researchers discover historical CVEs, which maintainers **promptly patch in subsequent releases**.
- The presence of **historical patched CVEs** is a sign of **active security stewardship**, NOT a reason to abandon a library!
- Only **active, unpatched CVEs on the current latest release** represent real security risk.

### **Proposed Refinement:**
- **Version Scoping**: In `deps_dev.py` and `verdict.py`, explicitly separate `active_cves_on_current_version` from `historical_patched_cves`.
- **Verdict Rule Adjustment**:
  1. If `active_cves_on_current_version == 0` (even if historical total $> 0$), permit **`BORROW`** and include an audit note: *`"0 active CVEs on latest v1.7.9 (14 historical CVEs fully patched)"`*.
  2. Only trigger **`MIGRATE`** if `active_cves_on_current_version > 0` (an unpatched vulnerability remains open on the current release).

---

## 7. 📌 Safe Version Pinning Strategy (0 Extra Queries In-Memory Implementation)

### **Problem Statement:**
When the latest release version of a healthy package (e.g. `v2.4.0`) contains a newly reported vulnerability, how far back in version history should the system look to recommend a safe stable version?

### **Proposed Boundary Rules & 0-Extra-Query Implementation:**
1. **0 Extra Queries Optimization**:
   - The existing `deps.dev` `Advisories` query already returns `pkg.AffectedVersions` (e.g. `">= 2.1.0"`).
   - In Python, evaluate the already-retrieved version history list in memory against `AffectedVersions` (0 extra BigQuery calls, 0 extra bytes scanned!).
2. **SemVer Major Version Constraint (No Breaking Changes)**:
   - Stay within the **same Major version branch** (`v2.x`).
   - Recommending a version in the same Major branch guarantees 100% code compatibility for the user.
3. **12-Month Recency Horizon**:
   - Do NOT suggest versions published **more than 12 months ago**.
4. **Fallback to MIGRATE**:
   - If no vulnerability-free version exists within the same Major branch in the last 12 months, abort version pinning and trigger **`MIGRATE`** to an active alternative library.

---

## 8. 🤖 Replace Hardcoded Static Package Lists with Dynamic LLM Classification

### **Problem Statement:**
Currently, [`verdict.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/agents/verdict.py#L98-L135) contains static Python arrays (`deprecated_map` and `micro_utils`). Hardcoding package names in backend code limits the system to packages explicitly typed into the codebase.

### **Proposed Enhancement:**
- Remove hardcoded static arrays from backend Python files.
- Prompt Gemini 3.6 Flash in the **Verdict Agent** to dynamically classify packages as **micro-utilities** (under 25 LOC) or **deprecated/superseded packages** across **any ecosystem** (NPM, PyPI, Cargo, Go, Maven) based on code footprint, package metadata, and ecosystem context.

---

## 9. 📊 BigQuery SQL Query Optimization Strategy (Derived via `/bigquery-sql` Skill Audit)

### **Audit Analysis (Using `/bigquery-sql` Skill Rules):**
1. **Column Pruning in `deps_dev.py`**: Prune unused `Version` column from `target_project` CTE in `query_package_resolution()`.
2. **Common Subexpression Reuse in `gh_archive.py`**: Refactor `COUNTIF(type = 'PushEvent')`, `COUNTIF(type = 'PullRequestEvent')`, and `COUNTIF(type = 'IssuesEvent')` into a `weekly_counts` CTE to prevent BigQuery from evaluating `COUNTIF` multiple times per row.
3. **Approximate Distinct Aggregation (`APPROX_COUNT_DISTINCT`)**: Replace exact `COUNT(DISTINCT actor.id)` and `COUNT(DISTINCT Dependency.Name)` with `APPROX_COUNT_DISTINCT(...)` to slash worker memory usage and accelerate multi-gigabyte queries.

---

## 10. ⚡ Early Fast-Path "BUILD" Bypass for Micro-Utilities (< 25 LOC)

### **Problem Statement:**
When a user asks for a trivial helper (e.g. *"left pad a string"*, *"slugify text"*, *"check if a number is even"*, *"clamp float between min/max"*), running a full 104-week BigQuery GH Archive query, fitting Statsmodels/ARIMA ML models, and scanning security advisories wastes execution time (~3–5s) and incurs unnecessary query costs for a 5-line function.

### **Proposed Fast-Path Bypass:**
1. **Early Classifier Filter**: Before triggering expensive BigQuery queries or time-series forecasting, inspect if the task requirement represents a lightweight micro-utility under ~25 lines of code.
2. **Instant Pipeline Bypass**:
   - Bypass BigQuery GH Archive activity scanning and ARIMA ML fitting.
   - Instantly issue a **`BUILD`** decision: *"Feature requirement is a lightweight micro-utility (< 25 LOC). Building directly avoids third-party dependency bloat, transitive dependencies, and supply-chain vulnerability risks."*
3. **Instant Code Generation**:
   - Instantly invoke the **Builder Agent** to generate the clean, zero-dependency Python/JS snippet + unit test on the spot (< 500ms total latency!).

---

## 11. 🚀 Bypass Diagnosis Agent & Pass Direct Input to Verdict Agent when `github_url == null`

### **Architectural Insight:**
When a package has `github_url == null` (or resolution fails/package does not exist), GH Archive and GitHub API queries are already safely bypassed (`raw_weekly_data = []`, `recent_issues = []`). No GitHub API calls or BigQuery bytes are wasted.

### **Problem Statement:**
Currently, when `github_url == null`, the forecasting engine returns default fallback scores (`health_score: 75`). The pipeline passes these dummy numbers to the **Diagnosis Agent**, causing it to hallucinate that non-existent packages (e.g. `add2ints`) are *"mature, stable packages with a 75 health score"*, which directly contradicts the **Verdict Agent**!

### **Proposed Architectural Flow:**
When `github_url == null` or requirement is a native language capability / micro-task:
1. **Bypass Diagnosis Agent**: Skip calling the Diagnosis Agent entirely (do not generate fake health diagnoses for non-existent libraries).
2. **Direct Verdict Payload**: Pass a clean, explicit context payload directly to the **Verdict Agent**:
   ```json
   {
     "package_exists": false,
     "github_url": null,
     "user_requirement": "add 2 integers",
     "is_native_capability": true
   }
   ```
3. **Clean Verdict & Builder Execution**:
   - **Verdict Agent** immediately outputs **`BUILD`**: *"The requirement 'add 2 integers' is a native language operation. Third-party packages are unnecessary."*
   - **Builder Agent** generates `return a + b` in **< 300ms** with **0 agent contradictions**!

---

## 12. 🧰 Antigravity Automated Audit Toolkit Integration

### **Available Specialized Audit Workflows:**
1. **`/ml-best-practices` (Machine Learning & Forecasting Audit)**:
   - Audits statistical forecasting engine ([`forecasting.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/services/forecasting.py)), OLS trend slope calculations, 90-day confidence bounds, and ARIMA model accuracy metrics.
2. **`/building-data-apps` (Full-Stack Data App Architecture)**:
   - Audits end-to-end data pipeline flow from BigQuery datasets $\rightarrow$ FastAPI backend $\rightarrow$ React Vite UI.
3. **`/managing-python-dependencies` (Python Dependency Health)**:
   - Scans backend Python requirements ([`requirements.txt`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/requirements.txt)) and virtual environment isolation.
4. **`/gcloud-auth-verification` (GCP Auth & BigQuery Quotas)**:
   - Verifies Application Default Credentials (ADC), BigQuery authentication, project scoping, and query byte limits ([`bigquery.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/core/bigquery.py)).
5. **`/discovering-gcp-data-assets` (GCP Data Asset Inspection)**:
   - Inspects schema definitions, table partitions, and cost bounds for `deps_dev_v1` and `githubarchive.month.*`.
6. **`/chrome-devtools` & `/a11y-debugging` (Accessibility & Browser Performance Audit)**:
   - Performs automated Chrome DevTools browser testing on [http://localhost:3000](http://localhost:3000) for ARIA compliance, keyboard focus traps, and rendering latency.

---

## 13. 🔑 GitHub REST API Authentication Header (`GITHUB_TOKEN`)

### **Problem Statement:**
Currently, REST calls to the GitHub API (`api.github.com/repos/...` and `api.github.com/repos/.../issues`) in [`github_issues.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/services/github_issues.py) are sent unauthenticated.

### **Rate Limit Risk:**
- GitHub enforces a strict **60 requests/hour per IP address** rate limit for unauthenticated REST API calls.
- In production or multi-user testing environments, running 15-20 searches quickly exhausts the 60-request quota, resulting in `HTTP 403 Rate Limit Exceeded` errors.

### **Proposed Enhancement:**
- Add an optional `GITHUB_TOKEN: Optional[str] = None` setting in [`config.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/core/config.py).
- In [`github_issues.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/services/github_issues.py), attach `headers={"Authorization": f"token {settings.GITHUB_TOKEN}"}` if configured.
- Attaching a GitHub Personal Access Token raises the API rate limit from **60 requests/hour to 5,000 requests/hour**!

---

## 14. 🎯 Automated Candidate Verification Filter (`verified_exists == True`) in Candidate Finder

### **Problem Statement:**
In Task Requirement Mode, the Candidate Finder LLM occasionally suggests candidate package names that do not exist on the target ecosystem registry (PyPI/NPM), returning `verified_exists: false` (e.g. `add2ints`, `mathutils-plus`, `simple-adder`).

### **Proposed Enhancement:**
- **Existence Filter**: In [`candidate_finder.py`](file:///d:/Downloads/patchamomma/buildOrBorrow/backend/app/agents/candidate_finder.py), filter the screened candidate list to ensure `verified_exists == True` before selecting a primary package for deep pipeline evaluation.
- **Micro-Task Fallback**: If 0 candidates have `verified_exists == True`, automatically trigger the **Native Micro-Task Fast-Path** (Item 10) to issue **`BUILD`** without running deep pipeline evaluations on fake package names.

---

## 15. 🏆 OpenSSF & `deps.dev` Automated Validation Benchmark Integration

### **Value Proposition Differentiation:**
While raw data platforms like **OpenSSF Scorecards** (`openssf:scorecardcron.scorecard-v2`) and **`deps.dev`** output passive security metrics (e.g., `4.2/10`), **BuildOrBorrow** acts as the actionable **AI Decision & Code Generation Engine** that transforms raw data into `BORROW`, `MIGRATE`, or `BUILD` verdicts and generates custom zero-dependency code snippets on the spot.

### **Proposed Validation Suite (`backend/scripts/benchmark_validation.py`):**
- **Validation Dataset**: Query `https://api.securityscorecards.dev/projects/github.com/{owner}/{repo}` to extract official ground-truth OpenSSF scores (0-10) for top 100 packages across PyPI, NPM, Cargo, Go, and Maven.
- **Decision Accuracy Benchmark**: Compare BuildOrBorrow's 90-day predicted health scores (`0-100`) and verdicts (`BORROW`, `MIGRATE`, `BUILD`) against OpenSSF maintainer scores and `deps.dev` advisory data.
- **Accuracy Metric Output**: Output automated benchmark reports calculating Verdict Accuracy Rate (`%`), Pipeline Latency (`s`), and Code Generation Success Rate (`%`).
