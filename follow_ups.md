# BuildOrBorrow Architecture & Pipeline Follow-Ups

This document outlines key technical follow-ups and architectural enhancements identified for the **BuildOrBorrow** decision engine pipeline.

---

## 1. ⚡ GH Archive Zero-Activity Pre-Check Before Running ARIMA Model [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> Implemented in [`backend/app/api/endpoints/evaluate.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/api/endpoints/evaluate.py) and [`backend/app/api/endpoints/forecast.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/api/endpoints/forecast.py). Before invoking BigQuery ML `ARIMA_PLUS`, the pipeline checks if `sum(total_events) == 0`. If dormant/stagnant, it immediately sets `health_score = 0.0`, `trend_direction = 'DECLINING'`, and `maintenance_verdict_signal = 'AT_RISK_STAGNANT'`, completely bypassing ML model fitting and eliminating unnecessary training costs and warnings.

### **Problem Statement:**
Currently, when a repository has 0 commits or 0 developer events across the historical lookback window (e.g. 104 weeks), the pipeline still attempts to fit Statsmodels / BigQuery ML ARIMA forecasting models. Running time-series models on zero-variance or empty arrays wastes CPU execution time, incurs unnecessary BigQuery ML query costs, and produces convergence warnings.

### **Proposed Enhancement:**
- **Pre-Check Filter**: Before invoking ARIMA model training or forecasting routines (`query_arima_plus_forecast()` / statistical fallback), inspect the retrieved weekly activity array.
- **Bypass Rule**: If `sum(total_events) == 0` or if historical data points are empty across the lookback period:
  1. Bypass ARIMA model fitting immediately.
  2. Directly set `health_score = 0.0`, `trend_direction = 'DECLINING'`, and `maintenance_verdict_signal = 'AT_RISK_STAGNANT'`.
  3. Inject an explicit `zero_activity_stagnant: True` boolean flag directly into the payload sent to the **Diagnosis Agent** and **Verdict Agent**.

---

## 2. 🏷️ GitHub Public "Archived" Tag Detection (`archived == True`) (Done ✅)

### **Problem Statement:**
GitHub allows repository owners to mark a repository as officially **Archived** (read-only mode). An archived repository is a 100% definitive, deterministic signal that the project has stopped maintenance permanently and will never receive security patches or feature updates.

### **Proposed Enhancement:**
- **REST Metadata Inspection**: Include a check for the `archived` property from the GitHub API repository endpoint (`GET /repos/{owner}/{repo}`).
- **Deterministic Signal Injection**: If `archived == True`:
  1. Set `is_abandoned = True` and status `ABANDONED_STRUGGLING` immediately.
  2. Override standard confidence calculations to enforce a 100% confidence factor: `"+ Official GitHub Repository status is ARCHIVED (read-only)"`.
  3. Force the **Verdict Agent** decision to **`MIGRATE`** (if an active alternative exists) or **`BUILD`** (if requirement is light).

---

## 3. 🔍 GH Archive Event Tracking Audit & Weighting Analysis [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> Extended event tracking schema in [`models/gh_archive.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/models/gh_archive.py) and queries in [`queries/gh_archive.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/queries/gh_archive.py). Included `create_events` (tags/releases, weight 3.0), `comment_events` (triage discussions, weight 1.0), and composite `weighted_activity`. Excluded automated bots (`actor.login NOT LIKE '%[bot]'`), and fully baked these aggregated metrics into the warehouse table `build_or_borrow_dw.github_weekly_activity`.

### **Current Event Query Audit ([`gh_archive.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/queries/gh_archive.py)):**
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

## 4. 📅 Direct 104-Week Lookback Horizon (Custom Dataset Integration) [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> Configured `DEFAULT_LOOKBACK_WEEKS = 104` in [`config.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/core/config.py) and connected backend directly to `project-bbc67fb6-4e57-4565-bb5.build_or_borrow_dw.github_weekly_activity` (17.3M rows, August 2024 to August 2026). Removed in-memory Python caching for stateless execution and implemented 0-byte inline UNNEST BigQuery ML `ARIMA_PLUS` training and inference.

