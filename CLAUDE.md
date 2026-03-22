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

### LLM-First Pipeline

The pipeline is **LLM-primary**: the LLM (Gemini via Replicate) is the sole classifier and field extractor. KB/RAG only provides context to help the LLM make better decisions — they never override LLM output.

```
POST /solve (app/main.py)
  → parse_attachments(files)              # app/attachment_parser.py
  → parse_prompt(prompt)                  # app/parser.py — LLM primary, rule-based fallback
    → LLM with KB-enriched system prompt  # app/llm_parser.py — _get_system_prompt()
    → _post_llm_enrichment()              # Targeted regex for fields LLM misses
  → validate_and_normalize_task(parsed)   # app/validator.py — normalize, don't drop
  → build_plan(parsed_task)               # app/planner.py — execution plan
  → execute_plan(client, plan)            # app/workflows/executor.py — all task logic
  → retry on failure (thinking=high)      # RAG error context injected on retry
  → {"status": "completed"}
```

**Context layers** (each feeds into the LLM, none overrides it):
1. **Base prompt** (`_SYSTEM_PROMPT_BASE` in `llm_parser.py`) — task type definitions, output format, few-shot examples
2. **KB context** (`_build_kb_context()`) — all 26 task specs from `task_registry.json` injected into system prompt
3. **RAG context** (`_get_rag_context()` in `main.py`) — TF-IDF retrieval injected into user message; error-specific on retry
4. **Post-LLM enrichment** (`_post_llm_enrichment()` in `parser.py`) — targeted regex for fields the LLM consistently misses

### Key Modules

- **`app/llm_parser.py`** — LLM parser with dynamic KB-enriched system prompt. `_get_system_prompt()` concatenates base instructions + KB context. Contains all few-shot examples.
- **`app/parser.py`** — Entry point. LLM primary, rule-based fallback for UNSUPPORTED/BANK_RECONCILIATION/CORRECT_LEDGER_ERRORS. `_post_llm_enrichment()` adds targeted regex extractions.
- **`app/planner.py`** — `build_plan()` converts `ParsedTask` → `ExecutionPlan` with named steps. Also has keyword-based task detection for rule-based fallback.
- **`app/validator.py`** — Normalizes fields (phones, dates, org numbers), validates prerequisites. Does NOT drop unknown fields — only removes KB-defined `forbidden_fields`.
- **`app/workflows/executor.py`** — Core execution engine. Handles all task types with prerequisite resolution and system-generated account retry logic.
- **`app/kb/task_registry.json`** — Source of truth for task specs: allowed fields, forbidden fields, gotchas, prerequisites.
- **`app/kb/rag.py`** — TF-IDF cosine similarity search over `rag_index.json` for error context on retry.
- **`app/clients/tripletex.py`** — HTTP client with `find_single`, `create_resource`, `update_resource` etc. Tracks all operations.
- **`app/schemas.py`** — `TaskType` enum (25 types), `ParsedTask`, `ExecutionPlan`, `SolveRequest`/`SolveResponse`.
- **`app/error_handling.py`** — Classifies Tripletex API errors into categories (recoverable vs terminal).

### Adding a New Task Type

1. Add value to `TaskType` enum in `app/schemas.py`.
2. Add keyword patterns in `app/planner.py` `TASK_KEYWORDS` and step sequence in `PLAN_STEPS`.
3. Add execution logic in `app/workflows/executor.py` `execute_plan()`.
4. Add a few-shot example in `app/llm_parser.py` `_SYSTEM_PROMPT_BASE`.
5. Add task spec in `app/kb/task_registry.json` (allowed fields, forbidden fields, gotchas).
6. Add validation rules in `app/validator.py` if needed.
7. Add post-LLM regex in `app/parser.py` `_post_llm_enrichment()` if the LLM consistently misses a field.

### Improving the Pipeline (Layer by Layer)

When a competition run fails, diagnose which layer needs fixing:

**1. Base Prompt** (`app/llm_parser.py` → `_SYSTEM_PROMPT_BASE`)
- Add/update **few-shot examples** for task types the LLM misclassifies or extracts poorly. Currently 14 examples covering all major task types.
- Update **task type descriptions** in the prompt to clarify ambiguous cases.
- Keep examples realistic — use actual competition prompts that failed.

**2. KB Task Registry** (`app/kb/task_registry.json`)
- Add **gotchas** when the Tripletex API rejects a field placement (e.g., "startDate belongs in employments array, not top level").
- Add **forbidden_fields** when the API returns 422 for a specific field — the validator auto-removes these.
- Update **allowed_parsed_fields** to document what the executor actually uses.
- KB context is injected into the LLM system prompt via `_build_kb_context()` — changes take effect immediately.

**3. RAG Index** (`app/kb/rag_index.json`)
- Add entries for **specific API errors** the agent encounters — RAG is queried with the error message on retry.
- Rebuild: add new entries directly to `rag_index.json` (TF-IDF index, no separate build step).
- RAG context goes in the **user message** (not system prompt) — useful for error-specific retry context.

**4. Post-LLM Enrichment** (`app/parser.py` → `_post_llm_enrichment()`)
- Add **targeted regex** only for fields the LLM consistently fails to extract across multiple languages.
- Current enrichments: travel cost items, department names, employee birthDate alias, project billing activity/hours, dimension voucher values.
- Keep minimal — every enrichment here is a workaround for an LLM limitation.

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

## Bug Fix Workflow (Competition Regressions)

When a competition run fails, follow this cycle:

1. **User pastes logs** from a failed competition submission.
2. **Diagnose the layer**: Is it LLM misclassification (base prompt)? Missing field (post-LLM enrichment)? API rejection (KB forbidden fields / executor)? Wrong account (system-generated account retry)?
3. **Fix the appropriate layer** — see "Improving the Pipeline" above.
4. **Add a regression test** in `tests/test_competition_regressions.py` using the exact prompt from the logs.
5. **Run only the new test** (`pytest tests/test_competition_regressions.py::test_name -v`) — fast iteration.
6. **Commit and push** to both `origin` and `vercel` remotes (`git push vercel <branch>:main`).
7. **Run the full regression suite occasionally** (`pytest tests/test_competition_regressions.py -v`) — not every fix, just periodically.

The regression test file has two sections:
- **Prompt-level tests**: call `parse_prompt()` → `validate_and_normalize_task()` on real competition prompts. No API calls.
- **Validator tests**: construct a `ParsedTask` directly and verify the validator normalizes correctly without dropping fields.

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
