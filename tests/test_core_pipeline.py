import unittest
import json
import os
from pathlib import Path
import tempfile

from backend.context_parser import parse_context
from backend.context_pruner import prune_context
from backend.decision_engine import decide_next_actions
from backend.decision_policy import invalidate_decision_policy_cache


class TestCorePipeline(unittest.TestCase):
    def test_parser_extracts_symptoms_history_and_disaster(self):
        parsed = parse_context(
            query_text="severe chest pain, sweating, shortness of breath in flood area",
            local_context="history: diabetes since 2015; previous dental issue 2010",
            domain="medical",
        )
        self.assertIn("severe chest pain", parsed["symptoms"])
        self.assertIn("history: diabetes since 2015", parsed["history"])
        self.assertEqual(parsed["disaster"], "flood")

    def test_pruner_retains_critical_signals(self):
        history = "old dental issue 2010\nchest pain with low SpO2 and severe sweating"
        retrieved = [
            "Cardiac emergency signs include chest pain, ECG changes, and oxygen desaturation.",
            "Routine cosmetic dentistry follow-up can be scheduled.",
        ]
        pruned, stats = prune_context(history, "cardiac", retrieved, query_text="chest pain low oxygen")
        self.assertIn("chest pain", pruned.lower())
        self.assertGreaterEqual(stats["critical_retention_ratio"], 0.6)

    def test_decision_engine_cardiac_critical(self):
        parsed = {
            "symptoms": ["chest pain", "sweating", "left arm pain"],
            "history": ["hypertension"],
            "disaster": "",
            "domain": "medical",
            "raw_query": "chest pain and sweating",
        }
        decision = decide_next_actions(parsed, "cardiac", ["ECG changes with troponin rise"])
        self.assertEqual(decision["urgency"], "CRITICAL")
        self.assertTrue(any("ecg" in action.lower() for action in decision["actions"]))

    def test_decision_engine_disaster_actions(self):
        parsed = {
            "symptoms": ["injury and contamination risk"],
            "history": [],
            "disaster": "flood",
            "domain": "disaster",
            "raw_query": "flood injury",
        }
        decision = decide_next_actions(parsed, "disaster_response", ["evacuation route available"])
        self.assertIn(decision["urgency"], {"HIGH", "CRITICAL"})
        self.assertTrue(any("higher ground" in action.lower() for action in decision["actions"]))

    def test_decision_policy_override_from_env_path(self):
        policy_payload = {
            "version": "test",
            "default": {
                "urgency": "LOW",
                "condition": "Default Test Condition",
                "actions": ["Observe"]
            },
            "disaster_actions": {
                "default": ["Evacuate safely"]
            },
            "rules": [
                {
                    "id": "custom_phrase_rule",
                    "any_phrases": ["mystic marker"],
                    "urgency": "HIGH",
                    "condition": "Custom Triggered Condition",
                    "actions": ["Trigger custom protocol"],
                    "reason": "custom policy matched"
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            policy_file = Path(temp_dir) / "decision_policy.json"
            policy_file.write_text(json.dumps(policy_payload), encoding="utf-8")

            previous = os.environ.get("DECISION_POLICY_PATH")
            os.environ["DECISION_POLICY_PATH"] = str(policy_file)
            invalidate_decision_policy_cache()

            try:
                parsed = {
                    "symptoms": ["patient has mystic marker observed"],
                    "history": [],
                    "disaster": "",
                    "domain": "medical",
                    "raw_query": "mystic marker",
                }
                decision = decide_next_actions(parsed, "general", [])
                self.assertEqual(decision["condition"], "Custom Triggered Condition")
                self.assertEqual(decision["urgency"], "HIGH")
                self.assertTrue(any("custom protocol" in action.lower() for action in decision["actions"]))
            finally:
                if previous is None:
                    os.environ.pop("DECISION_POLICY_PATH", None)
                else:
                    os.environ["DECISION_POLICY_PATH"] = previous
                invalidate_decision_policy_cache()


if __name__ == "__main__":
    unittest.main()
