# Operations Runbook

## Local Development Setup
1. Create/activate virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Configure environment:
   - `copy .env.example .env`
   - Fill API keys and runtime variables.

## Run the Application
- Start server:
  - `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload`
- Open UI:
  - `http://127.0.0.1:8000`

## Basic Health Checks
- `GET /health`
- Verify:
  - service status is `ok`
  - decision policy is `healthy`
  - expected mode/latency settings are loaded

## Test Command
- `python -m unittest tests/test_core_pipeline.py`

## Common Runtime Issues

### 1) Server does not start
Check:
- active Python env
- missing dependencies (`pip install -r requirements.txt`)
- syntax/runtime trace in startup logs

### 2) `uvicorn` exits quickly
Check:
- import errors in backend modules
- malformed `.env` values (integer/bool parsing)
- unavailable optional external services causing startup path exceptions

### 3) Slow responses
Check:
- `FAST_MODE_*` controls
- retrieval embedding settings
- ScaleDown timeout values
- external provider latency

### 4) No/low evidence snippets
Check:
- availability and quality of source corpus files
- retrieval index validity (`data/processed/retrieval_index`)
- domain mismatch in input (`medical` vs `disaster`)

### 5) Background refinement not completing
Check:
- `ENABLE_BACKGROUND_REFINEMENT`
- entries in `data/processed/refinement_store.db`
- logs for provider failures

## Deployment Considerations
- Configure `REQUIRE_API_KEY=true` for protected environments.
- Keep `.env` secrets out of repo and logs.
- Use reverse proxy/TLS in production.
- Pin dependency versions if reproducibility is required.

## Backup/Recovery Notes
- `decision_policy.json` and `sample_cases_library.json` are critical configuration assets.
- `refinement_store.db` is operational state and can be recreated if lost.
- `retrieval_index` can be regenerated from corpus, but may take time depending on corpus size.
