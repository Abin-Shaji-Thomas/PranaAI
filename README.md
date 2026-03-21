# PranaAI — Emergency Triage Assistant

PranaAI is a real-time emergency triage platform for medical and disaster workflows. It combines deterministic safety logic with AI-assisted reasoning, intelligent context pruning, and compression telemetry to produce operationally useful triage outputs.

## Why PranaAI
- Rapid triage output path with low-latency runtime modes
- Deterministic safety floor for urgency/action consistency
- Explainable context pruning before compression/reasoning
- ScaleDown visibility with before/after token and latency metrics
- Clinician-friendly handoff-oriented desktop interface

## Core Capabilities
- Multi-mode execution: `fast`, `full`, `auto`
- Strict-SLA preliminary response + optional background refinement
- Structured parsing from messy free-text input
- Grounded retrieval from local corpus
- Evidence snippets, timing breakdown, and context comparison output
- Single-flow landscape UI for smooth operator workflow

## Tech Stack
- Backend: Python, FastAPI, Pydantic
- Frontend: HTML, CSS, JavaScript (single-page app)
- Integrations: OpenAI-compatible inference + ScaleDown compression
- Retrieval: lexical + optional semantic retrieval (Sentence Transformers + FAISS)
- Persistence: SQLite (`refinement_store.db`)
- Configuration: `.env` with `python-dotenv`

## Documentation
- Main docs index: [docs/README.md](docs/README.md)
- Master overview: [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Implementation journey: [docs/IMPLEMENTATION_JOURNEY.md](docs/IMPLEMENTATION_JOURNEY.md)
- API/config reference: [docs/API_AND_CONFIG.md](docs/API_AND_CONFIG.md)
- Dataset usage: [docs/DATASETS_USAGE.md](docs/DATASETS_USAGE.md)
- Operations runbook: [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md)

## Repository Structure
- `backend/` — API app and triage pipeline modules
- `frontend/index.html` — operator dashboard
- `data/raw/medical/` — retrieval source corpus
- `data/processed/` — decision policy, sample library, retrieval index, refinement DB
- `docs/` — full technical and operational documentation
- `tests/` — core unit test suite

## API Surface
- `GET /` — serve frontend
- `GET /health` — health + policy metadata
- `GET /sample-cases` — expanded sample scenarios for UI/testing
- `POST /triage` — primary triage endpoint
- `GET /triage/refinement/{request_id}` — refinement status endpoint

## Quick Start

### 1) Clone and install
```bash
git clone <your-repo-url>
cd PranaAI
pip install -r requirements.txt
```

### 2) Configure environment
```bash
copy .env.example .env
```
Set required keys:
- `OPENAI_API_KEY`
- `SCALEDOWN_API_KEY`

Recommended runtime controls:
- `TRIAGE_DEFAULT_MODE`
- `TARGET_LATENCY_MS`
- `FORCE_STRICT_SLA_ALL_REQUESTS`
- `FAST_MODE_SCALEDOWN_TIMEOUT_MS`
- `SAMPLE_CASE_MIN_LINES`
- `SAMPLE_CASE_MAX_LINES`
- `SAMPLE_CASE_VARIANTS`

### 3) Run locally
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```
Open: `http://127.0.0.1:8000`

## Running Tests
```bash
python -m unittest tests/test_core_pipeline.py
```

## End-to-End Processing Flow
1. Parse input into structured emergency signals.
2. Classify emergency type and confidence.
3. Retrieve relevant context from local corpus.
4. Prune non-essential/noisy context.
5. Compress context with ScaleDown.
6. Compute urgency/actions via deterministic engine.
7. Optionally refine in full mode with safety-floor merge.
8. Return decision + evidence + telemetry for UI rendering.

## Contribution Guide
1. Fork and create a focused feature/fix branch.
2. Keep changes scoped to the active product path.
3. Update docs/tests alongside behavioral changes.
4. Run tests before opening a PR.
5. In PR description include:
   - problem statement
   - change summary
   - validation results (tests/screenshots/logs)

## Important Notes
- Product scope is direct input triage (no upload workflow in current version).
- External provider keys must stay in `.env` only.
- PranaAI is decision support and does not replace licensed clinical judgment.
