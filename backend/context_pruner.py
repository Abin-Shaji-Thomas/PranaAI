import re
from datetime import datetime
from typing import Dict, List, Tuple


IRRELEVANT_BY_EMERGENCY = {
	"cardiac": ["dental", "skin", "sprain", "broken arm"],
	"respiratory": ["dental", "skin", "ankle", "orthopedic"],
	"neurological": ["dental", "cosmetic", "routine eye"],
	"trauma": ["dental", "mild allergy"],
}


def _is_recent(line: str) -> bool:
	match = re.search(r"(19|20)\d{2}", line)
	if not match:
		return True
	year = int(match.group())
	return (datetime.now().year - year) <= 7


def prune_context(patient_history: str, emergency_type: str, retrieved_chunks: List[str]) -> Tuple[str, Dict[str, float]]:
	relevant_history: List[str] = []
	history_lines = [line.strip() for line in patient_history.splitlines() if line.strip()]

	remove_terms = IRRELEVANT_BY_EMERGENCY.get(emergency_type, [])
	for line in history_lines:
		lower = line.lower()
		if any(term in lower for term in remove_terms):
			continue
		if _is_recent(line) or emergency_type in lower:
			relevant_history.append(line)

	compact_chunks: List[str] = []
	seen = set()
	for chunk in retrieved_chunks:
		c = chunk.strip()
		key = c[:200].lower()
		if c and key not in seen:
			seen.add(key)
			compact_chunks.append(c)

	original_text = "\n".join(history_lines + retrieved_chunks)
	pruned_text = "\n".join(relevant_history + compact_chunks)

	original_len = max(1, len(original_text))
	reduction = 1 - (len(pruned_text) / original_len)

	stats = {
		"original_chars": float(len(original_text)),
		"pruned_chars": float(len(pruned_text)),
		"reduction_ratio": float(round(max(0.0, reduction), 4)),
	}
	return pruned_text, stats
