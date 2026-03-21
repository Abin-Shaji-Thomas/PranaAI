from typing import Dict, List

from .decision_policy import get_decision_policy


URGENCY_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}


def _has_any(text: str, phrases: List[str]) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in phrases)


def _raise_urgency(current: str, candidate: str) -> str:
    if URGENCY_ORDER.get(candidate, 0) > URGENCY_ORDER.get(current, 0):
        return candidate
    return current


def _merge_actions(base: List[str], extra: List[str], limit: int = 6) -> List[str]:
    merged: List[str] = []
    seen = set()
    for item in base + extra:
        action = item.strip()
        if not action:
            continue
        key = action.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(action)
        if len(merged) >= limit:
            break
    return merged


def _as_list_of_strings(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _rule_matches(rule: Dict[str, object], emergency_type: str, text: str) -> bool:
    emergency_types = [str(item).strip().lower() for item in _as_list_of_strings(rule.get("emergency_types"))]
    any_phrases = [str(item).strip().lower() for item in _as_list_of_strings(rule.get("any_phrases"))]

    type_match = (not emergency_types) or (emergency_type in emergency_types)
    phrase_match = (not any_phrases) or _has_any(text, any_phrases)
    return type_match and phrase_match


def decide_next_actions(
    parsed_context: Dict[str, object],
    emergency_type: str,
    retrieved_chunks: List[str],
) -> Dict[str, object]:
    policy = get_decision_policy()
    default_block = policy.get("default", {}) if isinstance(policy.get("default"), dict) else {}

    symptoms = parsed_context.get("symptoms", []) if isinstance(parsed_context.get("symptoms"), list) else []
    history = parsed_context.get("history", []) if isinstance(parsed_context.get("history"), list) else []
    disaster = str(parsed_context.get("disaster", "") or "").strip().lower()

    text = " ".join([*(str(item) for item in symptoms), *(str(item) for item in history), *(retrieved_chunks or [])]).lower()

    urgency = str(default_block.get("urgency", "MODERATE")).upper()
    if urgency not in URGENCY_ORDER:
        urgency = "MODERATE"
    condition = str(default_block.get("condition", "Undetermined Emergency")).strip() or "Undetermined Emergency"
    actions = _as_list_of_strings(default_block.get("actions")) or ["Stabilize patient", "Monitor vitals", "Escalate to senior clinician"]
    reason_flags: List[str] = []

    rules = policy.get("rules", []) if isinstance(policy.get("rules"), list) else []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if not _rule_matches(rule, emergency_type, text):
            continue

        candidate_urgency = str(rule.get("urgency", "")).upper().strip()
        if candidate_urgency in URGENCY_ORDER:
            urgency = _raise_urgency(urgency, candidate_urgency)

        candidate_condition = str(rule.get("condition", "")).strip()
        if candidate_condition:
            condition = candidate_condition

        rule_actions = _as_list_of_strings(rule.get("actions"))
        if rule_actions:
            actions = _merge_actions(rule_actions, actions)

        label = str(rule.get("reason", "")).strip() or str(rule.get("id", "matched_rule")).strip() or "matched_rule"
        reason_flags.append(label)

    if emergency_type == "disaster_response" or disaster:
        urgency = _raise_urgency(urgency, "HIGH")
        condition = "Disaster Field Response"
        disaster_block = policy.get("disaster_actions", {}) if isinstance(policy.get("disaster_actions"), dict) else {}
        disaster_actions = _as_list_of_strings(disaster_block.get(disaster))
        if not disaster_actions:
            disaster_actions = _as_list_of_strings(disaster_block.get("default")) or ["Move to designated safe zone", "Establish triage point", "Coordinate evacuation and hazard control"]
        actions = _merge_actions(disaster_actions, actions)
        reason_flags.append(f"disaster context: {disaster or 'general'}")

    reason = "Rule-based decision using parsed symptoms/history and grounded retrieval context"
    if reason_flags:
        reason = f"{reason}; matched: {', '.join(reason_flags[:4])}"

    return {
        "condition": condition,
        "urgency": urgency,
        "actions": actions[:5],
        "reason": reason,
    }
