import re
import os
from datetime import datetime
from typing import Dict, List, Tuple

from .emergency_classifier import EMERGENCY_KEYWORDS


IRRELEVANT_BY_EMERGENCY = {
	"cardiac": ["dental", "skin", "sprain", "broken arm"],
	"respiratory": ["dental", "skin", "ankle", "orthopedic"],
	"neurological": ["dental", "cosmetic", "routine eye"],
	"trauma": ["dental", "mild allergy"],
}


GLOBAL_RELEVANCE_TERMS = {
	"allergy", "medication", "drug", "bp", "blood pressure", "oxygen", "spo2",
	"pulse", "ecg", "heart", "chest", "breath", "stroke", "seizure", "bleeding",
	"fracture", "fever", "sepsis", "vitals", "diabetes", "hypertension",
}


MIN_RELEVANT_WORDS = 6


CRITICAL_SIGNAL_TERMS = {
	"chest pain", "shortness of breath", "cannot breathe", "spo2", "oxygen", "ecg",
	"slurred speech", "facial droop", "seizure", "stroke", "bleeding", "hemorrhage",
	"unconscious", "unresponsive", "evacuation", "mass casualty", "contamination",
}


ADMIN_NOISE_TERMS = {
	"billing", "invoice", "policy number", "insurance id", "claim", "address", "zipcode",
	"fax", "email", "appointment", "marketing", "promotion", "follow us", "terms and conditions",
	"copyright", "www", "http", "cookie policy", "disclaimer",
}


CLINICAL_PRIORITY_TERMS = {
	"allergy", "allergies", "medication", "medications", "dose", "vitals", "bp", "hr", "rr", "spo2",
	"oxygen", "ecg", "st elevation", "troponin", "blood pressure", "pulse", "temperature", "glucose",
	"pregnant", "anticoagulant", "insulin", "sepsis", "stroke", "bleeding", "fracture", "burn",
	"evacuation", "contamination", "hazmat", "mass casualty",
}


def _tokenize(text: str) -> set:
	return {tok for tok in re.findall(r"[a-zA-Z]+", text.lower()) if len(tok) > 2}


def _line_is_clinically_relevant(line: str, emergency_type: str) -> bool:
	lower = line.lower()
	tokens = _tokenize(lower)

	emergency_terms = set()
	for term in EMERGENCY_KEYWORDS.get(emergency_type, []):
		emergency_terms.update(_tokenize(term))

	if emergency_type == "disaster_response":
		emergency_terms.update({"evacuation", "casualty", "rescue", "shelter", "triage"})

	if tokens.intersection(emergency_terms):
		return True
	if tokens.intersection(GLOBAL_RELEVANCE_TERMS):
		return True

	return False


def _contains_critical_signal(text: str) -> bool:
	lower = text.lower()
	if any(term in lower for term in CRITICAL_SIGNAL_TERMS):
		return True
	return bool(re.search(r"\b(bp|hr|rr|spo2|o2|temp)\b", lower))


def _extract_critical_terms(text: str) -> set[str]:
	lower = text.lower()
	return {term for term in CRITICAL_SIGNAL_TERMS if term in lower}


def _is_recent(line: str) -> bool:
	match = re.search(r"(19|20)\d{2}", line)
	if not match:
		return True
	year = int(match.group())
	return (datetime.now().year - year) <= 7


def _split_segments(text: str) -> List[str]:
	if not text.strip():
		return []

	raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
	segments: List[str] = []
	for line in raw_lines:
		parts = re.split(r"(?<=[\.;])\s+", line)
		for part in parts:
			candidate = part.strip(" -\t")
			if len(candidate) >= 18:
				segments.append(candidate)

	if not segments and text.strip():
		fallback_parts = re.split(r"(?<=[\.;])\s+", text.strip())
		segments = [part.strip() for part in fallback_parts if len(part.strip()) >= 18]

	return segments


