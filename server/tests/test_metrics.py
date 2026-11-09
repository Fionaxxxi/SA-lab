"""S2 指标脚本自测（彭雯青）。

不依赖真实录音：用构造记录验证 CER、分位数、完成率与覆盖率口径，
确保 S2 拿到真数据时脚本本身不会算错。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "experiments" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_metrics as cm  # noqa: E402


class TestTextNormalization(unittest.TestCase):
    def test_strips_punctuation_and_space(self):
        self.assertEqual(cm.normalize_text("今天，天气 很好。"), "今天天气很好")

    def test_lowercases_english(self):
        self.assertEqual(cm.normalize_text("Hello, World!"), "helloworld")


class TestCer(unittest.TestCase):
    def test_identical_is_zero(self):
        result = cm.char_error_rate("今天天气很好。", "今天天气很好")
        self.assertEqual(result["cer"], 0.0)
        self.assertEqual(result["edit_distance"], 0)

    def test_one_char_substitution(self):
        result = cm.char_error_rate("今天天气很好", "今天天气很号")
        self.assertEqual(result["edit_distance"], 1)
        self.assertEqual(result["ref_chars"], 6)
        self.assertAlmostEqual(result["cer"], 1 / 6, places=6)

    def test_empty_reference_rejected(self):
        with self.assertRaises(ValueError):
            cm.char_error_rate("，。！", "任意")


class TestPercentile(unittest.TestCase):
    def test_linear_interpolation(self):
        values = [10.0, 20.0, 30.0, 40.0]
        self.assertAlmostEqual(cm.percentile(values, 50), 25.0, places=6)
        self.assertAlmostEqual(cm.percentile(values, 90), 37.0, places=6)

    def test_single_value(self):
        self.assertEqual(cm.percentile([5.0], 90), 5.0)

    def test_empty_returns_none(self):
        self.assertIsNone(cm.percentile([], 90))


class TestSummarize(unittest.TestCase):
    def test_completion_excludes_cancelled_from_timing_only(self):
        records = [
            {
                "case_id": "r1",
                "success": True,
                "end_to_end_ms": 3000,
                "audio_ms": 15000,
                "ref": "今天天气很好",
                "hyp": "今天天气很好",
                "keypoints": {"k1": True, "k2": False},
            },
            {
                "case_id": "r2",
                "success": True,
                "end_to_end_ms": 4000,
                "audio_ms": 15000,
                "ref": "今天天气很好",
                "hyp": "今天天气很号",
                "keypoints": {"k1": True, "k2": True},
            },
            {"case_id": "r3", "success": False},
            {"case_id": "r4", "success": False, "cancelled": True},
        ]
        summary = cm.summarize(records)

        self.assertEqual(summary["n_valid"], 3)
        self.assertEqual(summary["n_success"], 2)
        self.assertEqual(summary["n_cancelled"], 1)
        self.assertAlmostEqual(summary["completion_rate"], 2 / 3, places=6)
        self.assertAlmostEqual(summary["completion_rate_including_cancelled"], 2 / 4, places=6)
        self.assertEqual(summary["end_to_end_ms"]["p50"], 3500.0)
        self.assertEqual(summary["end_to_end_ms"]["p90"], 3900.0)
        # r1=0.2, r2=4000/15000=0.2667，两条样本线性插值 P50≈0.2333（summarize 保留 4 位）
        self.assertEqual(summary["rtf"]["p50"], 0.2333)
        self.assertEqual(summary["keypoint_coverage"]["covered"], 3)
        self.assertEqual(summary["keypoint_coverage"]["total"], 4)
        self.assertEqual(summary["keypoint_coverage"]["rate"], 0.75)
        self.assertAlmostEqual(summary["cer"]["mean"], (0 + 1 / 6) / 2, places=5)


if __name__ == "__main__":
    unittest.main()
