"""复现比对逻辑的自测。

被测对象是 experiments/scripts/s0_repro_check.py：它决定"两次运行是否一致"，
如果它自己有假阳性/假阴性，9/9 一致的结论就不可信。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "experiments" / "scripts"))

import s0_repro_check as repro  # noqa: E402


class TestStripVolatile(unittest.TestCase):
    def test_removes_generated_at_and_elapsed(self):
        payload = {"generated_at": "2026-11-09T00:00:00", "elapsed_ms": 123, "cases": [1]}
        self.assertEqual(repro.strip_volatile(payload), {"cases": [1]})

    def test_keeps_other_keys(self):
        payload = {"schema_version": "v1", "generated_at": "x"}
        self.assertEqual(repro.strip_volatile(payload), {"schema_version": "v1"})


class TestDiffPaths(unittest.TestCase):
    def test_identical_returns_empty(self):
        self.assertEqual(
            repro.diff_paths({"a": 1, "b": [1, 2]}, {"a": 1, "b": [1, 2]}),
            [],
        )

    def test_value_changed(self):
        diffs = repro.diff_paths({"a": 1}, {"a": 2})
        self.assertEqual(len(diffs), 1)
        self.assertIn("a", diffs[0])

    def test_nested_list_value_changed(self):
        diffs = repro.diff_paths({"v": [1, 2]}, {"v": [1, 3]})
        self.assertTrue(any("v[1]" in item for item in diffs))

    def test_list_length_differs(self):
        diffs = repro.diff_paths({"v": [1, 2]}, {"v": [1]})
        self.assertTrue(any("length" in item for item in diffs))

    def test_missing_key(self):
        diffs = repro.diff_paths({"a": 1}, {"b": 1})
        self.assertTrue(
            any("only in earlier" in item or "only in later" in item for item in diffs)
        )

    def test_type_mismatch(self):
        diffs = repro.diff_paths({"a": 1}, {"a": "1"})
        self.assertTrue(any("type" in item for item in diffs))


class TestCaseIndex(unittest.TestCase):
    def test_index_by_case_id(self):
        payload = {"cases": [{"case_id": "A", "x": 1}, {"case_id": "B"}, {"no_id": 1}]}
        index = repro.case_index(payload)
        self.assertEqual(set(index), {"A", "B"})
        self.assertEqual(index["A"]["x"], 1)

    def test_cases_not_list(self):
        self.assertEqual(repro.case_index({"cases": "x"}), {})


if __name__ == "__main__":
    unittest.main()