def _segment_score(segment: str, query_tokens: set, emergency_terms: set, emergency_type: str) -> float:
	lower = segment.lower()
	tokens = _tokenize(lower)

	score = 0.0
	if not tokens:
		return score

	score += len(tokens.intersection(query_tokens)) * 4.0
	score += len(tokens.intersection(emergency_terms)) * 3.5

	if _contains_critical_signal(segment):
		score += 16.0

	if any(term in lower for term in CLINICAL_PRIORITY_TERMS):
		score += 9.0

	if emergency_type and emergency_type.replace("_", " ") in lower:
		score += 4.0

	if any(noise in lower for noise in ADMIN_NOISE_TERMS):
		score -= 12.0

	if len(tokens) < 4 and not _contains_critical_signal(segment):
		score -= 5.0

	return score


def _classify_segment(
	segment: str,
	query_tokens: set,
	emergency_terms: set,
	emergency_type: str,
	score: float,
) -> Tuple[str, List[str]]:
	lower = segment.lower()
	tokens = _tokenize(lower)
	reasons: List[str] = []

	if tokens.intersection(query_tokens):
		reasons.append("query_overlap")
	if tokens.intersection(emergency_terms):
		reasons.append("emergency_keyword")
	if _contains_critical_signal(segment):
		reasons.append("critical_signal")
	if any(term in lower for term in CLINICAL_PRIORITY_TERMS):
		reasons.append("clinical_priority")

	has_noise = any(noise in lower for noise in ADMIN_NOISE_TERMS)
	if has_noise:
		reasons.append("administrative_noise")

	if score > 0 and not has_noise:
		return "useful", reasons or ["scored_positive"]

	if score > 8 and "critical_signal" in reasons:
		return "useful", reasons

	if has_noise and "critical_signal" not in reasons:
		return "noise", reasons or ["administrative_noise"]

	if score <= 0:
		return "noise", reasons or ["low_signal"]

	return "useful", reasons or ["fallback_useful"]


def prune_context_for_scaledown(
	raw_context: str,
	query_text: str,
	emergency_type: str,
) -> Tuple[str, Dict[str, float]]:
	segments = _split_segments(raw_context)
	if not segments:
		return "", {
			"original_chars": 0.0,
			"pruned_chars": 0.0,
			"reduction_ratio": 0.0,
			"critical_retention_ratio": 1.0,
			"critical_terms_in_source_context": 0.0,
			"selected_segments": 0.0,
		}

	query_tokens = _tokenize(query_text)
	emergency_terms: set[str] = set()
	for term in EMERGENCY_KEYWORDS.get(emergency_type, []):
		emergency_terms.update(_tokenize(term))

	scored: List[Tuple[float, int, str]] = []
	classification_rows: List[Dict[str, object]] = []
	for idx, segment in enumerate(segments):
		score = _segment_score(segment, query_tokens, emergency_terms, emergency_type)
		segment_type, reasons = _classify_segment(segment, query_tokens, emergency_terms, emergency_type, score)
		classification_rows.append(
			{
				"index": idx,
				"segment": segment,
				"score": round(float(score), 2),
				"type": segment_type,
				"reasons": reasons,
			}
		)
		if score > 0:
			scored.append((score, idx, segment))

	if not scored:
		scored = [(0.1, idx, segment) for idx, segment in enumerate(segments[:6])]

	scored.sort(key=lambda row: row[0], reverse=True)
	max_chars = int(os.getenv("FAST_MODE_PRUNER_MAX_CHARS", "1400"))
	max_segments = int(os.getenv("FAST_MODE_PRUNER_MAX_SEGMENTS", "14"))

	selected = scored[:max_segments]
	selected.sort(key=lambda row: row[1])
	selected_indices = {row[1] for row in selected}

	builder: List[str] = []
	total_chars = 0
	for _, _, segment in selected:
		remaining = max_chars - total_chars
		if remaining <= 0:
			break
		chunk = segment if len(segment) <= remaining else segment[:remaining]
		builder.append(chunk)
		total_chars += len(chunk) + 1

	pruned_text = "\n".join(builder).strip()
	original_text = "\n".join(segments)

	if not pruned_text:
		pruned_text = "\n".join(segments[:2])[:max_chars]

	original_critical_terms = _extract_critical_terms(original_text)
	retained_critical_terms = _extract_critical_terms(pruned_text)
	critical_retention_ratio = 1.0
	if original_critical_terms:
		critical_retention_ratio = len(retained_critical_terms.intersection(original_critical_terms)) / len(original_critical_terms)

	if original_critical_terms and critical_retention_ratio < 0.5:
		fallback = "\n".join([seg for seg in segments if _contains_critical_signal(seg)])
		if fallback.strip():
			pruned_text = fallback[:max_chars]
			retained_critical_terms = _extract_critical_terms(pruned_text)
			critical_retention_ratio = len(retained_critical_terms.intersection(original_critical_terms)) / max(1, len(original_critical_terms))

	original_len = max(1, len(original_text))
	reduction = 1 - (len(pruned_text) / original_len)

	stats = {
		"original_chars": float(len(original_text)),
		"pruned_chars": float(len(pruned_text)),
		"reduction_ratio": float(round(max(0.0, reduction), 4)),
		"critical_retention_ratio": float(round(critical_retention_ratio, 4)),
		"critical_terms_in_source_context": float(len(original_critical_terms)),
		"selected_segments": float(len(builder)),
		"total_segments": float(len(segments)),
		"useful_segments_detected": float(sum(1 for row in classification_rows if row.get("type") == "useful")),
		"noise_segments_detected": float(sum(1 for row in classification_rows if row.get("type") == "noise")),
		"kept_useful_segments": float(sum(1 for row in classification_rows if row.get("index") in selected_indices and row.get("type") == "useful")),
		"dropped_noise_segments": float(sum(1 for row in classification_rows if row.get("index") not in selected_indices and row.get("type") == "noise")),
		"kept_examples": [
			{
				"text": str(row.get("segment", ""))[:180],
				"score": row.get("score", 0.0),
				"reasons": row.get("reasons", []),
			}
			for row in classification_rows
			if row.get("index") in selected_indices
		][:5],
		"dropped_noise_examples": [
			{
				"text": str(row.get("segment", ""))[:180],
				"score": row.get("score", 0.0),
				"reasons": row.get("reasons", []),
			}
			for row in classification_rows
			if row.get("index") not in selected_indices and row.get("type") == "noise"
		][:5],
	}
	return pruned_text, stats


