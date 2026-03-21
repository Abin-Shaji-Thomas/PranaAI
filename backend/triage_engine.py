import time
import os
from typing import Dict

from .context_parser import parse_context
from .context_pruner import prune_context
from .context_pruner import prune_context_for_scaledown
from .decision_engine import decide_next_actions
from .emergency_classifier import classify_emergency
from .llm_engine import generate_triage
from .retrieval import retrieve_context
from .scaledown_compressor import compress_context
from .utils import compute_severity_score


def _clip_text(value: str, limit: int = 7000) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n...[truncated for display]"


def _raw_preview_limit() -> int:
    return int(os.getenv("RAW_CONTEXT_PREVIEW_MAX_CHARS", "50000"))


def _budget_context_for_mode(text: str, execution_mode: str) -> str:
    if execution_mode != "fast":
        return text

    max_chars = int(os.getenv("FAST_MODE_CONTEXT_MAX_CHARS", "2200"))
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _budget_history_for_fast_mode(text: str, execution_mode: str) -> str:
    if execution_mode != "fast":
        return text

    max_chars = int(os.getenv("FAST_MODE_HISTORY_MAX_CHARS", "3200"))
    if len(text) <= max_chars:
        return text

    head = int(max_chars * 0.7)
    tail = max_chars - head
    return f"{text[:head]}\n...[history truncated for SLA]...\n{text[-tail:]}"


def _resolve_mode(requested_mode: str) -> str:
    mode = (requested_mode or "auto").lower().strip()
    if mode in {"fast", "full"}:
        return mode

    default_mode = os.getenv("TRIAGE_DEFAULT_MODE", "fast").strip().lower()
    if default_mode in {"fast", "full"}:
        return default_mode
    return "fast"


def _should_use_full_auto(symptoms: str, patient_history: str, emergency_type: str, confidence: float) -> tuple[bool, str]:
    auto_conf_threshold = float(os.getenv("AUTO_FULL_CONFIDENCE_THRESHOLD", "0.7"))
    auto_history_tokens = int(os.getenv("AUTO_FULL_HISTORY_TOKENS", "180"))

    history_tokens = len(patient_history.split())
    symptoms_lower = symptoms.lower()
    ambiguous_markers = ["unknown", "unclear", "not sure", "mixed symptoms", "multiple symptoms"]

    if confidence < auto_conf_threshold:
        return True, "low_classifier_confidence"
    if emergency_type in {"general", "disaster_response"}:
        return True, "complex_domain_requires_full"
    if history_tokens >= auto_history_tokens:
        return True, "large_history_context"
    if any(marker in symptoms_lower for marker in ambiguous_markers):
        return True, "ambiguous_symptoms"

    return False, "default_fast_for_sla"


def _urgency_rank(value: str) -> int:
    order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
    return order.get((value or "").upper(), 1)


def _select_safer_decision(rule_based: Dict, llm_based: Dict) -> Dict:
    if _urgency_rank(rule_based.get("urgency", "MODERATE")) > _urgency_rank(llm_based.get("urgency", "MODERATE")):
        merged_actions = []
        seen = set()
        for action in rule_based.get("actions", []) + llm_based.get("actions", []):
            text = str(action).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            merged_actions.append(text)
            if len(merged_actions) >= 5:
                break

        safer = dict(llm_based)
        safer["urgency"] = rule_based.get("urgency", llm_based.get("urgency", "MODERATE"))
        safer["actions"] = merged_actions or rule_based.get("actions", llm_based.get("actions", []))
        safer["reason"] = f"{llm_based.get('reason', 'Reasoning result')}; safety floor applied from deterministic decision engine"
        return safer
    return llm_based


