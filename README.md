# BuildOrBorrow: Project Details & Specification
---

## 1. Final Project Idea

Developers often evaluate software dependencies using current snapshots such as GitHub stars, latest commit date, open issues, and current vulnerabilities. **BuildOrBorrow** instead examines how a dependency has behaved over the previous 18–24 months, forecasts its activity approximately 90 days into the future, interprets the resulting trajectory, and recommends whether the developer should continue using the dependency, migrate to an alternative, or build a small replacement.

> **Core Idea:** Observe the dependency's trajectory, forecast its near-term health, diagnose what the trend means, and convert that evidence into an actionable developer decision.

---

## 2. What Makes the Project Distinct

The project should not be positioned as simply predicting whether a GitHub repository will be abandoned. That research problem already has prior work. The stronger contribution is to investigate whether longitudinal dependency-health forecasting can be converted into an actionable developer decision: **BORROW**, **MIGRATE**, or **BUILD**.

```
Current dependency information
              +
18–24 month repository behavior
              +
    90-day activity forecast
              +
  Security / dependency burden
              +
Context about the functionality being used
              +
    LLM-based interpretation
              ↓
  Actionable recommendation
```

---

## 3. Complete System Flow

```
                      USER
                       │
                       ▼
         Package name OR task description
                       │
                       ▼
              Input classification
                       ├── Package input ────────────────────────┐
                       └── Task input                            │
                           │                                     │
                           ▼                                     │
                    Gemini identifies                            │
                  exactly 3 candidates                           │
                           │                                     │
         ┌─────────────────┼─────────────────┐                   │
         ▼                 ▼                 ▼                   │
    Candidate A       Candidate B       Candidate C              │
         └─────────────────┬─────────────────┘                   │
                           ▼                                     │
               REUSABLE PACKAGE PIPELINE <───────────────────────┘
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
      Package           Security         Historical
    Resolution           /Bloat           Activity
         └─────────────────┼─────────────────┘
                           ▼
                      Forecasting
                      ARIMA_PLUS
                           ▼
                    diagnosis_agent
                           ▼
                     verdict_agent
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
      BORROW            MIGRATE            BUILD
         │                 │                 │
         │        Analyze alternative        │
         │           builder_agent <─────────┘
         └─────────────────┬─────────────────┘
                           ▼
                        React UI
```

---

## 4. Step 0: User Input

The frontend should use a single-screen, single-submit flow. The user enters either an exact package name or a task description. A toggle distinguishes the two modes. An optional feature field records what specific functionality the developer actually uses.

```text
What are you looking for?
[ feedparser ]

■ Exact package name
■ A task I need to solve

What specific feature do you use?
[ Parse RSS feeds and extract title/link ]

[ Analyze ]
```

---

## 5. Two Input Paths

- **Exact package:** Resolve the package and run it through the pipeline.
- **Task description:** Gemini returns exactly three candidates, conceptually standard, lightweight, and modern. All three are then passed to the same reusable analysis pipeline in parallel.

```python
analyze_packages([package1, package2, package3])
```

The same reusable function is used for:
- Single-package analysis
- Task-based comparison
- Alternative validation after **MIGRATE**

---

## 6. Stage 1: Resolve Package

**Data Source:** `deps.dev` BigQuery. Resolve package name, ecosystem, project, repository, GitHub URL, and license. This stage is deterministic and uses no AI.

```
Packages ──> Deps.dev ──> Project ──> GitHub repository ──> License
```

**Edge Cases:** Package not found, renamed/transferred repositories, deleted or archived repositories, and monorepos where repository-level activity may not represent package-level health.

---

## 7. Stage 2: Security and Dependency Burden

Use `deps.dev` to retrieve known direct and transitive vulnerabilities, license information, and dependency burden. The first version can use total transitive dependency count as the simple burden metric. Dependency graph depth can be added later if useful.

```text
Security & Dependency Check
  Direct vulnerabilities:    0
  Transitive vulnerabilities: 1

  Direct dependencies:       5
  Transitive dependencies:   27

  License: MIT
```

---

## 8. Stage 3: Historical Trend

**Data Source:** GH Archive through BigQuery. Use approximately 18–24 months of GitHub activity and aggregate it weekly. At minimum, collect push activity, issues, pull requests, forks, and watches. For technical accuracy, call `PushEvent` counts 'push activity' rather than automatically calling them commits unless commits are explicitly counted from the event payload.

| Week | Pushes | Issues | PRs | Forks | Watches |
|:---:|:---:|:---:|:---:|:---:|:---:|
| W1 | 42 | 8 | 5 | 2 | 13 |
| W2 | 39 | 7 | 6 | 1 | 11 |
| W3 | 45 | 9 | 4 | 3 | 14 |
| ... | ... | ... | ... | ... | ... |
| W80 | 9 | 2 | 1 | 0 | 2 |

