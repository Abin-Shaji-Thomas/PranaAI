from typing import Dict, Tuple


EMERGENCY_KEYWORDS = {
    "cardiac": ["chest pain", "sweating", "left arm", "jaw pain", "ecg", "palpitations"],
    "respiratory": ["shortness of breath", "wheezing", "cannot breathe", "asthma", "oxygen"],
    "neurological": ["slurred speech", "facial droop", "stroke", "seizure", "confusion"],
    "trauma": ["bleeding", "injury", "fracture", "fall", "accident", "wound"],
    "infection": ["fever", "infection", "sepsis", "chills", "pus"],
    "disaster_response": ["earthquake", "flood", "collapse", "mass casualty", "evacuation"],
}


def classify_emergency(symptoms: str) -> Tuple[str, float, Dict[str, int]]:
    text = symptoms.lower()
    scores: Dict[str, int] = {key: 0 for key in EMERGENCY_KEYWORDS.keys()}

    for category, keywords in EMERGENCY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[category] += 1

    best = max(scores, key=scores.get)
    max_score = scores[best]
    if max_score == 0:
        return "general", 0.5, scores

    confidence = min(0.95, 0.4 + (max_score * 0.15))
    return best, confidence, scores