def analyze_emergency(
    symptoms: str,
    patient_history: str = "",
    mode: str = "auto",
    domain: str = "medical",
    allow_scaledown: bool = True,
) -> Dict:
    start = time.perf_counter()
    requested_mode = (mode or "auto").lower().strip()
    original_patient_history = patient_history or ""
    parsed_context = parse_context(symptoms, patient_history, domain)

    t0 = time.perf_counter()
    emergency_type, confidence, _ = classify_emergency(symptoms)
    t_classify = (time.perf_counter() - t0) * 1000

    if requested_mode == "auto":
        use_full, decision_reason = _should_use_full_auto(symptoms, patient_history, emergency_type, confidence)
        execution_mode = "full" if use_full else "fast"
    else:
        execution_mode = _resolve_mode(requested_mode)
        decision_reason = f"explicit_{execution_mode}"

    patient_history = _budget_history_for_fast_mode(patient_history, execution_mode)

    t0 = time.perf_counter()
    retrieval_top_k = 1 if execution_mode == "fast" else 4
    fast_disable_semantic = os.getenv("FAST_MODE_DISABLE_SEMANTIC_RETRIEVAL", "true").strip().lower() in {"1", "true", "yes", "y"}
    use_semantic_retrieval = not (execution_mode == "fast" and fast_disable_semantic)
    skip_fast_retrieval = os.getenv("FAST_MODE_SKIP_RETRIEVAL", "true").strip().lower() in {"1", "true", "yes", "y"}
    if execution_mode == "fast" and skip_fast_retrieval:
        retrieved = []
    else:
        retrieved = retrieve_context(
            symptoms,
            emergency_type,
            top_k=retrieval_top_k,
            domain=domain,
            use_semantic=use_semantic_retrieval,
        )
    t_retrieval = (time.perf_counter() - t0) * 1000

    disable_fast_pruner = os.getenv("FAST_MODE_DISABLE_PRUNER", "false").strip().lower() in {"1", "true", "yes", "y"}
    if execution_mode == "fast" and disable_fast_pruner:
        pruned_context = patient_history
        prune_stats = {
            "original_chars": float(len(patient_history)),
            "pruned_chars": float(len(patient_history)),
            "reduction_ratio": 0.0,
            "critical_retention_ratio": 1.0,
            "critical_terms_in_source_context": 0.0,
        }
        t_prune = 0.0
    elif execution_mode == "fast":
        t0 = time.perf_counter()
        pruned_context, prune_stats = prune_context_for_scaledown(
            raw_context=patient_history,
            query_text=symptoms,
            emergency_type=emergency_type,
        )
        t_prune = (time.perf_counter() - t0) * 1000
    else:
        t0 = time.perf_counter()
        pruned_context, prune_stats = prune_context(
            patient_history,
            emergency_type,
            retrieved,
            query_text=symptoms,
        )
        t_prune = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    rule_decision = decide_next_actions(parsed_context, emergency_type, retrieved)
    t_decision = (time.perf_counter() - t0) * 1000

    raw_input_context = original_patient_history.strip()
    base_context = (pruned_context or patient_history or "").strip()
    if symptoms.strip():
        context_for_compression = f"Symptoms/Incident: {symptoms.strip()}\n{base_context}".strip()
    else:
        context_for_compression = base_context
    context_for_compression = _budget_context_for_mode(context_for_compression, execution_mode)

    compression_prompt = (
        f"Emergency type: {emergency_type}. "
        f"Question: {symptoms}. "
        "Keep only triage-critical facts relevant to this question. "
        "Preserve red-flag symptoms, vitals, medications, allergies, hazard notes, and evacuation constraints."
    )

    if allow_scaledown:
        fast_timeout_ms = int(os.getenv("FAST_MODE_SCALEDOWN_TIMEOUT_MS", "1500"))
        timeout_seconds = (fast_timeout_ms / 1000.0) if execution_mode == "fast" else None
        t0 = time.perf_counter()
        compression = compress_context(
            context=context_for_compression,
            prompt=compression_prompt,
            timeout_seconds=timeout_seconds,
        )
        t_compress = (time.perf_counter() - t0) * 1000
    else:
        compression = {
            "attempted_scaledown": False,
            "compressed_text": context_for_compression,
            "natural_language_text": context_for_compression,
            "source_tokens": max(1, len(context_for_compression.split())),
            "original_tokens": max(1, len(context_for_compression.split())),
            "compressed_tokens": max(1, len(context_for_compression.split())),
            "compression_ratio": 1.0,
            "used_scaledown": False,
            "successful": False,
            "latency_ms": 0,
            "tokens_saved": 0,
            "savings_percent": 0.0,
            "estimated_cost_saved_usd": 0.0,
            "skip_reason": "strict_sla_preliminary",
        }
        t_compress = 0.0

    if execution_mode == "fast":
        llm = rule_decision
        t_llm = 0.0
    else:
        t0 = time.perf_counter()
        llm = generate_triage(symptoms, compression["compressed_text"], emergency_type)
        llm = _select_safer_decision(rule_decision, llm)
        t_llm = (time.perf_counter() - t0) * 1000

    severity = compute_severity_score(emergency_type, confidence, llm["urgency"])
    total_ms = (time.perf_counter() - start) * 1000

    return {
        "execution_mode": execution_mode,
        "input_format": {
            "domain": domain,
            "query_field": "symptoms_or_incident_details",
            "context_field": "patient_history_or_context_notes",
        },
        "mode_decision": {
            "requested_mode": requested_mode,
            "resolved_mode": execution_mode,
            "reason": decision_reason,
        },
        "structured_input": parsed_context,
        "emergency_type": emergency_type,
        "confidence": round(confidence, 3),
        "possible_condition": llm["condition"],
        "urgency": llm["urgency"],
        "recommended_actions": llm["actions"],
        "reason": llm["reason"],
        "severity_score": severity,
        "context_comparison": {
            "raw_input_context": _clip_text(raw_input_context, _raw_preview_limit()),
            "pruned_context": _clip_text(pruned_context),
            "natural_language_context": _clip_text(compression.get("natural_language_text", pruned_context)),
            "compressed_context": _clip_text(compression["compressed_text"]),
        },
        "evidence_snippets": [chunk[:220] for chunk in retrieved[:3]],
        "context_stats": {
            "pruning": prune_stats,
            "deterministic_decision_ms": round(t_decision, 2),
            "compression": {
                "used_scaledown": compression["used_scaledown"],
                "attempted_scaledown": compression.get("attempted_scaledown", False),
                "successful": compression.get("successful", False),
                "provider": compression.get("provider", ""),
                "provider_request_id": compression.get("provider_request_id", ""),
                "scaledown_api_url": compression.get("scaledown_api_url", ""),
                "scaledown_model": compression.get("scaledown_model", ""),
                "latency_ms": compression.get("latency_ms", 0),
                "source_tokens": compression.get("source_tokens", compression["original_tokens"]),
                "original_tokens": compression["original_tokens"],
                "compressed_tokens": compression["compressed_tokens"],
                "compression_ratio": compression["compression_ratio"],
                "tokens_saved": compression.get("tokens_saved", 0),
                "savings_percent": compression.get("savings_percent", 0.0),
                "estimated_cost_saved_usd": compression.get("estimated_cost_saved_usd", 0.0),
                "skip_reason": compression.get("skip_reason", ""),
            },
        },
        "latency_ms": {
            "classification": round(t_classify, 2),
            "retrieval": round(t_retrieval, 2),
            "pruning": round(t_prune, 2),
            "compression": round(t_compress, 2),
            "llm": round(t_llm, 2),
            "total": round(total_ms, 2),
            "target_under_500ms": total_ms < 500,
        },
    }