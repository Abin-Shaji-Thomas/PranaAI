# Datasets and Retrieval Usage

## Why datasets exist in this project
Datasets in PranaAI are used primarily for:
- Retrieval grounding (evidence snippets for triage)
- Policy/rule support and sample-case generation
- Demonstration and evaluation scenarios

They are not used for live online model training during request handling.

## Active Data Assets

### `data/raw/medical/*`
Source corpus files loaded by retrieval to build searchable text chunks.

### `data/processed/master_triage_dataset.csv`
Consolidated dataset used as part of retrieval corpus.

### `data/processed/retrieval_index/*`
Precomputed retrieval artifacts:
- `docs.json` (serialized indexed text units)
- `embeddings.npy` (semantic vectors, when enabled)
- `manifest.json` (index compatibility metadata)

This cache speeds up retrieval startup/runtime and can be rebuilt from corpus.

### `data/processed/sample_cases_library.json`
Base sample scenarios used by `GET /sample-cases` and UI sample loading.

### `data/processed/decision_policy.json`
Deterministic policy/rule configuration used by decision engine.

### `data/processed/refinement_store.db`
Operational SQLite state for background refinement tracking (not a training dataset).

## How retrieval uses data
`backend/retrieval.py`:
1. Walks supported files in `data/` (`.txt`, `.csv`, `.json`, `.jsonl`)
2. Extracts text-like chunks
3. Tokenizes + optionally embeds
4. Builds/loads persisted index
5. Scores and returns top contextual snippets by query + emergency context

## Rebuilding retrieval index
Index is refreshed when corpus signature changes.
If needed, deleting `data/processed/retrieval_index/*` forces regeneration on next warmup/query.

## Minimal data set for project functionality
Required:
- `data/processed/decision_policy.json`
- `data/processed/sample_cases_library.json`
- at least one retrieval corpus source (`data/raw/medical/*` and/or processed CSV)

Optional but performance-recommended:
- `data/processed/retrieval_index/*`

Operational state:
- `data/processed/refinement_store.db` (created/updated automatically)
