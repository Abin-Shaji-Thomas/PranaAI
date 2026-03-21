import json
import os
from pathlib import Path
from typing import Dict, Optional


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_PATH = BASE_DIR / "data" / "processed" / "decision_policy.json"

_POLICY_CACHE: Optional[Dict[str, object]] = None
_POLICY_CACHE_KEY: Optional[str] = None


def _default_policy() -> Dict[str, object]:
    return {
        "version": "1.0",
        "default": {
            "urgency": "MODERATE",
            "condition": "Undetermined Emergency",
            "actions": ["Stabilize patient", "Monitor vitals", "Escalate to senior clinician"],
        },
        "disaster_actions": {
            "flood": [
                "Move to higher ground immediately",
                "Avoid contact with flood water and electrical hazards",
                "Use clean drinking water and contamination control",
            ],
            "earthquake": [
                "Take cover and protect head-neck immediately",
                "Move away from glass, unstable walls, and falling objects",
                "Evacuate to open safe assembly area after shaking stops",
            ],
            "heatwave": [
                "Move patient to shaded or cooled area",
                "Start oral or IV rehydration based on condition",
                "Actively cool body and monitor temperature",
            ],
            "default": [
                "Move to designated safe zone",
                "Establish triage point",
                "Coordinate evacuation and hazard control",
            ],
        },
        "rules": [
            {
                "id": "cardiac_red_flags",
                "emergency_types": ["cardiac"],
                "any_phrases": ["chest pain", "left arm", "jaw pain", "ecg", "sweating"],
                "urgency": "CRITICAL",
                "condition": "Acute Coronary Syndrome",
                "actions": [
                    "Administer oxygen",
                    "Give aspirin if not contraindicated",
                    "Perform ECG immediately",
                    "Activate cardiac response team",
                ],
                "reason": "cardiac red flags",
            },
            {
                "id": "respiratory_distress",
                "emergency_types": ["respiratory"],
                "any_phrases": ["shortness of breath", "cannot breathe", "spo2", "wheezing"],
                "urgency": "HIGH",
                "condition": "Acute Respiratory Distress",
                "actions": [
                    "Support airway",
                    "Start oxygen therapy",
                    "Assess SpO2 and respiratory rate",
                    "Prepare nebulization or intubation pathway",
                ],
                "reason": "respiratory distress",
            },
            {
                "id": "neurological_deficit",
                "emergency_types": ["neurological"],
                "any_phrases": ["slurred speech", "facial droop", "seizure", "stroke", "one sided weakness"],
                "urgency": "CRITICAL",
                "condition": "Acute Neurological Emergency",
                "actions": [
                    "Activate stroke or seizure protocol",
                    "Check glucose and airway",
                    "Arrange urgent neuro-imaging",
                    "Continuous neuro-vitals monitoring",
                ],
                "reason": "neurological deficit",
            },
            {
                "id": "trauma_hemorrhage",
                "emergency_types": ["trauma"],
                "any_phrases": ["active bleeding", "hemorrhage", "fracture", "accident", "wound"],
                "urgency": "HIGH",
                "condition": "Trauma / Hemorrhage",
                "actions": [
                    "Control bleeding with direct pressure",
                    "Immobilize injured area",
                    "Establish IV access and fluids",
                    "Prepare rapid transfer",
                ],
                "reason": "trauma indicators",
            },
            {
                "id": "infection_risk",
                "emergency_types": ["infection"],
                "any_phrases": ["sepsis", "high fever", "chills", "infection"],
                "urgency": "HIGH",
                "condition": "Severe Infection Risk",
                "actions": [
                    "Obtain vitals and sepsis screening",
                    "Start infection control precautions",
                    "Prepare broad-spectrum treatment pathway",
                ],
                "reason": "infection risk",
            },
        ],
    }


def _cache_key_for(path: Path) -> str:
    if not path.exists():
        return f"{path.as_posix()}::missing"
    stat = path.stat()
    return f"{path.as_posix()}::{stat.st_mtime_ns}::{stat.st_size}"


def _get_policy_path() -> Path:
    configured = os.getenv("DECISION_POLICY_PATH", "").strip()
    if configured:
        return Path(configured).resolve()
    return DEFAULT_POLICY_PATH


def invalidate_decision_policy_cache() -> None:
    global _POLICY_CACHE, _POLICY_CACHE_KEY
    _POLICY_CACHE = None
    _POLICY_CACHE_KEY = None


def get_decision_policy() -> Dict[str, object]:
    global _POLICY_CACHE, _POLICY_CACHE_KEY

    path = _get_policy_path()
    key = _cache_key_for(path)
    if _POLICY_CACHE is not None and _POLICY_CACHE_KEY == key:
        return _POLICY_CACHE

    fallback = _default_policy()
    if not path.exists():
        _POLICY_CACHE = fallback
        _POLICY_CACHE_KEY = key
        return fallback

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = fallback
    except Exception:
        payload = fallback

    if not isinstance(payload.get("rules"), list):
        payload["rules"] = fallback["rules"]
    if not isinstance(payload.get("default"), dict):
        payload["default"] = fallback["default"]
    if not isinstance(payload.get("disaster_actions"), dict):
        payload["disaster_actions"] = fallback["disaster_actions"]

    _POLICY_CACHE = payload
    _POLICY_CACHE_KEY = key
    return payload


def get_decision_policy_health() -> Dict[str, object]:
    path = _get_policy_path()
    fallback = _default_policy()

    path_exists = path.exists()
    loaded_from_file = False
    used_fallback = False
    validation_errors = []

    payload: Dict[str, object]
    if not path_exists:
        payload = fallback
        used_fallback = True
        validation_errors.append("policy_file_missing")
    else:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                payload = parsed
                loaded_from_file = True
            else:
                payload = fallback
                used_fallback = True
                validation_errors.append("policy_not_object")
        except Exception:
            payload = fallback
            used_fallback = True
            validation_errors.append("policy_json_parse_error")

    rules = payload.get("rules") if isinstance(payload, dict) else []
    default_block = payload.get("default") if isinstance(payload, dict) else {}
    disaster_actions = payload.get("disaster_actions") if isinstance(payload, dict) else {}

    if not isinstance(rules, list):
        validation_errors.append("rules_not_list")
        rules = []
    if not isinstance(default_block, dict):
        validation_errors.append("default_not_object")
        default_block = {}
    if not isinstance(disaster_actions, dict):
        validation_errors.append("disaster_actions_not_object")
        disaster_actions = {}

    return {
        "path": str(path),
        "path_exists": path_exists,
        "loaded_from_file": loaded_from_file,
        "used_fallback": used_fallback,
        "version": str(payload.get("version", fallback.get("version", "unknown"))),
        "rules_count": len(rules),
        "has_default": bool(default_block),
        "disaster_profiles": len(disaster_actions),
        "validation_errors": validation_errors,
        "healthy": len(validation_errors) == 0,
    }
