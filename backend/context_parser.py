import re
from typing import Dict, List


DISASTER_TERMS = ["flood", "earthquake", "heatwave", "cyclone", "landslide", "fire", "collapse"]
HISTORY_HINTS = ["history", "past", "previous", "known", "since", "diagnosed", "old", "chronic"]


def _normalize_items(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        item = re.sub(r"\s+", " ", value.strip().lower())
        if len(item) < 3:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _split_segments(text: str) -> List[str]:
    parts = re.split(r"[\n,;|]+", text)
    return [part.strip() for part in parts if part.strip()]


def parse_context(query_text: str, local_context: str = "", domain: str = "medical") -> Dict[str, object]:
    query = (query_text or "").strip()
    context = (local_context or "").strip()
    merged = "\n".join([value for value in [query, context] if value]).lower()

    disaster = ""
    for term in DISASTER_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", merged):
            disaster = term
            break

    symptoms: List[str] = []
    history: List[str] = []

    for segment in _split_segments(query):
        if any(hint in segment.lower() for hint in HISTORY_HINTS):
            history.append(segment)
        else:
            symptoms.append(segment)

    for segment in _split_segments(context):
        lower = segment.lower()
        if re.search(r"\b(19|20)\d{2}\b", lower) or any(hint in lower for hint in HISTORY_HINTS):
            history.append(segment)
        else:
            symptoms.append(segment)

    if domain == "disaster" and not symptoms and query:
        symptoms = [query]

    return {
        "symptoms": _normalize_items(symptoms),
        "history": _normalize_items(history),
        "disaster": disaster,
        "domain": (domain or "medical").strip().lower(),
        "raw_query": query,
    }
