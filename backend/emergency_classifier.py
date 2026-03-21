import re
from typing import Dict, Tuple


EMERGENCY_KEYWORDS = {
    "cardiac": ["chest pain", "sweating", "left arm", "jaw pain", "ecg", "palpitations"],
    "respiratory": ["shortness of breath", "wheezing", "cannot breathe", "asthma", "oxygen"],
    "neurological": ["slurred speech", "facial droop", "stroke", "seizure", "confusion"],
    "trauma": ["bleeding", "injury", "fracture", "fall", "accident", "wound"],
    "infection": ["fever", "infection", "sepsis", "chills", "pus"],
    "disaster_response": ["earthquake", "flood", "collapse", "mass casualty", "evacuation"],
}


EMERGENCY_WEIGHTS = {
    "cardiac": {
        "crushing chest pain": 4,
        "chest pain": 3,
        "left arm": 3,
        "jaw pain": 2,
        "diaphoresis": 2,
        "sweating": 2,
        "palpitations": 2,
        "ecg": 2,
    },
    "respiratory": {
        "shortness of breath": 4,
        "cannot breathe": 4,
        "low oxygen": 3,
        "spo2": 3,
        "wheezing": 2,
        "asthma": 2,
    },
    "neurological": {
        "slurred speech": 4,
        "facial droop": 4,
        "one sided weakness": 4,
        "seizure": 3,
        "stroke": 3,
        "confusion": 2,
    },
    "trauma": {
        "active bleeding": 4,
        "hemorrhage": 4,
        "fracture": 3,
        "injury": 2,
        "accident": 2,
        "wound": 2,
    },
    "infection": {
        "high fever": 3,
        "sepsis": 4,
        "infection": 2,
        "chills": 2,
        "pus": 2,
    },
    "disaster_response": {
        "mass casualty": 4,
        "evacuation": 3,
        "flood": 3,
        "earthquake": 3,
        "collapse": 3,
        "contamination": 2,
    },
}


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z]+", text.lower()) if len(token) > 2}


def _phrase_score(text: str, phrase: str) -> int:
    phrase = phrase.strip().lower()
    if not phrase:
        return 0
    if phrase in text:
        return 1

    phrase_tokens = _tokenize(phrase)
    text_tokens = _tokenize(text)
    if phrase_tokens and phrase_tokens.issubset(text_tokens):
        return 1
    return 0


def classify_emergency(symptoms: str) -> Tuple[str, float, Dict[str, int]]:
    text = symptoms.lower()
    scores: Dict[str, int] = {key: 0 for key in EMERGENCY_KEYWORDS.keys()}

    for category, keywords in EMERGENCY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[category] += 1

    for category, weighted_phrases in EMERGENCY_WEIGHTS.items():
        for phrase, weight in weighted_phrases.items():
            if _phrase_score(text, phrase):
                scores[category] += weight

    best = max(scores, key=scores.get)
    max_score = scores[best]
    if max_score == 0:
        return "general", 0.5, scores

    confidence = min(0.99, 0.45 + (max_score * 0.06))
    return best, confidence, scores
