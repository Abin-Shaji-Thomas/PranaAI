from typing import Dict


BASE_SEVERITY = {
	"cardiac": 88,
	"respiratory": 82,
	"neurological": 86,
	"trauma": 80,
	"infection": 72,
	"disaster_response": 90,
	"general": 65,
}


URGENCY_BOOST = {
	"CRITICAL": 8,
	"HIGH": 4,
	"MODERATE": 0,
	"LOW": -8,
}


def compute_severity_score(emergency_type: str, confidence: float, urgency: str) -> Dict:
	base = BASE_SEVERITY.get(emergency_type, BASE_SEVERITY["general"])
	confidence_boost = int(round((max(0.0, min(1.0, confidence)) - 0.5) * 20))
	urgency_boost = URGENCY_BOOST.get(urgency.upper(), 0)
	score = max(0, min(100, base + confidence_boost + urgency_boost))

	if score >= 90:
		band = "CRITICAL"
	elif score >= 75:
		band = "HIGH"
	elif score >= 55:
		band = "MODERATE"
	else:
		band = "LOW"

	return {
		"score": score,
		"band": band,
	}

