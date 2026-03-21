import os
import time
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter


SUPPORTED_SCALEDOWN_MODELS = {
    "gpt-4o",
    "gpt-4o-mini",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
}


_SCALEDOWN_SESSION: Optional[requests.Session] = None


def _get_scaledown_session() -> requests.Session:
    global _SCALEDOWN_SESSION
    if _SCALEDOWN_SESSION is not None:
        return _SCALEDOWN_SESSION

    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    _SCALEDOWN_SESSION = session
    return session


def _pick_scaledown_model() -> str:
    requested = os.getenv("SCALEDOWN_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini")).strip()
    if requested in SUPPORTED_SCALEDOWN_MODELS:
        return requested
    return "gpt-4o-mini"


def _extract_provider_request_id(data: Dict, headers: requests.structures.CaseInsensitiveDict) -> str:
    candidates = [
        data.get("request_id"),
        data.get("id"),
        data.get("trace_id"),
        data.get("request_metadata", {}).get("request_id") if isinstance(data.get("request_metadata"), dict) else None,
        headers.get("x-request-id"),
        headers.get("x-trace-id"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_compressed_text(data: Dict, fallback: str) -> str:
    if isinstance(data.get("compressed_prompt"), str) and data.get("compressed_prompt", "").strip():
        return data["compressed_prompt"]

    results = data.get("results", {})
    if isinstance(results, dict):
        candidate = results.get("compressed_prompt", "")
        if isinstance(candidate, str) and candidate.strip():
            return candidate

    return fallback


def _extract_tokens(data: Dict, original_tokens: int, compressed_text: str) -> Dict[str, int]:
    doc_original = int(data.get("original_prompt_tokens", 0) or 0)
    doc_compressed = int(data.get("compressed_prompt_tokens", 0) or 0)

    legacy_original = int(data.get("total_original_tokens", 0) or 0)
    legacy_compressed = int(data.get("total_compressed_tokens", 0) or 0)

    resolved_original = doc_original or legacy_original or original_tokens
    resolved_compressed = doc_compressed or legacy_compressed or _approx_tokens(compressed_text)

    return {
        "original": max(1, resolved_original),
        "compressed": max(1, resolved_compressed),
    }


def _approx_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _context_to_natural_language(context: str) -> str:
    lines = [line.strip() for line in context.splitlines() if line.strip()]
    if len(lines) <= 2:
        return context.strip()

    max_lines = int(os.getenv("SCALEDOWN_NATURAL_MAX_LINES", "120"))
    return "\n".join(lines[:max_lines]).strip()


def _calc_savings(original_tokens: int, compressed_tokens: int) -> Dict[str, float]:
    saved = max(0, original_tokens - compressed_tokens)
    savings_percent = (saved / original_tokens * 100.0) if original_tokens > 0 else 0.0
    cost_per_million = float(os.getenv("SCALEDOWN_INPUT_COST_PER_1M", "0.15"))
    estimated_cost_saved = (saved / 1_000_000) * cost_per_million
    return {
        "tokens_saved": int(saved),
        "savings_percent": round(savings_percent, 2),
        "estimated_cost_saved_usd": round(estimated_cost_saved, 8),
    }


def compress_context(context: str, prompt: str, timeout_seconds: Optional[float] = None) -> Dict:
    api_key = os.getenv("SCALEDOWN_API_KEY", "").strip()
    api_url = os.getenv("SCALEDOWN_API_URL", "https://api.scaledown.xyz/compress/raw/")
    scaledown_model = _pick_scaledown_model()
    rate = os.getenv("SCALEDOWN_COMPRESSION_RATE", "auto")
    min_tokens = int(os.getenv("SCALEDOWN_MIN_TOKENS", "220"))
    force_all_inputs = os.getenv("SCALEDOWN_FORCE_ALL_INPUTS", "true").strip().lower() in {"1", "true", "yes", "y"}
    source_tokens = _approx_tokens(context)
    natural_context = _context_to_natural_language(context)
    natural_tokens = _approx_tokens(natural_context)
    original_tokens = natural_tokens

    if original_tokens < min_tokens and not force_all_inputs:
        savings = _calc_savings(original_tokens, original_tokens)
        return {
            "attempted_scaledown": False,
            "compressed_text": context,
            "natural_language_text": natural_context,
            "source_tokens": source_tokens,
            "original_tokens": original_tokens,
            "compressed_tokens": original_tokens,
            "compression_ratio": 1.0,
            "used_scaledown": False,
            "successful": False,
            "latency_ms": 0,
            "skip_reason": "context_below_threshold",
            "provider": "scaledown",
            "provider_request_id": "",
            "scaledown_api_url": api_url,
            "scaledown_model": scaledown_model,
            **savings,
        }

    if not api_key:
        savings = _calc_savings(original_tokens, original_tokens)
        return {
            "attempted_scaledown": False,
            "compressed_text": context,
            "natural_language_text": natural_context,
            "source_tokens": source_tokens,
            "original_tokens": original_tokens,
            "compressed_tokens": original_tokens,
            "compression_ratio": 1.0,
            "used_scaledown": False,
            "successful": False,
            "latency_ms": 0,
            "skip_reason": "missing_api_key",
            "provider": "scaledown",
            "provider_request_id": "",
            "scaledown_api_url": api_url,
            "scaledown_model": scaledown_model,
            **savings,
        }

    payload = {
        "context": natural_context,
        "prompt": (
            f"{prompt}\n"
            "Preserve medically/disaster critical facts exactly from context. "
            "Do not invent facts. Remove only repetitive or irrelevant administrative content."
        ),
        "model": scaledown_model,
        "scaledown": {"rate": rate},
    }
    max_tokens = int(os.getenv("SCALEDOWN_MAX_TOKENS", "500"))
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    effective_timeout = timeout_seconds if timeout_seconds is not None else float(os.getenv("SCALEDOWN_TIMEOUT_SECONDS", "12"))

    try:
        started = time.perf_counter()
        session = _get_scaledown_session()
        res = session.post(api_url, json=payload, headers=headers, timeout=effective_timeout)
        res.raise_for_status()
        data = res.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        provider_request_id = _extract_provider_request_id(data, res.headers)

        compressed_text = _extract_compressed_text(data, context)
        token_stats = _extract_tokens(data, original_tokens, compressed_text)
        compression_ratio = token_stats["compressed"] / max(1, token_stats["original"])
        savings = _calc_savings(token_stats["original"], token_stats["compressed"])
        reported_success = bool(data.get("successful", False))
        achieved_reduction = token_stats["compressed"] < token_stats["original"]
        used_scaledown = bool(reported_success or achieved_reduction or (compressed_text != context))
        successful = bool(reported_success or achieved_reduction)

        return {
            "attempted_scaledown": True,
            "compressed_text": compressed_text,
            "natural_language_text": natural_context,
            "source_tokens": source_tokens,
            "original_tokens": token_stats["original"],
            "compressed_tokens": token_stats["compressed"],
            "compression_ratio": round(float(compression_ratio), 4),
            "used_scaledown": used_scaledown,
            "successful": successful,
            "latency_ms": elapsed_ms,
            "skip_reason": "" if used_scaledown else "no_compression_returned",
            "provider": "scaledown",
            "provider_request_id": provider_request_id,
            "scaledown_api_url": api_url,
            "scaledown_model": scaledown_model,
            **savings,
        }
    except requests.Timeout:
        savings = _calc_savings(original_tokens, original_tokens)
        return {
            "attempted_scaledown": True,
            "compressed_text": context,
            "natural_language_text": natural_context,
            "source_tokens": source_tokens,
            "original_tokens": original_tokens,
            "compressed_tokens": original_tokens,
            "compression_ratio": 1.0,
            "used_scaledown": False,
            "successful": False,
            "latency_ms": int(effective_timeout * 1000),
            "skip_reason": "scaledown_timeout",
            "provider": "scaledown",
            "provider_request_id": "",
            "scaledown_api_url": api_url,
            "scaledown_model": scaledown_model,
            **savings,
        }
    except Exception:
        savings = _calc_savings(original_tokens, original_tokens)
        return {
            "attempted_scaledown": True,
            "compressed_text": context,
            "natural_language_text": natural_context,
            "source_tokens": source_tokens,
            "original_tokens": original_tokens,
            "compressed_tokens": original_tokens,
            "compression_ratio": 1.0,
            "used_scaledown": False,
            "successful": False,
            "latency_ms": 0,
            "skip_reason": "scaledown_error",
            "provider": "scaledown",
            "provider_request_id": "",
            "scaledown_api_url": api_url,
            "scaledown_model": scaledown_model,
            **savings,
        }
