import os
import json
from typing import Dict, List

from openai import OpenAI


def _fallback(symptoms: str, emergency_type: str) -> Dict:
	s = symptoms.lower()
	if emergency_type == "cardiac" or "chest pain" in s:
		return {
			"condition": "Acute Coronary Syndrome",
			"urgency": "CRITICAL",
			"actions": ["Administer oxygen", "Give aspirin", "Perform ECG", "Monitor vitals"],
			"reason": "Based on chest pain, sweating and possible cardiac risk indicators.",
		}
	if emergency_type == "trauma" or "bleeding" in s:
		return {
			"condition": "Hemorrhage / Trauma",
			"urgency": "HIGH",
			"actions": ["Apply direct pressure", "Control bleeding", "Prepare IV fluids", "Rapid transport"],
			"reason": "Based on trauma and blood loss indicators.",
		}
	if emergency_type == "neurological" or any(k in s for k in ["slurred speech", "facial droop", "weakness", "seizure", "stroke"]):
		return {
			"condition": "Acute Neurological Emergency",
			"urgency": "CRITICAL",
			"actions": ["Activate stroke/seizure protocol", "Assess airway and glucose", "Urgent neuro imaging pathway", "Continuous neuro-vitals monitoring"],
			"reason": "Based on acute focal neurological deficit indicators.",
		}
	if emergency_type == "disaster_response" or any(k in s for k in ["flood", "earthquake", "evacuation", "collapse"]):
		return {
			"condition": "Disaster Field Response",
			"urgency": "HIGH",
			"actions": [
				"Activate nearest safe evacuation route",
				"Isolate high-risk hazard zones and contaminated sources",
				"Prioritize vulnerable groups for assisted transfer",
				"Establish triage point and coordinate rescue logistics",
			],
			"reason": "Based on disaster incident indicators and immediate population safety risk.",
		}
	return {
		"condition": "Undetermined Emergency",
		"urgency": "MODERATE",
		"actions": ["Stabilize patient", "Monitor vitals", "Escalate for physician review"],
		"reason": "Insufficient high-confidence signal for a single category.",
	}


def _parse_actions(text: str) -> List[str]:
	actions: List[str] = []
	for line in text.splitlines():
		stripped = line.strip()
		if stripped.startswith("-") or stripped[:2].isdigit():
			actions.append(stripped.lstrip("-0123456789. "))
	return actions[:5]


def _urgency_rank(value: str) -> int:
	order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
	return order.get((value or "").upper(), 1)


def _enforce_urgency_floor(symptoms: str, emergency_type: str, urgency: str) -> str:
	lower = symptoms.lower()
	high_risk_markers = [
		"chest pain", "shortness of breath", "cannot breathe", "slurred speech",
		"facial droop", "seizure", "unresponsive", "active bleeding", "mass casualty",
	]

	required = "HIGH"
	if emergency_type in {"cardiac", "neurological"} and ("chest pain" in lower or "slurred speech" in lower or "facial droop" in lower):
		required = "CRITICAL"
	elif any(marker in lower for marker in high_risk_markers):
		required = "HIGH"

	return required if _urgency_rank(urgency) < _urgency_rank(required) else urgency


def generate_triage(symptoms: str, compressed_context: str, emergency_type: str) -> Dict:
	api_key = os.getenv("OPENAI_API_KEY", "").strip()
	model = os.getenv("LLM_MODEL", "gpt-4o-mini")
	request_timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "18"))
	if not api_key:
		result = _fallback(symptoms, emergency_type)
		result["urgency"] = _enforce_urgency_floor(symptoms, emergency_type, result.get("urgency", "MODERATE"))
		return result

	system_prompt = (
		"You are a clinical emergency triage assistant. Prioritize current symptoms and only grounded context facts. "
		"If uncertain, explicitly state uncertainty and escalate safely. Do not invent details. "
		"Return strict JSON with keys: condition, urgency, actions, reason. "
		"urgency must be one of CRITICAL/HIGH/MODERATE/LOW. actions must be a short list of imperative steps."
	)
	user_prompt = f"Emergency Type: {emergency_type}\nSymptoms: {symptoms}\nContext:\n{compressed_context}"

	try:
		client = OpenAI(api_key=api_key, timeout=request_timeout)
		completion = client.chat.completions.create(
			model=model,
			temperature=0.2,
			max_tokens=220,
			response_format={"type": "json_object"},
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
		)
		text = completion.choices[0].message.content or ""
		parsed = json.loads(text)

		condition = str(parsed.get("condition", "Undetermined Emergency")).strip() or "Undetermined Emergency"
		urgency = str(parsed.get("urgency", "MODERATE")).strip().upper()
		if urgency not in {"CRITICAL", "HIGH", "MODERATE", "LOW"}:
			urgency = "MODERATE"
		urgency = _enforce_urgency_floor(symptoms, emergency_type, urgency)

		reason = str(parsed.get("reason", "Model response parsed.")).strip() or "Model response parsed."

		actions_raw = parsed.get("actions", [])
		actions = [str(item).strip() for item in actions_raw if str(item).strip()] if isinstance(actions_raw, list) else []
		if not actions:
			actions = _parse_actions(text)
		if not actions:
			actions = _fallback(symptoms, emergency_type)["actions"]

		return {
			"condition": condition,
			"urgency": urgency,
			"actions": actions,
			"reason": reason,
		}
	except Exception:
		result = _fallback(symptoms, emergency_type)
		result["urgency"] = _enforce_urgency_floor(symptoms, emergency_type, result.get("urgency", "MODERATE"))
		return result


def generate_triage_fast(symptoms: str, emergency_type: str, compressed_context: str = "") -> Dict:
	fallback = _fallback(symptoms, emergency_type)
	fallback["urgency"] = _enforce_urgency_floor(symptoms, emergency_type, fallback.get("urgency", "MODERATE"))
	context_lower = compressed_context.lower()
	if emergency_type == "disaster_response":
		actions = fallback["actions"][:]
		if "evac" in context_lower or "evacuation" in context_lower:
			actions.insert(0, "Activate evacuation route and move vulnerable population first")
		if "contamin" in context_lower or "water" in context_lower:
			actions.insert(1, "Isolate contaminated water sources and deploy safe water points")
		fallback["actions"] = actions[:5]
		fallback["reason"] = "Based on symptoms/incident details and grounded context indicators from uploaded repository."
		return fallback

	if emergency_type == "cardiac" and ("troponin" in context_lower or "ecg" in context_lower):
		fallback["reason"] = "Based on chest pain cluster and cardiac indicators found in provided context."
	return fallback

