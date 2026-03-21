import os
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


def generate_triage(symptoms: str, compressed_context: str, emergency_type: str) -> Dict:
	api_key = os.getenv("OPENAI_API_KEY", "").strip()
	model = os.getenv("LLM_MODEL", "gpt-4o-mini")
	if not api_key:
		return _fallback(symptoms, emergency_type)

	system_prompt = (
		"You are an emergency triage assistant. Reply concise with format:\n"
		"Condition: ...\nUrgency: CRITICAL/HIGH/MODERATE/LOW\n"
		"Actions:\n- ...\n- ...\nReason: ..."
	)
	user_prompt = f"Emergency Type: {emergency_type}\nSymptoms: {symptoms}\nContext:\n{compressed_context}"

	try:
		client = OpenAI(api_key=api_key)
		completion = client.chat.completions.create(
			model=model,
			temperature=0.2,
			max_tokens=220,
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
		)
		text = completion.choices[0].message.content or ""

		condition = "Undetermined Emergency"
		urgency = "MODERATE"
		reason = "Model response parsed."
		for line in text.splitlines():
			low = line.lower()
			if low.startswith("condition:"):
				condition = line.split(":", 1)[1].strip() or condition
			elif low.startswith("urgency:"):
				urgency = line.split(":", 1)[1].strip().upper() or urgency
			elif low.startswith("reason:"):
				reason = line.split(":", 1)[1].strip() or reason

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
		return _fallback(symptoms, emergency_type)

