import os
from typing import Dict

import requests


def compress_context(context: str, prompt: str) -> Dict:
    api_key = os.getenv("SCALEDOWN_API_KEY", "").strip()
    api_url = os.getenv("SCALEDOWN_API_URL", "https://api.scaledown.xyz/compress/raw/")
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    rate = os.getenv("SCALEDOWN_COMPRESSION_RATE", "high")

    if not api_key:
        return {
            "compressed_text": context,
            "original_tokens": max(1, len(context.split())),
            "compressed_tokens": max(1, len(context.split())),
            "compression_ratio": 0.0,
            "used_scaledown": False,
        }

    payload = {
        "context": context,
        "prompt": prompt,
        "model": llm_model,
        "max_tokens": 500,
        "scaledown": {"rate": rate},
    }
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        res = requests.post(api_url, json=payload, headers=headers, timeout=12)
        res.raise_for_status()
        data = res.json()
        return {
            "compressed_text": data["results"]["compressed_prompt"],
            "original_tokens": int(data.get("total_original_tokens", 0) or 0),
            "compressed_tokens": int(data.get("total_compressed_tokens", 0) or 0),
            "compression_ratio": float(data.get("request_metadata", {}).get("average_compression_ratio", 0.0) or 0.0),
            "used_scaledown": True,
        }
    except Exception:
        return {
            "compressed_text": context,
            "original_tokens": max(1, len(context.split())),
            "compressed_tokens": max(1, len(context.split())),
            "compression_ratio": 0.0,
            "used_scaledown": False,
        }
