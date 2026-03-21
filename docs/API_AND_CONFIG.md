# API and Configuration Reference

## API Endpoints

### `GET /`
Serves frontend dashboard (`frontend/index.html`).

### `GET /health`
Returns service health and policy metadata.

Typical fields include:
- `status`
- `target_latency_ms`
- `default_mode`
- `scaledown_force_all_inputs`
- `decision_policy` object (`healthy`, `rules_count`, `version`, etc.)

### `GET /sample-cases`
Returns expanded sample scenario library.
- Source base: `data/processed/sample_cases_library.json`
- Includes category coverage and variants based on env settings

### `POST /triage`
Main endpoint for triage.

#### Request schema (logical)
- `domain`: `medical | disaster`
- `symptoms`: medical query text
- `incident_details`: disaster query text
- `patient_history`: optional history
- `context_notes`: optional disaster context
- `mode`: `auto | fast | full`
- `strict_sla`: boolean

#### Response shape (high-level)
- Mode and execution metadata
- Structured parsed input
- Emergency type and confidence
- Urgency, condition, recommended actions
- Severity score
- Context comparison blocks
- Evidence snippets
- Pruning and compression stats
- Stage latency metrics

### `GET /triage/refinement/{request_id}`
Checks background refinement status.
- `pending`
- `complete` + final result
- `error`

## Configuration (`.env`)

### Core keys
- `OPENAI_API_KEY`
- `SCALEDOWN_API_KEY`
- `SCALEDOWN_API_URL`
- `SCALEDOWN_MODEL`

### Runtime behavior
- `TRIAGE_DEFAULT_MODE`
- `TARGET_LATENCY_MS`
- `FORCE_STRICT_SLA_ALL_REQUESTS`
- `AUTO_STRICT_SLA_ON_FAST`
- `ENABLE_BACKGROUND_REFINEMENT`

### Fast path controls
- `FAST_MODE_SKIP_RETRIEVAL`
- `FAST_MODE_DISABLE_SEMANTIC_RETRIEVAL`
- `FAST_MODE_DISABLE_PRUNER`
- `FAST_MODE_HISTORY_MAX_CHARS`
- `FAST_MODE_CONTEXT_MAX_CHARS`
- `FAST_MODE_SCALEDOWN_TIMEOUT_MS`

### Sample generation controls
- `SAMPLE_CASE_MIN_LINES`
- `SAMPLE_CASE_MAX_LINES`
- `SAMPLE_CASE_VARIANTS`

### Retrieval controls
- `RETRIEVAL_ENABLE_EMBEDDINGS`
- `RETRIEVAL_EMBED_MODEL`
- `RETRIEVAL_EMBED_BATCH_SIZE`

### Policy path
- `DECISION_POLICY_PATH` (defaults to `data/processed/decision_policy.json`)

## Security Notes
- Keep `.env` out of source control.
- Do not expose provider keys or key fingerprints in API/UI.
- Use `REQUIRE_API_KEY=true` and `APP_API_KEY=...` if deploying publicly.
