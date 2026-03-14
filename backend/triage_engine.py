def analyze_emergency(symptoms: str):

    text = symptoms.lower()

    if "chest pain" in text or "sweating" in text:
        return {
            "emergency_type": "cardiac",
            "possible_condition": "Acute Coronary Syndrome",
            "urgency": "CRITICAL",
            "recommended_actions": [
                "Administer oxygen",
                "Give aspirin",
                "Perform ECG",
                "Monitor vitals"
            ]
        }

    if "bleeding" in text or "injury" in text:
        return {
            "emergency_type": "trauma",
            "possible_condition": "Hemorrhage",
            "urgency": "HIGH",
            "recommended_actions": [
                "Apply pressure",
                "Control bleeding",
                "Prepare IV fluids"
            ]
        }

    return {
        "emergency_type": "unknown",
        "possible_condition": "Undetermined",
        "urgency": "MEDIUM",
        "recommended_actions": [
            "Further medical evaluation required"
        ]
    }