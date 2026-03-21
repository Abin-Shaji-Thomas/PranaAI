# PranaAI Architecture

## System Overview
PranaAI is a single-service triage platform with:
- FastAPI backend (`backend/`)
- Single-page frontend (`frontend/index.html`)
- Local data/retrieval corpus (`data/`)
- External AI/compression providers (OpenAI-compatible + ScaleDown)

## High-Level Flow
1. Operator enters query in UI (medical symptoms or disaster incident details).
2. UI calls `POST /triage`.
3. Backend parses text into structured signals.
4. Emergency classifier assigns emergency type and confidence.
5. Retrieval collects relevant context from local corpus.
6. Pruner removes low-value/noisy context.
7. ScaleDown compresses context for latency and token efficiency.
8. Decision engine (deterministic) computes urgency/actions.
9. Optional full reasoning refines output while preserving safety floor.
10. UI renders handoff report, checklist, evidence, timing, and compression telemetry.

## Backend Components
- `app.py`
  - API routes, middleware, health checks, startup warmup, sample-case endpoint.
- `triage_engine.py`
  - Core orchestrator for parsing, retrieval, pruning, compression, and decisioning.
- `context_parser.py`
  - Converts free text into structured symptom/history/disaster signals.
- `emergency_classifier.py`
  - Classifies likely emergency family.
- `retrieval.py`
  - Hybrid lexical/semantic retrieval from local corpora.
- `context_pruner.py`
  - Intelligent context reduction and quality diagnostics.
- `scaledown_compressor.py`
  - Compression adapter + telemetry normalization.
- `decision_engine.py`
  - Deterministic triage decision logic.
- `decision_policy.py`
  - Externalized policy loading and validation.
- `llm_engine.py`
  - Full-mode deep reasoning path.
- `refinement_store.py`
  - SQLite persistence for background refinement lifecycle.

## Frontend Design
The UI is optimized for desktop operations with:
- Single-flow landscape layout
- Clinician-first section ordering
- Handoff report first-class actions (copy/print/download)
- Structured checklist and telemetry cards
- Smooth transitions without split-panel clutter

## Data and Persistence
- `data/raw/medical/*`: source corpus consumed by retrieval loader
- `data/processed/master_triage_dataset.csv`: consolidated tabular corpus
- `data/processed/retrieval_index/*`: persisted retrieval docs + embeddings + manifest
- `data/processed/sample_cases_library.json`: sample/test scenario base set
- `data/processed/decision_policy.json`: deterministic policy rules
- `data/processed/refinement_store.db`: background refinement state database

## Runtime Modes
- `fast`: deterministic low-latency path
- `full`: deeper reasoning path + safety floor merge
- `auto`: policy-based mode selection

Strict-SLA path can return immediate preliminary output and continue full refinement in background.

## Safety and Reliability Boundaries
- Deterministic policy acts as triage safety floor.
- Full reasoning cannot silently lower safer urgency in conflict scenarios.
- Telemetry exposes decision/compression context while avoiding secret leakage.
- This system is decision support and not a replacement for licensed clinical judgment.
