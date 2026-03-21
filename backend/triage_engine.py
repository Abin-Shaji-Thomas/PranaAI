import time
from typing import Dict

from .context_pruner import prune_context
from .emergency_classifier import classify_emergency
from .llm_engine import generate_triage
from .retrieval import retrieve_context
from .scaledown_compressor import compress_context
from .utils import compute_severity_score


def analyze_emergency(symptoms: str, patient_history: str = "") -> Dict:
    start = time.perf_counter()

    t0 = time.perf_counter()
    emergency_type, confidence, _ = classify_emergency(symptoms)
    t_classify = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    retrieved = retrieve_context(symptoms, emergency_type, top_k=4)
    t_retrieval = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    pruned_context, prune_stats = prune_context(patient_history, emergency_type, retrieved)
    t_prune = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    compression = compress_context(
        context=pruned_context,
        prompt="Provide emergency triage recommendation with urgency and immediate actions",
    )
    t_compress = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    llm = generate_triage(symptoms, compression["compressed_text"], emergency_type)
    t_llm = (time.perf_counter() - t0) * 1000

    severity = compute_severity_score(emergency_type, confidence, llm["urgency"])
    total_ms = (time.perf_counter() - start) * 1000

    return {
        "emergency_type": emergency_type,
        "confidence": round(confidence, 3),
        "possible_condition": llm["condition"],
        "urgency": llm["urgency"],
        "recommended_actions": llm["actions"],
        "reason": llm["reason"],
        "severity_score": severity,
        "context_stats": {
            "pruning": prune_stats,
            "compression": {
                "used_scaledown": compression["used_scaledown"],
                "original_tokens": compression["original_tokens"],
                "compressed_tokens": compression["compressed_tokens"],
                "compression_ratio": compression["compression_ratio"],
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