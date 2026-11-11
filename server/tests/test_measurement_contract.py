"""Independent fixture check for the published accounting rules."""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

CONFIGS = Path(__file__).resolve().parents[2] / "experiments" / "configs"


def read(name):
    return json.loads((CONFIGS / name).read_text("utf-8"))


class MeasurementContractTests(unittest.TestCase):
    def test_run_configuration_and_accounting_fixture(self):
        validator = Draft202012Validator(read("run-config.schema.json"))
        for config in read("ljx-fixture-runs.json"):
            validator.validate(config)
        rows = [json.loads(line) for line in
                (CONFIGS / "ljx-accounting-fixture.jsonl").read_text("utf-8").splitlines()]
        expected = read("ljx-accounting-expected.json")
        terminal = {}
        visible = {}
        for row in rows:
            self.assertEqual(row["run_id"], expected["run_id"])
            key = tuple(row[field] for field in ("run_id", "device_id", "task_id"))
            if row["event"] == "TASK_TERMINAL":
                self.assertEqual(terminal.setdefault(key, row), row)
            elif row["event"] == "FEEDBACK_VISIBLE":
                self.assertEqual(visible.setdefault(key, row), row)
        valid = {key for key, row in terminal.items() if row["effective_input"]}
        success = {key for key in valid if terminal[key]["status"] == "SUCCEEDED"}
        latency = sorted(visible[key]["elapsed_ms"] for key in success)
        self.assertEqual(len(valid), expected["effective_tasks"])
        self.assertEqual(len(success), expected["successful_tasks"])
        self.assertEqual(len(success) / len(valid), expected["completion_rate"])
        self.assertEqual(len(latency), expected["feedback_latency_sample_count"])
        low, high = latency
        for percentile in (50, 90, 99):
            self.assertAlmostEqual(low + (high - low) * percentile / 100, expected[f"p{percentile}_ms"])