def prune_context(
	patient_history: str,
	emergency_type: str,
	retrieved_chunks: List[str],
	query_text: str = "",
) -> Tuple[str, Dict[str, float]]:
	relevant_history: List[str] = []
	history_lines = [line.strip() for line in patient_history.splitlines() if line.strip()]

	remove_terms = IRRELEVANT_BY_EMERGENCY.get(emergency_type, [])
	for line in history_lines:
		lower = line.lower()
		if any(term in lower for term in remove_terms):
			continue
		if len(_tokenize(line)) < MIN_RELEVANT_WORDS and not _contains_critical_signal(line):
			continue
		if emergency_type in lower:
			relevant_history.append(line)
			continue
		if _line_is_clinically_relevant(line, emergency_type) and _is_recent(line):
			relevant_history.append(line)

	compact_chunks: List[str] = []
	seen = set()
	for chunk in retrieved_chunks:
		c = chunk.strip()
		if not c:
			continue
		chunk_lower = c.lower()
		if any(term in chunk_lower for term in remove_terms):
			continue
		if not _line_is_clinically_relevant(c, emergency_type) and not _contains_critical_signal(c):
			continue
		key = c[:200].lower()
		if key not in seen:
			seen.add(key)
			compact_chunks.append(c)

	original_text = "\n".join(history_lines + retrieved_chunks)
	pruned_text = "\n".join(relevant_history + compact_chunks)

	original_critical_terms = _extract_critical_terms(original_text)
	retained_critical_terms = _extract_critical_terms(pruned_text)
	critical_retention_ratio = 1.0
	if original_critical_terms:
		critical_retention_ratio = len(retained_critical_terms.intersection(original_critical_terms)) / len(original_critical_terms)

	if original_critical_terms and critical_retention_ratio < 0.6:
		pruned_text = "\n".join(relevant_history + retrieved_chunks)

	original_len = max(1, len(original_text))
	reduction = 1 - (len(pruned_text) / original_len)

	stats = {
		"original_chars": float(len(original_text)),
		"pruned_chars": float(len(pruned_text)),
		"reduction_ratio": float(round(max(0.0, reduction), 4)),
		"critical_retention_ratio": float(round(critical_retention_ratio, 4)),
		"critical_terms_in_source_context": float(len(original_critical_terms)),
	}
	return pruned_text, stats