---

## 9. Stage 3B: Forecasting

Use BigQuery ML `ARIMA_PLUS` to forecast approximately 90 days ahead. The 18–24 month history provides context, while the forecast supplies the short-term trajectory. The system must not claim to predict the package's entire future or guarantee abandonment.

```
18–24 months historical activity
               │
               ▼
           ARIMA_PLUS
               │
               ▼
     approximately 90 days
               │
               ▼
 Forecast + prediction interval
```

**Confidence:** The UI may label forecast confidence using prediction-interval width, but this should be described as *forecast certainty*, not the probability that the package will be abandoned.

---

## 10. Stage 4: `diagnosis_agent`

This is the first stage where Generative AI is genuinely useful. Gemini receives structured quantitative evidence, the forecast, security/dependency context, **and the titles of the 10–20 most recent issues, fetched via the GitHub REST API.** Its job is to interpret what the trend means rather than invent the underlying numbers.

> **Critical Distinction:** Differentiating between **declining but stable** and **declining and struggling**. A mature project with falling activity and almost no unresolved issues may be functionally complete. A project with falling activity plus increasing unresolved issues may be genuinely struggling.

> **Why this matters:** Without real issue/PR text, this agent would be reasoning purely over numbers a rule-based threshold could mostly replicate. Reading actual issue content — not just counting how many are open — is what makes this step genuinely require AI rather than dressed-up arithmetic.

---

## 11. Stage 5: `verdict_agent`

The verdict agent combines the deterministic evidence, forecast, diagnosis, and the user's stated feature requirement. It returns one of three actions:

| Verdict | Meaning |
|:---|:---|
| **BORROW** | Continue using the dependency because the project is sufficiently stable or mature for the required use. |
| **MIGRATE** | Move to an alternative because the dependency's trajectory, issues, security, or other evidence creates meaningful risk. |
| **BUILD** | Implement the required functionality directly when the feature is small enough and taking another dependency is not justified. |

---

## 12. Alternative Validation Loop

If the verdict is **MIGRATE**, do not simply name an alternative. Run the suggested alternative through the same reusable package pipeline. The UI should explain concretely why the alternative is better using real numbers.

```
Current package ──> MIGRATE ──> Gemini suggests alternative ──> Alternative package
                                                                       │
                                                                       ▼
                                                                 Same pipeline
                                                                       │
                                                                       ▼
                                                       Forecast + Security + Dependencies + Diagnosis
                                                                       │
                                                                       ▼
                                                             Side-by-side comparison
                                                                       │
                                                                       ▼
                                                         "Alternative is better because..."
```

---

## 13. Stage 6: `builder_agent`

The builder agent runs only for **BUILD**. It receives the task and the specific feature required and generates a small, preferably zero-dependency replacement. The result should be presented as a suggested implementation, not as guaranteed production-ready code.

---

## 14. Final UI

The frontend should contain an expandable pipeline and a separate verdict card. Multiple pipeline rows can be open simultaneously. Each stage should show a one-line summary, detailed evidence when expanded, and a *Show Raw Data* control.

```text
✓ 1. Resolve package
  Found PyPI package ──> GitHub repository
  MIT license

✓ 2. Security & dependency check
  0 direct vulnerabilities
  1 transitive vulnerability
  27 transitive dependencies

✓ 3. Trend forecast
  Activity declining
  90-day forecast continues downward

■ 4. Diagnosis
  Declining but stable

✓ 5. Verdict
  BORROW

■ 6. Builder
  Not required
```

The verdict card should contain the recommendation, reasoning, license flag, forecast-confidence label, and *Copy as Markdown*. Task mode should show 2–3 candidate comparison cards, while a **MIGRATE** result should show the alternative side by side after it has been independently analyzed.

---

## 15. Architecture

```text
backend/
├── main.py
├── models/
│   ├── request_models.py
│   └── response_models.py
├── queries/
│   ├── deps_dev.py
│   ├── github_trend.py
│   └── forecasting.py
├── services/
│   ├── package_resolver.py
│   ├── security_service.py
│   ├── trend_service.py
│   ├── issue_context_service.py
│   └── package_pipeline.py
├── agents/
│   ├── diagnosis_agent.py
│   ├── verdict_agent.py
│   └── builder_agent.py
├── pipeline/
│   ├── sequential_pipeline.py
│   └── parallel_pipeline.py
└── Dockerfile

frontend/
├── src/
│   ├── components/
│   │   ├── SearchForm.jsx
│   │   ├── Pipeline.jsx
│   │   ├── PipelineStep.jsx
│   │   ├── VerdictCard.jsx
│   │   ├── ComparisonCard.jsx
│   │   └── RawData.jsx
│   ├── services/
│   │   └── api.js
│   ├── App.jsx
│   └── main.jsx
└── ...
```

