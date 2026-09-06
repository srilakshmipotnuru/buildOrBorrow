# BuildOrBorrow: AI-Powered Dependency Health Evaluator & Decision Engine

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React Version](https://img.shields.io/badge/react-19.2%2B-61dafb.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/vite-8.2%2B-646cff.svg)](https://vitejs.dev/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-3.5%20%2F%203.6-8E75B2.svg)](https://deepmind.google/technologies/gemini/)
[![Google Cloud BigQuery](https://img.shields.io/badge/BigQuery-ML%20ARIMA__PLUS-4285F4.svg)](https://cloud.google.com/bigquery)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**BuildOrBorrow** is an intelligent software dependency health evaluator and decision engine. Instead of evaluating third-party dependencies using static point-in-time snapshots (such as current GitHub stars, latest commit date, or current issue counts), **BuildOrBorrow** analyzes **104 weeks (~2 years)** of historical activity, generates a **90-day time-series forecast via BigQuery ML `ARIMA_PLUS`**, inspects security vulnerabilities and dependency burden using Google `deps.dev`, evaluates open GitHub issue severity via the GitHub REST API, and uses multi-agent Generative AI (powered by Google Gemini) to diagnose maintenance trends and deliver actionable developer decisions: **BORROW**, **MIGRATE**, or **BUILD**.

---

## Table of Contents

- [Key Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture & Pipeline Flow](#architecture--how-it-works)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Environment Variables](#environment-variables)
- [Running the Project](#running-the-project)
- [Usage Examples](#usage)
- [API Documentation](#api-documentation)
- [Data Warehouse & BigQuery ML](#database)
- [Testing & Benchmarking](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Dual Evaluation Modes**:
  - **Single Package Mode**: Deeply evaluates an exact package name across ecosystems (**PyPI**, **npm**, **Cargo**, **Go**, **Maven**).
  - **Task Mode**: Accepts a plain-English task requirement (e.g., *"Parse RSS feeds in Python"*), uses the `Candidate Finder Agent` to surface 3 popular packages, screens them via `deps.dev`, and performs deep primary evaluation.
- **Micro-Utility Fast-Path Bypass**: Automatically detects single-function micro-task requirements (< 25 LOC such as math clamping, string repeating, or null checking) and immediately issues a zero-dependency **BUILD** verdict, bypassing heavy BigQuery data scans.
- **Longitudinal Telemetry & ML Time-Series Forecasting**: Aggregates 104 weeks of historical GitHub activity (pushes, pull requests, open issues, star velocity, active contributors) and projects developer activity 90 days into the future using BigQuery ML `ARIMA_PLUS`.
- **Security & Dependency Burden Scanning**: Leverages Google `deps.dev` BigQuery datasets to evaluate direct/transitive vulnerability severity counts (**CRITICAL**, **HIGH**, **MEDIUM**, **LOW**), license compatibility, and transitive dependency depth.
- **GitHub Issue Severity Analysis**: Scans recent open issue titles via the GitHub REST API to distinguish mature, feature-complete *"finished software"* from struggling projects burdened by unaddressed bug debt.
- **Multi-Agent GenAI Decision Engine (Google Gemini)**:
  - `Candidate Finder Agent`: Identifies 3 modern, well-maintained candidate packages for task requests.
  - `Diagnosis Agent`: Distinguishes feature-complete mature projects (`MATURE_STABLE`) from struggling or abandoned projects (`ABANDONED_STRUGGLING`).
  - `Verdict Agent`: Integrates a Calculative Confidence Engine (Formulaic Base + LLM Delta + Hard Caps) to issue the final decision (**BORROW**, **MIGRATE**, **BUILD**, or **UNVERIFIED_CANDIDATES**).
  - `Builder Agent`: Generates clean, production-ready, zero-dependency code replacements when the verdict is **BUILD**.
- **Alternative Verification Loop**: Automatically suggests, screens, and verifies healthier alternative packages when a package receives a **MIGRATE** decision.
- **Interactive Modern UI**: Built with React 19, TypeScript, Vite, Recharts, and Lucide React icons, featuring expandable 6-step pipeline accordions, interactive forecast charts, candidate comparison grids, and a raw JSON inspector.
- **Empirical Benchmark Suite**: Automated Python test runner (`run_tests.py`) evaluating 25 benchmark scenarios against expected decisions in `test_dataset.csv`.

---

## Tech Stack

### Backend
- **Language**: Python 3.10+
- **Framework**: FastAPI (>= 0.100.0), Uvicorn (>= 0.22.0)
- **Data Validation & Settings**: Pydantic v2, `pydantic-settings`, `python-dotenv`
- **AI / GenAI SDK**: `google-genai` (>= 0.1.0) featuring `gemini-3.5-flash-lite`, `gemini-3.6-flash`, and `gemini-3.1-flash-lite`
- **Cloud & Data Warehouse**: `google-cloud-bigquery` (>= 3.10.0), GH Archive, Open Source `deps.dev` BigQuery datasets, BigQuery ML (`ARIMA_PLUS`)
- **HTTP Client**: `requests` (>= 2.31.0)

### Frontend
- **Framework**: React 19.2+, Vite 8.2+
- **Language**: TypeScript 6.0+
- **Data Visualization**: Recharts (>= 2.15.1)
- **Icons & Styling**: Lucide React (>= 0.475.0), Vanilla CSS (Custom dark-mode glassmorphism theme)
- **Code Highlighting**: `react-syntax-highlighter` (>= 15.6.1)
- **HTTP & Utilities**: Axios (>= 1.7.9)

---

## Architecture / How It Works

BuildOrBorrow operates as a 6-stage evaluation pipeline. Below is the system flow for both Single Package Mode and Task Mode:

```
                                     USER INPUT
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   ▼                                           ▼
          [ Package Mode ]                              [ Task Mode ]
       (e.g., "feedparser")                   (e.g., "Parse RSS feeds in Python")
                   │                                           │
                   │                             Is Micro-Utility (< 25 LOC)?
                   │                                   ├── YES ──► Fast-Path BUILD
                   │                                   └── NO  ──► Candidate Finder Agent
                   │                                                   (Suggests 3 packages)
                   │                                                           │
                   └─────────────────────┬─────────────────────────────────────┘
                                         ▼
                             Stage 1: Package Resolution
                              (deps.dev BigQuery Dataset)
                                         │
                                         ▼
                         Stage 2: Security & Dependency Scan
                              (deps.dev BigQuery Dataset)
                                         │
                                         ▼
                     Stage 3: 104-Week Activity & 90-Day Forecast
                          (GH Archive + BigQuery ML ARIMA_PLUS)
                                         │
                                         ▼
                          Stage 4: GitHub Issue Severity
                               (GitHub REST API v3)
                                         │
                                         ▼
                             Stage 5: Diagnosis Agent
                              (Google Gemini GenAI)
                                         │
                                         ▼
                              Stage 6: Verdict Agent
                              (Google Gemini GenAI)
                                         │
         ┌───────────────────────────────┼───────────────────────────────┐
         ▼                               ▼                               ▼
    [ BORROW ]                      [ MIGRATE ]                      [ BUILD ]
 Continue using                Alternative Verification            Builder Agent
  dependency                   Loop & Comparison View            Zero-Dep Code Snippet
```

### Actionable Decisions Summary

| Decision | Condition & Meaning |
| :--- | :--- |
| **BORROW** | The dependency is actively maintained or mature/stable, secure, and appropriate to adopt into your codebase. |
| **MIGRATE** | The dependency is abandoned, struggling, or vulnerable. The system automatically suggests and verifies a healthier alternative package. |
| **BUILD** | The requirement is a lightweight micro-utility (< 25 LOC) or the existing packages are bloated/risky. The system generates an in-house, zero-dependency implementation. |
| **UNVERIFIED_CANDIDATES** | Complex task requirements whose suggested packages could not be verified in the target ecosystem registry. |

---

## Project Structure

```
buildOrBorrow/
├── backend/                        # FastAPI Backend Application
│   ├── app/
│   │   ├── agents/                 # Google Gemini AI Multi-Agent Engine
│   │   │   ├── builder.py          # Zero-dependency code generation agent
│   │   │   ├── candidate_finder.py # Task-to-candidate package discovery agent
│   │   │   ├── diagnosis.py        # Health diagnosis & issue severity agent
│   │   │   └── verdict.py          # Final decision & calculative confidence engine
│   │   ├── api/
│   │   │   └── endpoints/          # REST API endpoints
│   │   │       ├── deps_dev.py     # deps.dev resolution & security endpoints
│   │   │       ├── evaluate.py     # Main full evaluation pipeline endpoint
│   │   │       ├── forecast.py     # BigQuery ML ARIMA_PLUS forecast endpoints
│   │   │       └── gh_archive.py   # Historical GitHub activity endpoints
│   │   ├── core/                   # Core application configuration & infrastructure
│   │   │   ├── bigquery.py         # Google BigQuery client initializer
│   │   │   ├── config.py           # 12-factor application settings & limits
│   │   │   └── utils.py            # Gemini retry handlers & helper utilities
│   │   ├── models/                 # Pydantic data schemas & response DTOs
│   │   ├── queries/                # BigQuery SQL queries (deps.dev & GH Archive)
│   │   ├── services/               # Internal services (forecasting, GitHub issues, verification)
│   │   └── main.py                 # FastAPI app entry point & CORS configuration
│   ├── logs/                       # Test suite run output logs
│   ├── requirements.txt            # Backend Python dependencies
│   ├── run_tests.py                # Automated benchmark execution script
│   └── test_dataset.csv            # 25 benchmark evaluation test cases
├── frontend/                       # React 19 + Vite Frontend Application
│   ├── src/
│   │   ├── components/             # Modular React UI components
│   │   │   ├── code/               # Zero-dependency code replacement viewer
│   │   │   ├── common/             # Search form & header controls
│   │   │   ├── inspector/          # Raw JSON data inspector
│   │   │   ├── Pipeline/           # 6-step accordion pipeline & Recharts graphs
│   │   │   └── verdict/            # Verdict hero card, candidate grid & migration views
│   │   ├── services/               # API client (Axios) & session storage cache
│   │   ├── types/                  # TypeScript interface definitions (api.ts)
│   │   ├── App.tsx                 # App layout & evaluation state coordinator
│   │   └── main.tsx                # React DOM render entry point
│   ├── package.json                # Frontend npm dependencies & scripts
│   └── vite.config.ts              # Vite bundle configuration
├── docs/                           # Technical documentation & architecture guides
│   └── bigquery_warehouse.md       # BigQuery Warehouse DDL, ML Model & IAM setup guide
├── dryrun/                         # CLI testing utilities
│   └── dry_run.py                  # CLI script for testing package resolution & issue fetching
├── .env.example                    # Global backend environment configuration template
└── README.md                       # Main project documentation
```

---

## Prerequisites

Before running BuildOrBorrow, ensure you have the following installed and configured:

1. **Python**: Version `3.10` or higher
2. **Node.js**: Version `18.0` or higher (with `npm`)
3. **Google Cloud Platform (GCP) Account**:
   - An active GCP Project ID with BigQuery API enabled.
   - Authentication configured via standard GCP credentials (`gcloud auth application-default login`) or service account JSON key.
4. **Google Gemini API Key**:
   - Obtain an API key from [Google AI Studio](https://aistudio.google.com/).
5. **GitHub Personal Access Token (Optional but Recommended)**:
   - A standard GitHub PAT increases GitHub REST API rate limits from 60 to 5,000 requests/hour.

---

## Installation & Setup

Follow these step-by-step instructions to set up BuildOrBorrow locally:

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/buildOrBorrow.git
cd buildOrBorrow
```

### 2. Configure Backend Environment

Copy the `.env.example` file to create your local `.env` file in the project root:

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:

```env
GCP_PROJECT=your-gcp-project-id
GEMINI_API_KEY=your-gemini-api-key
GITHUB_TOKEN=your-github-personal-access-token # Optional
ENABLE_BIGQUERY_BYTE_LIMITS=true
```

### 3. Set Up Backend Virtual Environment

```bash
cd backend
python -m venv .venv

# Activate on Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Activate on macOS/Linux:
source .venv/bin/activate

# Install required Python packages:
pip install -r requirements.txt
cd ..
```

### 4. Set Up Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Environment Variables

### Backend Configuration (`.env`)

| Variable | Description | Required | Default |
| :--- | :--- | :---: | :--- |
| `GCP_PROJECT` | Active Google Cloud Platform Project ID for BigQuery. | **Yes** | `None` |
| `GEMINI_API_KEY` | Google Gemini API Key for multi-agent GenAI features. | **Yes** | `None` |
| `GITHUB_TOKEN` | GitHub PAT to expand GitHub REST API rate limits (60 $\rightarrow$ 5000 req/hr). | No | `None` |
| `ENABLE_BIGQUERY_BYTE_LIMITS` | Set `true` for development byte caps, `false` for unrestricted production. | No | `true` |
| `BQ_GH_ARCHIVE_MAX_ALLOWED_MB` | Maximum MB billed cap for GH Archive historical scans. | No | `20000.0` (~20 GB) |
| `GEMINI_MODEL_NAME` | Primary high-throughput model for AI agents. | No | `gemini-3.5-flash-lite` |

### Frontend Configuration (`frontend/.env.example`)

| Variable | Description | Required | Default |
| :--- | :--- | :---: | :--- |
| `VITE_API_BASE_URL` | Base URL for FastAPI backend endpoints. | No | `http://localhost:8000/api` |

---

## Running the Project

To run BuildOrBorrow locally, start both the backend API server and frontend development server.

### 1. Start FastAPI Backend

```bash
cd backend
# Make sure virtual environment is activated
uvicorn app.main:app --reload --port 8000
```
- **Backend API**: `http://localhost:8000`
- **Interactive Swagger OpenAPI Docs**: `http://localhost:8000/docs`

### 2. Start Vite Frontend

In a separate terminal window:

```bash
cd frontend
npm run dev
```
- **Web Application UI**: `http://localhost:5173`

---

## Usage

### 1. Single Package Evaluation Mode
1. Open `http://localhost:5173`.
2. Select **Exact Package Name**.
3. Select Ecosystem (e.g., `pypi`, `npm`, `cargo`, `go`, `maven`).
4. Enter package name (e.g., `uvicorn`, `passlib`, or `clamp`).
5. Click **Evaluate Dependency**.

### 2. Task Requirement Mode
1. Select **A Task I Need to Solve**.
2. Enter your task description (e.g., *"Parse RSS feeds in Python"* or *"Restrict a numeric value between min and max boundary"*).
3. Click **Evaluate Dependency**.
4. View the suggested candidate packages grid, top candidate deep evaluation, decision banner, time-series forecast graph, or zero-dependency code replacement snippet.

### 3. Running Standalone CLI Dry Run
To verify BigQuery package resolution and GitHub issue fetching via CLI:

```bash
python dryrun/dry_run.py
```

---

## API Documentation

### Main Endpoint: `POST /api/evaluate`

Executes the full 6-stage evaluation pipeline.

#### Request Payload Examples

**Single Package Request:**
```json
{
  "package_name": "passlib",
  "system": "pypi",
  "user_requirement": "Password hashing with bcrypt"
}
```

**Task Requirement Request:**
```json
{
  "task_description": "Parse RSS feeds in Python",
  "system": "pypi"
}
```

#### Response Payload Structure

```json
{
  "mode": "package",
  "evaluation": {
    "package_name": "passlib",
    "system": "PYPI",
    "github_url": "https://github.com/pyca/passlib",
    "resolution": {
      "name": "passlib",
      "system": "PYPI",
      "version": "1.7.4",
      "licenses": ["BSD-3-Clause"]
    },
    "security": {
      "critical_vulnerabilities": 0,
      "total_vulnerabilities": 1,
      "transitive_dependencies": 4,
      "license": "BSD-3-Clause"
    },
    "forecast": {
      "trend_direction": "DECLINING",
      "health_score": 18.5,
      "maintenance_verdict_signal": "AT_RISK_STAGNANT"
    },
    "diagnosis": {
      "status": "ABANDONED_STRUGGLING",
      "is_abandoned": true,
      "explanation": "Package passlib has unmaintained repository telemetry and incompatibility with bcrypt 4.0+."
    },
    "verdict": {
      "decision": "MIGRATE",
      "confidence_score": 0.95,
      "confidence_level": "HIGH",
      "reasoning": [
        "Unmaintained since 2020 with unaddressed bug debt",
        "Migration recommended to bcrypt or argon2-cffi"
      ],
      "recommended_alternative": "argon2-cffi"
    }
  }
}
```

### Additional System Endpoints

- `GET /api/deps-dev/package-info?package_name=requests&system=pypi`: Queries `deps.dev` package metadata & vulnerabilities.
- `GET /api/gh-archive/activity?owner=psf&repo=requests&lookback_weeks=104`: Returns 104-week raw activity timeline from BigQuery.
- `GET /api/gh-archive/package-activity?package_name=fastapi&system=pypi`: Resolves package to repo and retrieves activity timeline.
- `GET /api/forecast/project?owner=psf&repo=requests`: Projects 90-day activity using BigQuery ML `ARIMA_PLUS`.

---

## Database

BuildOrBorrow utilizes Google BigQuery for longitudinal data storage and ML forecasting.

### 1. Data Sources
- `bigquery-public-data.deps_dev_v1`: Real-time dependency graphs, licenses, package versions, and OSV security advisories.
- `githubarchive.month.*`: Multi-terabyte GitHub public event stream.

### 2. Custom Data Warehouse Schema
- **Dataset**: `build_or_borrow_dw`
- **Table**: `github_weekly_activity`
- **Volume**: ~17.3 Million pre-aggregated weekly activity records across 104 weeks.
- **Optimization**: Partitioned by `week_start` (DATE) and clustered by `repo_name`. Bot accounts (`actor.login LIKE '%[bot]'`) are filtered out during aggregation.

### 3. BigQuery ML `ARIMA_PLUS` Forecasting
Time-series models project activity 13 weeks (~90 days) into the future. High-performance zero-scan inline parameter array passing (`UNNEST(@history)`) eliminates multi-gigabyte scans during model fitting.

For full DDL queries, SQL aggregation scripts, and collaborator IAM setup guides, see [`docs/bigquery_warehouse.md`](docs/bigquery_warehouse.md).

---

## Testing

BuildOrBorrow includes an empirical benchmark test suite that verifies system verdicts against 25 real-world scenarios in `test_dataset.csv`.

### Running Benchmark Test Suite

```bash
cd backend
python run_tests.py
```

The test runner will execute package-mode and task-mode evaluations, log individual test timings, compare actual decisions against expected benchmarks, and output a formatted report:

```
===================================================================================================
 🧪 BUILDORBORROW BENCHMARK TEST SUITE SUMMARY REPORT
===================================================================================================
📦 PART 1: PACKAGE MODE EVALUATIONS (14 Tests)
| Test ID | Package      | System | Expected         | Actual Verdict       | Result |
| PKG-001 | passlib      | pypi   | MIGRATE          | MIGRATE              | PASS   |
| PKG-005 | clamp        | npm    | BUILD            | BUILD                | PASS   |
| PKG-009 | cryptography | pypi   | BORROW           | BORROW               | PASS   |
...
===================================================================================================
```

Outputs are automatically saved to `backend/logs/test_run_latest.log`.

### Frontend Code Quality

```bash
cd frontend
# Run ESLint validation
npm run lint

# Run TypeScript build check
npm run build
```

---

## Deployment

### Backend Deployment (Docker / GCP Cloud Run)
1. Build container image:
   ```bash
   cd backend
   docker build -t buildorborrow-backend .
   ```
2. Set environment variables in Cloud Run: `GCP_PROJECT`, `GEMINI_API_KEY`, `ENABLE_BIGQUERY_BYTE_LIMITS=false`.
3. Deploy to Cloud Run or AWS App Runner listening on port `8000`.

### Frontend Deployment (Vercel / Netlify / Static Hosting)
1. Build production static bundle:
   ```bash
   cd frontend
   npm run build
   ```
2. Deploy the generated `dist/` directory to Vercel, Netlify, or Nginx.
3. Configure `VITE_API_BASE_URL` to point to your live backend endpoint.

---

## Troubleshooting

### 1. `403 Forbidden` / GitHub Rate Limit Exceeded
- **Cause**: GitHub REST API unauthenticated rate limit (60 requests/hr) reached.
- **Fix**: Add a valid `GITHUB_TOKEN` to your `.env` file.

### 2. BigQuery `Query exceeded limit for bytes billed`
- **Cause**: `ENABLE_BIGQUERY_BYTE_LIMITS=true` triggered byte cap safety rule.
- **Fix**: Increase `BQ_GH_ARCHIVE_MAX_ALLOWED_MB` in `app/core/config.py` or set `ENABLE_BIGQUERY_BYTE_LIMITS=false` in production.

### 3. Gemini API Quota / Network Error
- **Cause**: Invalid API key or temporary Google GenAI service throttling.
- **Fix**: Verify `GEMINI_API_KEY` in `.env`. The backend automatically triggers production-grade rule-based fallbacks if Gemini is unreachable.

### 4. CORS Errors in Frontend
- **Cause**: Frontend requests blocked by backend origin settings.
- **Fix**: Verify backend `main.py` CORSMiddleware rules and check that `VITE_API_BASE_URL` matches your backend server port (`http://localhost:8000/api`).

---

## Future Improvements

- **Dependency Graph Depth & Transitive Vulnerability Impact**: Expand transitive dependency tree depth scoring to measure indirect vulnerability propagation.
- **Monorepo Disambiguation**: Enhance package-level vs repo-level activity disambiguation for multi-package monorepos.
- **Supply Chain Name-Similarity & Typosquatting Detection**: Add automatic checks for typosquatting vulnerabilities and malicious package variants.
- **Expanded Package Ecosystems**: Support additional registries such as RubyGems (`rubygems`), NuGet (`dotnet`), and Hex (`elixir`).

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository and create a feature branch (`git checkout -b feature/amazing-feature`).
2. Run `python run_tests.py` inside `backend/` to verify zero regressions against the benchmark dataset.
3. Ensure frontend code passes linting (`npm run lint`).
4. Commit your changes and open a Pull Request.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
