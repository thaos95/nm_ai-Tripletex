# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

nm-ai2 is a Python 3.11+ monorepo. The active project is **Tripletex/** — a FastAPI agent that receives natural-language prompts, parses them into structured plans, and executes them against the Tripletex ERP API. The other top-level directories (Astar Island, Grocery Bot, NorgesGruppen Data) are placeholders.

## Build & Run Commands

All development happens inside `Tripletex/`:

```bash
cd Tripletex
pip install -e .[dev]          # Install with dev dependencies
uvicorn app.main:app --reload  # Run locally (port 8000)
```

### Testing

```bash
cd Tripletex
pytest                              # Run all tests
pytest tests/test_parser.py         # Single file
pytest tests/test_parser.py::test_name  # Single test
```

CI runs `pytest` from the repo root with Python 3.11 (see `.github/workflows/ci.yml`).

### Docker / Deploy

```bash
cd Tripletex
docker build -t tripletex-agent .
docker run -p 8000:8000 tripletex-agent
gcloud run deploy tripletex-agent --source . --region europe-north1 --allow-unauthenticated
```

## Architecture

### Request Flow

```
POST /solve (app/main.py)
  → parse_attachments(files)              # app/attachment_parser.py
  → parse_prompt(prompt)                  # app/parser.py — rule-based + LLM
  → validate_and_normalize_task(parsed)   # app/validator.py — field normalization
  → build_plan(parsed_task)               # app/planner.py — execution plan
  → execute_plan(client, plan)            # app/workflows/executor.py — all task logic
  → {"status": "completed"}
```

### Key Modules

- **`app/parser.py`** — Main parser entry point. Rule-based field extraction with LLM fallback. Produces `ParsedTask`.
- **`app/llm_parser.py`** — Optional LLM-based parser (OpenAI/Replicate). Called by parser.py when API key is set.
- **`app/planner.py`** — `build_plan()` converts `ParsedTask` → `ExecutionPlan` with named steps. Also has keyword-based task detection.
- **`app/validator.py`** — Normalizes fields (phones, dates, org numbers), validates prerequisites, drops unknown fields.
- **`app/workflows/executor.py`** — Core execution engine. Handles all 24 task types with prerequisite resolution (customer, employee, product, etc.).
- **`app/clients/tripletex.py`** — HTTP client with `find_single`, `create_resource`, `update_resource` etc. Tracks all operations.
- **`app/schemas.py`** — `TaskType` enum (25 types), `ParsedTask`, `ExecutionPlan`, `SolveRequest`/`SolveResponse`.
- **`app/error_handling.py`** — Classifies Tripletex API errors into categories (recoverable vs terminal).
- **`app/actions/`** — Legacy handlers (bypassed by workflows/executor). Kept for backward compatibility.

### Adding a New Task Type

1. Add value to `TaskType` enum in `app/schemas.py`.
2. Add keyword patterns in `app/planner.py` `TASK_KEYWORDS` and step sequence in `PLAN_STEPS`.
3. Add execution logic in `app/workflows/executor.py` `execute_plan()`.
4. Add field extraction in `app/parser.py` if needed.
5. Add validation rules in `app/validator.py` if needed.

## Configuration

Environment variables (see `Tripletex/.env.example`):

- `TRIPLETEX_AGENT_API_KEY` — Optional API key to protect `/solve`
- `TRIPLETEX_VERIFY_TLS` — TLS verification (default: true)
- `OPENAI_API_KEY` / `OPENAI_MODEL` — Optional LLM parser
- `TRIPLETEX_ENABLE_PREFLIGHT` — Enable pre-execution validation
- `TRIPLETEX_ENABLE_BANK_ACCOUNT_CREATION` — Auto-create bank accounts for invoices
- `TRIPLETEX_DEFAULT_BANK_ACCOUNT_NUMBER` / `_NAME` / `_TYPE` — Bank account defaults

## Conventions

- Python 3.11+ type hints throughout
- Pydantic v2 for all data models
- Tests use pytest; test files are in `Tripletex/tests/`
- The codebase is bilingual: code is in English, documentation/comments sometimes in Norwegian
- Stateless design: each `/solve` request is independent
- Synchronous httpx client (not async)

## Competition Context

This agent is built for the NM i AI Tripletex competition. Key scoring rules:

- **30 task types** across 3 tiers (Tier 1 = x1, Tier 2 = x2, Tier 3 = x3 multiplier)
- **56 variants per task** (7 languages x 8 data sets) — prompts in nb, en, es, pt, nn, de, fr
- **5-minute timeout** per submission; fresh Tripletex sandbox each run
- **Scoring**: field-by-field correctness normalized to 0–1, multiplied by tier. Perfect correctness unlocks an **efficiency bonus** (fewer API calls + zero 4xx errors = up to 2x tier score)
- Best score per task is kept; bad runs never lower your score
- All API calls go through a proxy at the provided `base_url`; auth is Basic Auth with username `0` and session token as password
- Competition docs are in `docs/tripletex/` (overview, scoring, endpoint spec, sandbox, examples)

## Branch and PR Conventions

- **Main branch**: `main` (production). Current development branch: `amanda` → `feature/tripletex-continued`.
- Feature branches from `main`: `feature/<slug>` or `feature/<number>-<slug>`.
- PRs into `main`.

## Worktree Convention

- Main checkout stays on the primary development branch.
- Worktrees at `~/ws/wt/nm-ai2/<number>-<slug>`.
- Use for non-trivial features, parallel work, or risky changes.
- Each worktree gets its own Claude session: `claude --resume <number>-<slug>`.
- Clean up after merge.

## High-Risk Areas

- **`app/clients/tripletex.py`** — API client and auth; changes affect all task types
- **`app/actions/__init__.py`** — Handler registry; incorrect registration breaks dispatch
- **`.github/workflows/`** — CI/CD pipelines
- **`Tripletex/.env.example`** — Configuration template; keep in sync with `app/config.py`
- **`app/main.py`** — `/solve` endpoint and exception handlers; the competition entry point

## Do Not

- Modify `.env` files unless explicitly told to (`.env.example` is fine)
- Commit secrets or credentials
- Skip pre-commit hooks with `--no-verify`
- Force-push to `main`
- Change the `/solve` request/response contract (it's defined by the competition)
- Add unnecessary API calls — every extra call and every 4xx error reduces the efficiency score
