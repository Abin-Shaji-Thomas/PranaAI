# PranaAI Project Documentation

## Documentation Map
- [README.md](README.md) (inside `docs/`) — docs navigation index
- [ARCHITECTURE.md](ARCHITECTURE.md) — component and runtime architecture
- [IMPLEMENTATION_JOURNEY.md](IMPLEMENTATION_JOURNEY.md) — what was built and why
- [API_AND_CONFIG.md](API_AND_CONFIG.md) — endpoint and env reference
- [DATASETS_USAGE.md](DATASETS_USAGE.md) — dataset/retrieval/indexing purpose
- [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) — setup, troubleshooting, operations

## 1) Project Summary
PranaAI is a real-time emergency triage assistant for:
- Medical emergency intake
- Disaster incident response

It accepts direct operator input (symptoms/incident + history/situation), runs deterministic + AI-assisted triage, applies intelligent context pruning and ScaleDown compression, and returns a clinically usable handoff output.

This repo is intentionally cleaned to keep only what is required for the current product behavior.

## 2) Current Product Scope
### Included
- FastAPI backend API
- Single-page frontend dashboard
- Real-time triage pipeline with strict-SLA preliminary mode
- Intelligent context pruning diagnostics
- ScaleDown compression telemetry
- Built-in sample library endpoint
- Core pipeline unit tests

### Excluded (removed as non-essential)
- Upload ingestion flow and related parser module
- Legacy benchmark scripts and generated benchmark reports
- Temporary cache folders and obsolete planning docs
- Unused disaster/testing raw files that were not used by runtime retrieval

## 3) Tech Stack
- Backend: Python, FastAPI, Pydantic
- Frontend: Vanilla HTML/CSS/JavaScript (single page)
- LLM/Compression Integrations: OpenAI-compatible generation + ScaleDown compression API
- Retrieval: local corpus retrieval with optional embeddings (Sentence Transformers + FAISS)
- Storage: SQLite (refinement state)
- Config: `.env` + `python-dotenv`

## 4) Runtime Architecture
1. User enters query and optional context in frontend.
2. Frontend calls `POST /triage`.
3. Backend parses input and classifies emergency type.
4. Context retrieval runs (policy and mode dependent).
5. Intelligent pruner keeps high-signal context and removes noise.
6. ScaleDown compresses pruned context (with timeout/fallback policy).
7. Decision engine returns urgency, condition, and recommended actions.
8. In full mode, deeper reasoning can refine output with a deterministic safety floor.
9. Frontend renders summary, checklist, handoff report, timing, and context comparisons.

## 5) Key Backend Modules
- `backend/app.py`
  - FastAPI app, routes, middleware, startup warmups, sample-case generation.
- `backend/triage_engine.py`
  - End-to-end orchestration for parse → classify → retrieve → prune → compress → decide.
- `backend/context_parser.py`
  - Extracts structured symptoms/history/disaster signals.
- `backend/context_pruner.py`
  - General pruning + intelligent pre-ScaleDown pruning stats.
- `backend/decision_engine.py`
  - Deterministic urgency/condition/action logic.
- `backend/decision_policy.py`
  - Externalized policy load + validation.
- `backend/retrieval.py`
  - Corpus load, lexical/semantic retrieval, index persistence.
- `backend/scaledown_compressor.py`
  - Compression request handling, telemetry normalization, fallback behavior.
- `backend/llm_engine.py`
  - Full-mode reasoning generation.
- `backend/refinement_store.py`
  - SQLite store for background refinement lifecycle.

## 6) Frontend UX Model
- Single-flow desktop landscape layout (no forced left/right split after output).
- Sections ordered for operations:
  - Summary
  - Medical Staff Handoff Report
  - Immediate Next Action
  - Clinical details/checklist
  - Evidence/timing/compression/pruning comparisons
- Smooth reveal transitions for readable movement without clutter.

## 7) Data Layout
- `data/processed/decision_policy.json` — triage decision rules
- `data/processed/sample_cases_library.json` — base sample library
- `data/processed/master_triage_dataset.csv` — consolidated dataset
- `data/processed/retrieval_index/` — persisted retrieval index artifacts
- `data/processed/refinement_store.db` — refinement state DB
- `data/raw/medical/*` — source files used by retrieval loader

## 8) API Endpoints
- `GET /`
  - Serves frontend UI
- `GET /health`
  - Runtime health + decision policy state
- `GET /sample-cases`
  - Expanded case library for testing/demo
- `POST /triage`
  - Main triage endpoint
- `GET /triage/refinement/{request_id}`
  - Background refinement polling endpoint

## 9) Environment Configuration (Important)
Required or commonly used variables:
- `OPENAI_API_KEY`
- `SCALEDOWN_API_KEY`
- `SCALEDOWN_API_URL`
- `SCALEDOWN_MODEL`
- `TRIAGE_DEFAULT_MODE`
- `TARGET_LATENCY_MS`
- `DECISION_POLICY_PATH`
- `FORCE_STRICT_SLA_ALL_REQUESTS`
- `AUTO_STRICT_SLA_ON_FAST`
- `FAST_MODE_SKIP_RETRIEVAL`
- `FAST_MODE_SCALEDOWN_TIMEOUT_MS`
- `SAMPLE_CASE_MIN_LINES`
- `SAMPLE_CASE_MAX_LINES`
- `SAMPLE_CASE_VARIANTS`

Copy `.env.example` to `.env` and adjust values for your environment.

## 10) Accuracy and Safety Notes
- Deterministic decision policy provides a stable safety floor.
- Full mode can add richer reasoning while preserving safer urgency when needed.
- Clinical checklist now distinguishes urgency and severity band clearly.
- This tool supports triage assistance and does not replace licensed clinical judgment.

## 11) Operational Commands
From repo root:
- Install deps: `pip install -r requirements.txt`
- Run app: `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload`
- Run tests: `python -m unittest tests/test_core_pipeline.py`

## 12) Repository Cleanup Record
This cleanup removed:
- Unused ingestion/upload module and upload artifacts
- Legacy benchmark scripts/reports
- Obsolete planning/pitch documents
- Redundant cache and temporary raw testing/disaster files
- Unused Python dependencies

The current repository is focused on the active triage product path only.

## 13) Recommended Next Enhancements
- Add API schema examples per endpoint in `API_AND_CONFIG.md`
- Add reproducible evaluation dataset split for quality benchmarking
- Add CI workflow to run tests and policy validation on every PR