### **Rationale:**
- **Why 104 Weeks (2 Years) is Required**: Short lookback windows (e.g. 5–12 weeks) fail for stable, mature packages (like `tone.js` or `feedparser`) where recent 3-month activity happens to be 0. A short lookback returns 0 events and causes the forecasting engine to output 0 activity.
- **Direct Query Model**: No custom BigQuery dataset and no monthly batch cron jobs are required.
- **Execution Plan**: Configure `DEFAULT_LOOKBACK_WEEKS = 104` directly in `config.py` for direct GH Archive querying (`githubarchive.month.*`), retrieving the full 2-year maintenance history so forecasting accurately captures long-term health without needing extra database infrastructure.

---

## 5. 👆 Interactive Candidate Re-Evaluation Action in Candidate Discovery Grid [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> - **1-Click Candidate Selection**: Added **`"Run Deep Pipeline"`** action button and active loading state (`Loader2` spinner) to non-selected candidate cards in [`CandidateGrid.tsx`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/frontend/src/components/verdict/CandidateGrid.tsx).
> - **Global Session-Wide Caching**: Configured `globalPackageCache` in [`App.tsx`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/frontend/src/App.tsx) to persist evaluated packages across searches during the entire browser session. Switching to previously evaluated packages loads **instantly (0ms latency, $0 API cost, 0 BigQuery bytes)** and displays a green **`"View Cached Analysis"`** badge.
> - **Backend Fast-Path Query Reuse**: Added `cached_github_url` to `EvaluationRequest` payload in [`evaluate.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/api/endpoints/evaluate.py), bypassing GitHub URL resolution wait times (~300ms latency reduction).
> - **UX Auto-Scroll Anchor**: Added `verdictRef` smooth scroll anchor (`scrollIntoView({ behavior: 'smooth' })`) to focus user attention on the updated Verdict Hero Card upon candidate selection.

### **Feature Intent:**
In **Task Requirement Mode**, the AI Candidate Finder selects 3 package candidates (1 primary candidate selected for deep pipeline evaluation + 2 runner-up candidates displayed as screening cards).

### **Proposed Enhancement:**
- **"Run Evaluation Pipeline" Chip/Button**: Add a 1-click **`"Run Evaluation Pipeline for this Package"`** action button to the screening cards of the non-selected runner-up candidates in [`CandidateGrid.tsx`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/frontend/src/components/verdict/CandidateGrid.tsx).
- **Execution Payload**:
  - `package_name` = Candidate package name (e.g., `faster-whisper`).
  - `system` = Current ecosystem (e.g., `pypi`).
  - `user_requirement` = Original task requirement entered by the user (e.g., `translate audio files`).
- **User UX Flow**: Clicking the button immediately triggers `evaluate_single_package_pipeline` for that specific candidate package without requiring the user to manually re-type the package name into Exact Package Mode!

---

## 6. 🛡️ Distinguish Active Unpatched CVEs (Latest Release) vs Historical Patched CVEs [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> - **Version Scoped Advisory Breakdown**: Implemented `active_cves_on_current_version` and `patched_historical_cves` in [`deps_dev.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/queries/deps_dev.py).
> - **Stewardship Rule**: Historical patched CVEs are recognized as active security stewardship and permit **`BORROW`** when active CVEs on current release equal 0. Unpatched CVEs on the current release trigger safe version pinning or **`MIGRATE`**.
Popular, foundational libraries (like `axios`, `express`, `lodash`, `requests`, `urllib3`) have been maintained for 10+ years. Over a decade, security researchers discover historical CVEs, which maintainers **promptly patch in subsequent releases**.
- The presence of **historical patched CVEs** is a sign of **active security stewardship**, NOT a reason to abandon a library!
- Only **active, unpatched CVEs on the current latest release** represent real security risk.