---

## 16. API Design

**Main Endpoint:** `POST /analyze`

### Request Examples

**Package Mode:**
```json
{
  "input": "feedparser",
  "mode": "package",
  "feature": "Parse RSS feeds"
}
```

**Task Mode:**
```json
{
  "input": "I need to parse RSS feeds in Python",
  "mode": "task",
  "feature": "Extract title and link"
}
```

### Response Format

The response should be structured JSON containing package resolution, security, trend, diagnosis, and verdict objects so the React frontend can render the result predictably:

```json
{
  "packages": [
    {
      "package": {},
      "security": {},
      "trend": {},
      "diagnosis": {},
      "verdict": {}
    }
  ]
}
```

---

## 17. Where AI Is and Is Not Used

| Stage | Technology | AI? |
|:---|:---|:---|
| Package resolution | BigQuery / `deps.dev` | No |
| Security and dependency count | BigQuery / `deps.dev` | No |
| Historical aggregation | BigQuery / GH Archive | No |
| Forecasting | BigQuery ML `ARIMA_PLUS` | ML, not GenAI |
| Diagnosis (incl. issue/PR text reasoning) | Gemini + ADK | Yes |
| Verdict | Gemini + ADK | Yes |
| Alternative reasoning | Gemini | Yes |
| Replacement generation | Gemini + ADK | Yes |

---

## 18. Agent Architecture

### Single Package Analysis (`SequentialAgent`)
```
Root Agent
    │
    ▼
SequentialAgent
    │
    ├───────────────────────┬───────────────────────┐
    ▼                       ▼                       ▼
DiagnosisAgent         VerdictAgent            BuilderAgent
                                                    │
                                              (only if BUILD)
```

### Multi-Candidate Analysis (`ParallelAgent`)
```
ParallelAgent
   ├── Package A ──┐
   ├── Package B ──┼──> Comparison
   └── Package C ──┘
```

> Using both `SequentialAgent` and `ParallelAgent` provides sequential reasoning for a single package and concurrent analysis for multiple candidates.

---

## 19. Data Sources

| Requirement | Source | Assessment |
|:---|:---|:---|
| Package resolution | `deps.dev` BigQuery | Excellent |
| GitHub repository | `deps.dev` BigQuery | Good |
| License | `deps.dev` BigQuery | Good |
| Security advisories | `deps.dev` BigQuery | Excellent |
| Dependency counts | `deps.dev` BigQuery | Excellent |
| Dependency graph | `deps.dev` BigQuery | Available |
| Historical GitHub activity | GH Archive | Excellent |
| Weekly trend features | GH Archive + BigQuery | Excellent |
| 90-day forecast | BigQuery ML | Excellent |
| Recent issue/PR text | GitHub REST API | **Required — MVP** |

*Note: `deps.dev`, GH Archive, and the GitHub REST API (for issue titles) are sufficient to start the project. External sources like Reddit are unnecessary for the planned version.*

---

## 20. Scope and Limitations

- Forecast horizon is approximately 90 days; this is an early-warning signal, not a long-range prophecy.
- The system evaluates project-level health, not individual contributors.
- License analysis only flags potential concerns; it does not provide legal advice.
- Repository activity is an imperfect proxy for package-level health, especially for monorepos.
- LLM diagnosis is reasoning over evidence, not ground truth.
- Issue/PR context is limited to the 10–20 most recent issue titles (not full thread bodies), to control cost and context size.
- The project does not include full technology-stack analysis.
- Bundle-size analysis is out of scope.
- Typosquatting and supply-chain name-similarity detection are future work.
- Multi-turn conversational follow-up is intentionally out of scope.
- Contributor recommendation matching is a possible Phase 2 idea.

---

## 21. Recommended Learning Areas

**Must Know:** Python, SQL, BigQuery, time-series basics, FastAPI, React, LLM concepts, and Google ADK.

*You do not need to master advanced deep learning, train your own LLM, Kubernetes, advanced frontend animation, graph neural networks, or complicated distributed systems.*

---

## 22. First Implementation Milestone

> **Rule:** Do not start with the React UI or the agents. First prove the data and forecasting foundation.

```
One known healthy package
           +
One known declining/abandoned package
           │
           ▼
Retrieve 18–24 months from GH Archive
           │
           ▼
    Aggregate weekly
           │
           ▼
    Run ARIMA_PLUS
           │
           ▼
Inspect forecast and prediction interval
           │
           ▼
Confirm that the pipeline produces sensible results
```

**Only after this foundation works:**
1. Build the `diagnosis_agent` (including the issue-title fetch)
2. Build the `verdict_agent`
3. Build the React UI
