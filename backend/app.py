from pathlib import Path
import logging
import time
import uuid
import threading
import json
import os
import hashlib

from fastapi import FastAPI, HTTPException
from fastapi import Request
from fastapi import BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool

from .config import get_settings
from .decision_policy import get_decision_policy_health
from .refinement_store import get_entry, set_error, set_pending, set_result
from .retrieval import warm_retrieval_cache
from .scaledown_compressor import compress_context
from .triage_engine import analyze_emergency


load_dotenv()
settings = get_settings()
logger = logging.getLogger("pranaai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class TriageRequest(BaseModel):
    symptoms: str = ""
    incident_details: str = ""
    patient_history: str = ""
    context_notes: str = ""
    domain: str = Field(default="medical", pattern="^(medical|disaster)$")
    mode: str = Field(default="auto", pattern="^(auto|fast|full)$")
    strict_sla: bool = False


app = FastAPI(title=settings.app_name, version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _warm_retrieval_in_background() -> None:
    try:
        stats = warm_retrieval_cache()
        logger.info("retrieval_warmup_done documents=%s faiss_indexed=%s", stats.get("documents"), stats.get("faiss_indexed"))
    except Exception as exc:
        logger.warning("retrieval_warmup_failed error=%s", exc)


def _warm_scaledown_in_background() -> None:
    enabled = os.getenv("ENABLE_SCALEDOWN_WARMUP", "true").strip().lower() in {"1", "true", "yes", "y"}
    if not enabled:
        return
    try:
        compress_context(
            context="Warmup context for emergency triage compression pipeline.",
            prompt="Warmup request. Return concise clinical summary.",
            timeout_seconds=2.0,
        )
        logger.info("scaledown_warmup_done")
    except Exception as exc:
        logger.warning("scaledown_warmup_failed error=%s", exc)


@app.on_event("startup")
def startup_warmup() -> None:
    policy_health = get_decision_policy_health()
    if policy_health.get("healthy"):
        logger.info(
            "decision_policy_ok version=%s rules=%s path=%s",
            policy_health.get("version"),
            policy_health.get("rules_count"),
            policy_health.get("path"),
        )
    else:
        logger.warning(
            "decision_policy_warning path=%s errors=%s",
            policy_health.get("path"),
            ",".join(policy_health.get("validation_errors", [])),
        )

    worker = threading.Thread(target=_warm_retrieval_in_background, daemon=True)
    worker.start()

    scaledown_worker = threading.Thread(target=_warm_scaledown_in_background, daemon=True)
    scaledown_worker.start()


@app.get("/")
def home():
    frontend = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    if frontend.exists():
        return FileResponse(frontend)
    return {"message": "PranaAI backend running", "hint": "Create frontend/index.html"}


@app.get("/health")
def health():
    policy_health = get_decision_policy_health()
    return {
        "status": "ok",
        "target_latency_ms": settings.target_latency_ms,
        "default_mode": settings.default_mode,
        "scaledown_force_all_inputs": settings.scaledown_force_all_inputs,
        "scaledown_api_url": os.getenv("SCALEDOWN_API_URL", "https://api.scaledown.xyz/compress/raw/"),
        "decision_policy": policy_health,
    }


def _expanded_case_context(case_item: dict) -> str:
    base_context = str(case_item.get("context", "")).strip()
    query = str(case_item.get("query", "")).strip()
    category = str(case_item.get("category", "general")).strip().lower() or "general"
    domain = str(case_item.get("domain", "medical")).strip().lower() or "medical"
    case_id = str(case_item.get("id", "case"))

    min_lines = int(os.getenv("SAMPLE_CASE_MIN_LINES", "120"))
    max_lines = int(os.getenv("SAMPLE_CASE_MAX_LINES", "420"))
    if max_lines < min_lines:
        max_lines = min_lines

    seed = int(hashlib.sha256(f"{case_id}|{category}|{domain}".encode("utf-8")).hexdigest()[:8], 16)
    span = max_lines - min_lines
    total_lines = min_lines + (seed % (span + 1))

    profile = _category_profile(domain, category)
    useful_bank = profile["signal"]
    noise_bank = profile["noise"]
    operational_bank = profile["ops"]

    lines = [
        f"Case Query: {query}" if query else "Case Query: unavailable",
        f"Case Domain: {domain} | Category: {category}",
    ]

    if base_context:
        for idx, raw_line in enumerate([line.strip() for line in base_context.splitlines() if line.strip()], start=1):
            lines.append(f"Base context {idx}: {raw_line}")

    for idx in range(1, total_lines + 1):
        hr = 88 + ((seed + idx * 3) % 55)
        rr = 14 + ((seed + idx * 5) % 20)
        spo2 = 84 + ((seed + idx * 7) % 15)
        systolic = 82 + ((seed + idx * 11) % 65)
        diastolic = 50 + ((seed + idx * 13) % 35)
        useful = useful_bank[(seed + idx) % len(useful_bank)].format(
            category=category,
            hr=hr,
            rr=rr,
            bp=f"{systolic}/{diastolic}",
            spo2=spo2,
            minute=idx,
        )
        noise = noise_bank[(seed + idx * 2) % len(noise_bank)].format(minute=idx)
        ops = operational_bank[(seed + idx * 4) % len(operational_bank)].format(minute=idx)

        selector = (seed + idx) % 9
        if selector in {0, 3, 6, 8}:
            lines.append(f"[{idx:03}] {useful}")
        elif selector in {2, 5}:
            lines.append(f"[{idx:03}] {ops}")
        else:
            lines.append(f"[{idx:03}] {noise}")

    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return "\n".join(lines)


def _category_profile(domain: str, category: str) -> dict:
    generic_signal = [
        "Red-flag progression for {category}; reassess airway and circulation at minute {minute}.",
        "Vitals trend HR {hr}, RR {rr}, BP {bp}, SpO2 {spo2}% with escalation watch.",
        "Medication/allergy history impacts immediate triage decision for this case.",
    ]
    generic_noise = [
        "Merged document footer and legal disclaimer copied from external template at minute {minute}.",
        "Administrative form chatter, archive references, and unrelated metadata at minute {minute}.",
        "Scheduling and billing notes not relevant to emergency response at minute {minute}.",
    ]
    generic_ops = [
        "Operational delay note: transfer queue fluctuating at minute {minute}.",
        "Cross-team handoff synchronization warning logged at minute {minute}.",
        "Resource allocation update recorded at minute {minute}.",
    ]

    medical_profiles = {
        "cardiac": {
            "signal": [
                "Chest pain with left-arm radiation and diaphoresis persists at minute {minute}.",
                "ECG concern with HR {hr}, BP {bp}, and SpO2 {spo2}% needs rapid review.",
                "Potential ACS progression with unstable hemodynamics and recurrent pain spikes.",
            ],
            "noise": generic_noise,
            "ops": [
                "Cath-lab access uncertainty documented at minute {minute}.",
                "Cardiac transfer readiness delayed due to transport congestion.",
                "Telemetry backlog and duplicate nursing relay note at minute {minute}.",
            ],
        },
        "respiratory": {
            "signal": [
                "Shortness of breath with RR {rr} and SpO2 {spo2}% suggests respiratory compromise.",
                "Accessory muscle use and inability to complete full sentences noted at minute {minute}.",
                "Oxygen demand rising despite initial support; reassess airway strategy.",
            ],
            "noise": generic_noise,
            "ops": [
                "Nebulizer allocation delay logged at minute {minute}.",
                "Respiratory support queue update captured in operations log.",
                "Duplicate monitor printout uploaded at minute {minute}.",
            ],
        },
        "neurological": {
            "signal": [
                "Sudden neuro deficit progression with speech change and unilateral weakness at minute {minute}.",
                "Neuro checks worsening with BP {bp}; urgent imaging pathway required.",
                "Seizure/post-ictal concern with airway vigilance and aspiration risk.",
            ],
            "noise": generic_noise,
            "ops": [
                "Stroke team paging delay logged at minute {minute}.",
                "Imaging corridor congestion note captured by dispatch.",
                "Repeated administrative copy of triage timestamp at minute {minute}.",
            ],
        },
        "trauma": {
            "signal": [
                "Active bleeding concern with BP {bp} and rising HR {hr} at minute {minute}.",
                "Mechanism of injury indicates multi-system trauma and shock risk.",
                "Pain escalation and perfusion decline require immediate hemorrhage control.",
            ],
            "noise": generic_noise,
            "ops": [
                "Extrication duration update posted at minute {minute}.",
                "Trauma bay turnover delay recorded in operations board.",
                "Duplicate incident narrative imported from dispatch log.",
            ],
        },
        "infection": {
            "signal": [
                "Fever/chills with hypotension trend and altered mentation at minute {minute}.",
                "Possible sepsis trajectory with tachycardia HR {hr} and perfusion concerns.",
                "Source-control and antimicrobial timing critical in this phase.",
            ],
            "noise": generic_noise,
            "ops": [
                "Lab turnaround delay update logged at minute {minute}.",
                "Sepsis bundle checklist duplicate entry detected in notes.",
                "Ward transfer bottleneck flagged by bed-management system.",
            ],
        },
    }

    disaster_profiles = {
        "flood": {
            "signal": [
                "Floodwater exposure with contamination risk and vulnerable cluster at minute {minute}.",
                "Evacuation route instability and shelter overload needs reprioritization.",
                "Water-borne illness risk indicators rising in field reports.",
            ],
            "noise": generic_noise,
            "ops": [
                "Boat dispatch queue update posted at minute {minute}.",
                "Bridge status uncertainty logged by incident command.",
                "Duplicate municipality memo imported at minute {minute}.",
            ],
        },
        "earthquake": {
            "signal": [
                "Aftershock risk with structural instability and entrapment hazard at minute {minute}.",
                "Mass-casualty triage load rising; prioritize airway/bleeding categories.",
                "Rapid shelter relocation required for vulnerable occupants.",
            ],
            "noise": generic_noise,
            "ops": [
                "Search-and-rescue sector reassignment logged at minute {minute}.",
                "Route clearance uncertainty recorded in command channel.",
                "Duplicate local authority bulletin ingested at minute {minute}.",
            ],
        },
        "heatwave": {
            "signal": [
                "Heat stress progression with dehydration signs and altered mentation at minute {minute}.",
                "Cooling resource saturation and high-risk elderly cluster identified.",
                "Renal/cardiac vulnerability requires aggressive hydration triage.",
            ],
            "noise": generic_noise,
            "ops": [
                "Cooling shelter occupancy update posted at minute {minute}.",
                "Mobile hydration unit delay note captured in field system.",
                "Duplicate weather alert summary imported at minute {minute}.",
            ],
        },
        "cyclone": {
            "signal": [
                "High-wind injury and flooding compound risk noted at minute {minute}.",
                "Coastal evacuation and shelter triage prioritization required now.",
                "Communication disruption impacts casualty routing decisions.",
            ],
            "noise": generic_noise,
            "ops": [
                "Generator outage and power restoration delay noted at minute {minute}.",
                "Transport corridor closure bulletin repeated in feed.",
                "Duplicate weather model attachment ingested at minute {minute}.",
            ],
        },
    }

    if domain == "medical":
        profile = medical_profiles.get(category, {"signal": generic_signal, "noise": generic_noise, "ops": generic_ops})
    else:
        profile = disaster_profiles.get(category, {"signal": generic_signal, "noise": generic_noise, "ops": generic_ops})

    return profile


def _ensure_category_coverage(base_cases: list[dict]) -> list[dict]:
    required_medical = ["cardiac", "respiratory", "neurological", "trauma", "infection", "obstetric", "pediatric"]
    required_disaster = ["flood", "earthquake", "heatwave", "cyclone", "landslide", "wildfire", "chemical_spill", "mass_casualty"]

    existing = {(str(case.get("domain", "")).lower(), str(case.get("category", "")).lower()) for case in base_cases if isinstance(case, dict)}
    augmented = list(base_cases)

    for category in required_medical:
        key = ("medical", category)
        if key in existing:
            continue
        augmented.append(
            {
                "id": f"med_{category}_auto",
                "domain": "medical",
                "category": category,
                "title": f"Auto-generated {category} emergency case",
                "query": f"Complex {category} emergency with evolving symptoms and unstable vitals",
                "context": f"Baseline clinical context for {category} with mixed operational and administrative data.",
            }
        )

    for category in required_disaster:
        key = ("disaster", category)
        if key in existing:
            continue
        augmented.append(
            {
                "id": f"dis_{category}_auto",
                "domain": "disaster",
                "category": category,
                "title": f"Auto-generated {category} incident case",
                "query": f"{category} incident with multi-site casualties, logistics constraints, and evolving hazards",
                "context": f"Baseline disaster context for {category} with mixed signal and administrative noise.",
            }
        )

    return augmented


def _sample_variant_case(case_item: dict, variant_index: int) -> dict:
    variant = max(1, int(variant_index))
    base_id = str(case_item.get("id", f"case_{variant}"))
    base_title = str(case_item.get("title", "Emergency case"))
    base_query = str(case_item.get("query", "")).strip()

    shift_profiles = [
        {
            "suffix": "with communication gaps",
            "context": "Channel outage reported in two zones; verbal relay introduces delayed updates and duplicate alerts.",
        },
        {
            "suffix": "with transport delays",
            "context": "Primary transfer route congested; estimated transfer delay 25-40 minutes with dynamic rerouting.",
        },
        {
            "suffix": "with multi-team handoff complexity",
            "context": "Cross-team handoff required across triage, transport, and receiving unit with partial records.",
        },
        {
            "suffix": "with constrained resources",
            "context": "Limited oxygen/PPE/critical bed capacity; prioritization protocol active for high-risk cases.",
        },
    ]
    shift = shift_profiles[(variant - 1) % len(shift_profiles)]

    adapted_query = base_query
    if adapted_query:
        adapted_query = f"{adapted_query}; scenario variant {variant} {shift['suffix']}"

    adapted_item = {
        **case_item,
        "id": f"{base_id}_v{variant}",
        "title": f"{base_title} (Variant {variant})",
        "query": adapted_query,
    }

    expanded_context = _expanded_case_context(adapted_item)
    expanded_context = f"{expanded_context}\nVariant profile note: {shift['context']}\nVariant marker: {base_id}-v{variant}"
    max_lines = int(os.getenv("SAMPLE_CASE_MAX_LINES", "420"))
    context_lines = [line for line in expanded_context.splitlines() if line.strip()]
    if len(context_lines) > max_lines:
        expanded_context = "\n".join(context_lines[:max_lines])
    return {
        **adapted_item,
        "context": expanded_context,
        "context_lines": _count_lines(expanded_context),
    }


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return len([line for line in text.splitlines() if line.strip()])


@app.get("/sample-cases")
def sample_cases():
    library_path = Path(__file__).resolve().parent.parent / "data" / "processed" / "sample_cases_library.json"
    if not library_path.exists():
        return {"version": "missing", "cases": []}

    try:
        payload = json.loads(library_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"version": "invalid", "cases": []}
        base_cases = payload.get("cases", []) if isinstance(payload.get("cases", []), list) else []
        base_cases = _ensure_category_coverage(base_cases)
        expanded_cases = []
        variants = max(1, int(os.getenv("SAMPLE_CASE_VARIANTS", "3")))
        for case in base_cases:
            if not isinstance(case, dict):
                continue
            for variant_index in range(1, variants + 1):
                expanded_cases.append(_sample_variant_case(case, variant_index))
        return {
            "version": str(payload.get("version", "1.0")),
            "generated_for": str(payload.get("generated_for", "PranaAI")),
            "count": len(expanded_cases),
            "variants_per_case": variants,
            "cases": expanded_cases,
        }
    except Exception:
        return {"version": "error", "cases": []}


@app.middleware("http")
async def add_request_observability(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    if settings.require_api_key and request.url.path not in {"/", "/health", "/docs", "/openapi.json", "/redoc"}:
        incoming_key = request.headers.get("x-api-key", "").strip()
        if not settings.app_api_key or incoming_key != settings.app_api_key:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized: invalid or missing x-api-key"})

    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    response.headers["X-Request-Id"] = request_id
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)

    logger.info(
        "request_id=%s method=%s path=%s status=%s latency_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def _run_full_refinement(request_id: str, query_text: str, local_context: str, domain: str) -> None:
    try:
        full_result = analyze_emergency(
            query_text,
            local_context,
            mode="full",
            domain=domain,
            allow_scaledown=True,
        )
        full_result.update({"response_type": "final", "request_id": request_id})
        set_result(request_id, full_result)
    except Exception as exc:
        set_error(request_id, str(exc))


def _start_refinement_thread(request_id: str, query_text: str, local_context: str, domain: str) -> None:
    worker = threading.Thread(
        target=_run_full_refinement,
        args=(request_id, query_text, local_context, domain),
        daemon=True,
    )
    worker.start()


def _refinement_enabled() -> bool:
    return os.getenv("ENABLE_BACKGROUND_REFINEMENT", "false").strip().lower() in {"1", "true", "yes", "y"}


@app.post("/triage")
async def triage(payload: TriageRequest, background_tasks: BackgroundTasks):
    try:
        query_text = (payload.symptoms or payload.incident_details or "").strip()
        if len(query_text) < 5:
            raise HTTPException(status_code=422, detail="Provide symptoms (medical) or incident_details (disaster) with at least 5 characters")

        local_context = "\n".join(
            [value for value in [payload.patient_history.strip(), payload.context_notes.strip()] if value]
        )

        auto_strict_sla = settings.auto_strict_sla_on_fast and (payload.mode in {"fast", "auto"})
        forced_strict_sla = bool(settings.force_strict_sla_all_requests)
        use_strict_sla = bool(forced_strict_sla or payload.strict_sla or auto_strict_sla)

        if use_strict_sla:
            request_id = str(uuid.uuid4())
            preliminary = await run_in_threadpool(
                analyze_emergency,
                query_text,
                local_context,
                "fast",
                payload.domain,
                True,
            )
            if _refinement_enabled():
                set_pending(request_id)
                _start_refinement_thread(request_id, query_text, local_context, payload.domain)
                refinement_status = "pending"
            else:
                set_result(request_id, {**preliminary, "response_type": "final", "request_id": request_id})
                refinement_status = "disabled"
            preliminary.update(
                {
                    "response_type": "preliminary",
                    "request_id": request_id,
                    "refinement_status": refinement_status,
                    "strict_sla_mode": (
                        "forced_all_policy"
                        if forced_strict_sla
                        else ("explicit" if payload.strict_sla else "auto_fast_policy")
                    ),
                }
            )
            return preliminary

        final_result = await run_in_threadpool(
            analyze_emergency,
            query_text,
            local_context,
            payload.mode,
            payload.domain,
            True,
        )
        final_result.update({"response_type": "final"})
        return final_result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/triage/refinement/{request_id}")
def get_refinement(request_id: str):
    entry = get_entry(request_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown request_id")
    return entry


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)