### **Proposed Refinement:**
- **Version Scoping**: In `deps_dev.py` and `verdict.py`, explicitly separate `active_cves_on_current_version` from `historical_patched_cves`.
- **Verdict Rule Adjustment**:
  1. If `active_cves_on_current_version == 0` (even if historical total $> 0$), permit **`BORROW`** and include an audit note: *`"0 active CVEs on latest v1.7.9 (14 historical CVEs fully patched)"`*.
  2. Only trigger **`MIGRATE`** if `active_cves_on_current_version > 0` (an unpatched vulnerability remains open on the current release).

---

## 7. 📌 Safe Version Pinning Strategy (0 Extra Queries In-Memory Implementation) [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> - **In-Memory Safe Version Evaluation**: Added `query_package_version_history` and `find_safe_pinned_version` in [`deps_dev.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/queries/deps_dev.py). Evaluates release history against `affected_version_ranges` with 0 extra BigQuery byte overhead.
> - **SemVer Major Branch Constraint**: Restricts version recommendations strictly to the same Major version branch (e.g. `2.x.x`) to guarantee zero breaking API changes.
> - **12-Month Recency Horizon**: Filters out release versions published > 365 days ago.
> - **Verdict & UI Integration**: Updated Verdict Agent ([`verdict.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/agents/verdict.py)) and UI Hero Card ([`VerdictCard.tsx`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/frontend/src/components/verdict/VerdictCard.tsx)) to display **`BORROW`** with a blue **`"Recommended Version Pin: vX.Y.Z"`** banner when a safe version exists, or fall back to **`MIGRATE`** if no clean version exists in the 12-month horizon.
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

## 8. 🤖 Eliminate Hardcoded AI Interceptors & Replace Static Lists with Dynamic LLM Classification (Done ✅)

### **Problem Statement:**
1. **Active AI Interceptor in `verdict.py` (Line 235)**:
   ```python
   if not api_key or pkg_lower in deprecated_map or pkg_lower in micro_utils:
       return _rule_based_verdict_fallback()
   ```
   Whenever one of the 27 hardcoded packages is evaluated, it **bypasses Gemini completely**, returning static pre-baked strings and skipping real architectural reasoning.
2. **Active AI Interceptor in `diagnosis.py` (Line 118)**:
   ```python
   if not api_key or is_readme_deprecated or pkg_lower in known_deprecated:
       return _rule_based_fallback()
   ```
   Similarly intercepts the Diagnosis Agent for 14 hardcoded package names and blind README substring matches.
3. **Naive Substring Keyword Matching in `verdict.py` (Line 136)**:
   ```python
   if any(w in user_requirement.lower() for w in ["clamp", "repeat", "null or undefined", "uppercase", "left pad", "is number", "slugify", "flatten", "escape string"]):
       return VerdictResponse(decision="BUILD", ...)
   ```
   Forces a `BUILD` verdict based on a single word match in the prompt (e.g. *"pipe clamp monitoring dashboard"*), completely blind to actual task complexity.
4. **Blind README Substring Trigger in `github_issues.py` (Lines 148–152)**:
   Checks if words like `"deprecated"`, `"renamed to"`, or `"unmaintained"` appear anywhere in the first 2500 characters of the README. If a healthy package states *"We removed a deprecated v1 function"*, it mistakenly marks the entire package as abandoned.
5. **Arbitrary +40 Star-Inflation Hack in `forecasting.py` (Lines 103–106)**:
   ```python
   if total_all_events >= 200 or total_stars >= 50:
       health_score = round(min(100.0, max(75.0, raw_health_score + 40.0)), 2)
   ```
6. **Lack of Domain Relevance / Purpose Alignment Guard in Package Mode**:
   Currently, in Package Mode, the Verdict Agent only checks whether `user_requirement` can be built in $< 25$ LOC vs $> 25$ LOC. It does **not** evaluate whether the package belongs to the domain of the requirement! For example, when evaluating `manim` with `caching needed`, because Manim is healthy and caching is non-trivial, it outputs `BORROW`, ignoring that importing a 500MB video animation engine for general caching is absurd overkill.

### **Proposed Enhancement:**
- **Remove all pre-call interceptors**: Ensure Gemini is called on 100% of requests; fallback logic should only execute inside `except Exception:` error handlers.
- **Dynamic Contextual Evaluation**: Pass the README snippet and repository context directly to Gemini so it dynamically classifies deprecation, micro-utilities (< 25 LOC), and bedrock stability across any ecosystem without hardcoded dictionaries.
- **System Instruction Separation (`system_instruction`)**: Move system persona and behavioral directives out of the raw user prompt string and pass them into `types.GenerateContentConfig(system_instruction=...)` across all agents (`verdict.py`, `diagnosis.py`, `builder.py`, `candidate_finder.py`) per Google GenAI SDK standards.
- **Structured Delimiters (XML Tags)**: Wrap prompt sections in clear XML-style delimiters (`<context>`, `<evidence>`, `<decision_rules>`) to prevent context confusion and protect against prompt injection from user inputs.
- **Domain Relevance & Anti-Overkill Rule (Package Mode)**: Instruct Gemini to verify purpose alignment. If the target package's primary purpose has zero relation to the requirement (e.g. video rendering library for web caching), forbid `BORROW`, flag the domain mismatch, and recommend standard library alternatives (`@functools.lru_cache`) or purpose-built packages (`cachetools`).
- **Objective Mathematical Velocity**: Remove artificial +40 star-inflation; let the time-series model reflect true momentum and let Gemini determine bedrock status.

---

## 9. 📊 BigQuery SQL Query Optimization Strategy (Derived via `/bigquery-sql` Skill Audit) [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> Applied `/bigquery-sql` optimization techniques across [`queries/gh_archive.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/queries/gh_archive.py) and [`queries/deps_dev.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/queries/deps_dev.py). Pruned unnecessary columns, leveraged clustering index keys on `repo_name`, and eliminated the 7.8 GB multi-iteration `CREATE MODEL` scan cost by passing the in-memory 104 historical weeks directly as an inline parameter array into `CREATE OR REPLACE MODEL ... FROM UNNEST(@history)` (0 bytes billed for model fitting!).

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

## 11. 🚀 Eliminate Ghost Scores & Task Scale Guard When `github_url == null` / Candidates Unverified

### **Problem Statement:**
1. **The Ghost 75 Score**:
   Currently, when `github_url == null` (or package resolution fails), lines 147–153 of `evaluate.py` inject a fake fallback:
   ```python
   forecast_results = {
       "health_score": 75.0,
       "projected_total_events_90d": 120,
       "maintenance_verdict_signal": "HEALTHY_ACTIVE"
   }
   ```
   This deceives the **Diagnosis Agent** and **Verdict Agent** into hallucinating that non-existent or unverified packages (e.g. `github.com/patrickmn/go-cache` when aborted) are *"mature, stable packages with a 75 health score"*, issuing false `BORROW` verdicts!
2. **Unverified Candidate Fallback Trap (Task Mode)**:
   In `evaluate.py` line 356, when **ALL 3** suggested candidates fail verification, the code falls back to `primary_cand = candidate_list[0]` and tags it as *"Selected for Deep Analysis"*, evaluating an unverified package.

### **Proposed Architectural Flow:**
1. **Eliminate Ghost 75 Score**:
   When `github_url == null`, set `health_score = 0.0` (or `None`), `projected_events = 0`, and `maintenance_verdict_signal = "UNAVAILABLE"`. Do not feed fake telemetry to Gemini.
2. **Task Scale Guard When Candidates are Unverified**:
   If `len(verified_candidates) == 0`:
   - Do **NOT** run deep analysis on candidate #1.
   - Show all 3 cards with the red **`Unverified in registry`** tag.
   - **Distinguish Task Scale**:
     - **Micro-Tasks (< 25 LOC, e.g. "is even", "pad string")**: Issue **`BUILD`** and generate the clean in-house code replacement.
     - **Large / Complex Tasks (e.g. "distributed consensus cluster", "speech recognition transformer")**: Do **NOT** blindly issue `BUILD`! A developer cannot build a speech recognition model or distributed cluster in 20 lines. Instead, output an honest **`UNVERIFIED_CANDIDATES`** notice:  
       *`"Could not verify candidate packages in the {system} registry for this requirement. Because this task requires significant architectural complexity, building a custom implementation from scratch is non-trivial. Please verify registry connection or evaluate by exact package name."`*

---

## 12. 🧰 Antigravity Automated Audit Toolkit Integration [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> Integrated and executed 8 specialized Antigravity skills during implementation: `/bigquery-sql` (cost & scan tuning), `/ml-best-practices` (104-week ARIMA confidence bounds), `/accidental-data-loss-prevention` (safe dataset and table modifications), `/building-data-apps` (data architecture), `/managing-python-dependencies` (isolated venv command executions), `/discovering-gcp-data-assets` (dataset inspection), `/enforcing-resource-attribution` (project budgeting), and `/gcloud-auth-verification` (ADC and service credentials).

### **Available Specialized Audit Workflows:**
1. **`/ml-best-practices` (Machine Learning & Forecasting Audit)**:
   - Audits statistical forecasting engine ([`forecasting.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/services/forecasting.py)), OLS trend slope calculations, 90-day confidence bounds, and ARIMA model accuracy metrics.
2. **`/building-data-apps` (Full-Stack Data App Architecture)**:
   - Audits end-to-end data pipeline flow from BigQuery datasets $\rightarrow$ FastAPI backend $\rightarrow$ React Vite UI.
3. **`/managing-python-dependencies` (Python Dependency Health)**:
   - Scans backend Python requirements ([`requirements.txt`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/requirements.txt)) and virtual environment isolation.
4. **`/gcloud-auth-verification` (GCP Auth & BigQuery Quotas)**:
   - Verifies Application Default Credentials (ADC), BigQuery authentication, project scoping, and query byte limits ([`bigquery.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/core/bigquery.py)).
5. **`/discovering-gcp-data-assets` (GCP Data Asset Inspection)**:
   - Inspects schema definitions, table partitions, and cost bounds for `deps_dev_v1` and `githubarchive.month.*`.
6. **`/chrome-devtools` & `/a11y-debugging` (Accessibility & Browser Performance Audit)**:
   - Performs automated Chrome DevTools browser testing on [http://localhost:3000](http://localhost:3000) for ARIA compliance, keyboard focus traps, and rendering latency.

---

## 13. 🔑 GitHub REST API Authentication Header (`GITHUB_TOKEN`) [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> Declared `GITHUB_TOKEN: Optional[str] = None` in [`config.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/core/config.py#L56) and configured [`github_issues.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/services/github_issues.py#L55-L57) to attach `Authorization: Bearer <token>` to both Search and REST API calls. If `GITHUB_TOKEN` is present in `.env`, the rate limit jumps to 5,000 requests/hour; if absent, it safely falls back to unauthenticated public access.

### **Problem Statement:**
Currently, REST calls to the GitHub API (`api.github.com/repos/...` and `api.github.com/repos/.../issues`) in [`github_issues.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/services/github_issues.py) are sent unauthenticated.

### **Rate Limit Risk:**
- GitHub enforces a strict **60 requests/hour per IP address** rate limit for unauthenticated REST API calls.
- In production or multi-user testing environments, running 15-20 searches quickly exhausts the 60-request quota, resulting in `HTTP 403 Rate Limit Exceeded` errors.

### **Proposed Enhancement:**
- Add an optional `GITHUB_TOKEN: Optional[str] = None` setting in [`config.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/core/config.py).
- In [`github_issues.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/services/github_issues.py), attach `headers={"Authorization": f"token {settings.GITHUB_TOKEN}"}` if configured.
- Attaching a GitHub Personal Access Token raises the API rate limit from **60 requests/hour to 5,000 requests/hour**!

---

## 14. 🎯 Automated Candidate Verification Filter (`verified_exists == True`) in Candidate Finder [DONE ✅]

> [!NOTE]
> **Implementation Summary (Completed):**
> Implemented in [`backend/app/api/endpoints/evaluate.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/api/endpoints/evaluate.py#L349-L358). In Task Mode, after screening the 3 suggested candidate packages with `deps.dev`, the funnel filters `[cand for cand, screen in zip(candidate_list, screenings) if screen.verified_exists]`. Only packages verified to exist in the registry are chosen as the primary candidate for deep evaluation.

### **Problem Statement:**
In Task Requirement Mode, the Candidate Finder LLM occasionally suggests candidate package names that do not exist on the target ecosystem registry (PyPI/NPM), returning `verified_exists: false` (e.g. `add2ints`, `mathutils-plus`, `simple-adder`).

### **Proposed Enhancement:**
- **Existence Filter**: In [`candidate_finder.py`](file:///c:/Users/tvars/OneDrive/Desktop/my_project/buildOrBorrow/backend/app/agents/candidate_finder.py), filter the screened candidate list to ensure `verified_exists == True` before selecting a primary package for deep pipeline evaluation.
- **Micro-Task Fallback**: If 0 candidates have `verified_exists == True`, automatically trigger the **Native Micro-Task Fast-Path** (Item 10) to issue **`BUILD`** without running deep pipeline evaluations on fake package names.

---

## 15. 🏆 OpenSSF, ecosyste.ms & CHAOSS Validation Benchmark Integration

### **Value Proposition Differentiation:**
While raw data platforms like **Google deps.dev**, **OpenSSF Scorecards** (`api.securityscorecards.dev`), **ecosyste.ms**, and **CHAOSS Metrics** output passive metrics (e.g. `4.2/10`), **BuildOrBorrow** acts as the actionable **AI Decision & Code Generation Engine** that transforms raw data into `BORROW`, `MIGRATE`, or `BUILD` verdicts and generates custom zero-dependency code snippets on the spot.

### **4 External Datasets & APIs for Validation (`backend/scripts/benchmark_validation.py`):**
1. **Google `deps.dev` BigQuery Dataset**: (Currently used in BuildOrBorrow) Package resolution, OSV vulnerabilities, and dependency counts across PyPI, NPM, Cargo, Go, and Maven.
2. **OpenSSF Scorecard REST API & BigQuery Dataset** (`api.securityscorecards.dev` / `openssf:scorecardcron.scorecard-v2`): Extracts official ground-truth maintainer & security scores (0-10) for 1M+ GitHub repositories across ALL languages.
3. **`ecosyste.ms` API**: Cross-ecosystem dependency graph metadata across 15+ package registries.
4. **Linux Foundation CHAOSS Metrics**: 80+ standardized open-source sustainability & health metrics.

---

## 🔮 Post-MVP Enhancements

### 16. 🐣 "INCUBATING_NEW" Guard for Brand New Packages (< 6 Weeks Old)
- **Problem**: When a package was published only 1 to 3 weeks ago, running BigQuery ML ARIMA on 2 or 3 data points produces volatile, statistically unreliable trend slopes.
- **Proposed Enhancement**: If a package has $< 6$ historical weeks of data in the warehouse, bypass ARIMA model fitting, tag the package status as **`INCUBATING_NEW`**, and warn the developer: *"Package was published recently (< 6 weeks old). Long-term maintenance trajectory cannot be determined yet; evaluate early-stage adoption risks."*

### 17. 🐙 Monorepo Parent Repository Context Notice
- **Problem**: Packages like `@babel/parser` or `google-cloud-storage` link to large parent monorepos (`babel/babel` and `google-cloud-python`).
- **Proposed Enhancement**: When a package maps to a known multi-package monorepo, display an informative context chip: *"Repository Telemetry reflects parent monorepo: babel/babel"* so developers understand that commit velocity represents the collective project suite.
