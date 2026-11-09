"""彭雯青模块自测（M2 校验、M3 编码、M4 匹配）。

归属说明：本文件由彭雯青编写用于 S0/S1 自测；server/tests 目录的最终
组织由林俊希确认，合入时可按需改名或拆分。
"""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules.asr import transcribe_segments  # noqa: E402
from server.modules.errors import InvalidPayload, ModelUnavailable, NoSpeech  # noqa: E402
from server.modules.match import match  # noqa: E402
from server.modules.semantic import SemanticEncoder, split_sentences  # noqa: E402

# S0 实测锁定的 token 序列（“面对群众诉求，我会先耐心倾听并记录关键信息。”）
TOKEN_IDS_S0 = [
    0, 6, 26811, 42444, 78119, 8681, 4, 89809, 2996, 117388, 107283,
    10456, 2672, 42750, 42037, 5412, 30, 2,
]


class TestSentenceSplit(unittest.TestCase):
    def test_split_by_sentence_punctuation(self):
        text = "第一句。第二句！第三句？"
        self.assertEqual(split_sentences(text), ["第一句。", "第二句！", "第三句？"])

    def test_commas_do_not_split(self):
        text = "先听，再记，最后处理。"
        self.assertEqual(split_sentences(text), ["先听，再记，最后处理。"])

    def test_no_punctuation_keeps_whole_text(self):
        text = "考生 开始 作答 面对 群众 诉求"
        self.assertEqual(split_sentences(text), [text])


class TestAsrValidation(unittest.TestCase):
    def test_odd_pcm_length(self):
        with self.assertRaises(InvalidPayload):
            transcribe_segments(
                [
                    {
                        "segment_id": "s1",
                        "start_sample": 0,
                        "end_sample": 1,
                        "pcm_b64": base64.b64encode(b"\x00\x00\x00").decode(),
                    }
                ]
            )

    def test_bad_base64(self):
        with self.assertRaises(InvalidPayload):
            transcribe_segments(
                [
                    {
                        "segment_id": "s1",
                        "start_sample": 0,
                        "end_sample": 10,
                        "pcm_b64": "!!!not-base64!!!",
                    }
                ]
            )

    def test_length_mismatch(self):
        pcm = b"\x00\x00" * 50  # 100 字节，区间 0..60 需要 120 字节
        with self.assertRaises(InvalidPayload):
            transcribe_segments(
                [
                    {
                        "segment_id": "s1",
                        "start_sample": 0,
                        "end_sample": 60,
                        "pcm_b64": base64.b64encode(pcm).decode(),
                    }
                ]
            )

    def test_empty_segments_is_no_speech(self):
        with self.assertRaises(NoSpeech):
            transcribe_segments([])

    def test_duplicate_segment_id(self):
        item = {
            "segment_id": "s1",
            "start_sample": 0,
            "end_sample": 1,
            "pcm_b64": base64.b64encode(b"\x00\x00").decode(),
        }
        with self.assertRaises(InvalidPayload):
            transcribe_segments([item, dict(item)])

    def test_missing_model(self):
        pcm = b"\x00\x00" * 16000
        with self.assertRaises(ModelUnavailable):
            transcribe_segments(
                [
                    {
                        "segment_id": "s1",
                        "start_sample": 0,
                        "end_sample": 16000,
                        "pcm_b64": base64.b64encode(pcm).decode(),
                    }
                ],
                model_dir=str(PROJECT_ROOT / "models" / "weights" / "no-such-model"),
            )


class TestSemanticEncoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoder = SemanticEncoder()

    def test_token_ids_locked(self):
        ids = self.encoder.token_ids("面对群众诉求，我会先耐心倾听并记录关键信息。")
        self.assertEqual(ids, TOKEN_IDS_S0)

    def test_encode_shape_and_norm(self):
        vectors = self.encoder.encode(["第一句。", "第二句。"])
        self.assertEqual(vectors.shape, (2, 384))
        norms = np.linalg.norm(vectors, axis=1)
        self.assertTrue(np.allclose(norms, 1.0, atol=1e-5))

    def test_empty_text_rejected(self):
        with self.assertRaises(InvalidPayload):
            self.encoder.encode([""])

    def test_encode_transcript_ids_stable(self):
        transcript = {
            "full_text": "第一句。第二句。",
            "segments": [{"segment_id": "s1", "start_sample": 0, "end_sample": 10, "text": "第一句。第二句。"}],
        }
        result = self.encoder.encode_transcript(
            transcript, [{"keypoint_id": "k1", "text": "第一句"}]
        )["embeddings"]
        self.assertEqual(result["dimension"], 384)
        self.assertEqual(len(result["answer_sentences"]), 2)
        self.assertEqual([item["sentence_id"] for item in result["answer_sentences"]], ["s1", "s2"])
        self.assertEqual([item["keypoint_id"] for item in result["keypoints"]], ["k1"])


def _embeddings(vectors: list[list[float]]) -> dict:
    dimension = len(vectors[0])
    return {
        "dimension": dimension,
        "answer_sentences": [
            {"sentence_id": f"s{index + 1}", "text": f"句{index + 1}", "vector": vector}
            for index, vector in enumerate(vectors)
        ],
        "keypoints": [{"keypoint_id": "k1", "vector": [1.0] + [0.0] * (dimension - 1)}],
    }


class TestMatch(unittest.TestCase):
    def test_tie_takes_earliest_sentence(self):
        result = match(_embeddings([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]), threshold=0.5)
        item = result["matches"][0]
        self.assertEqual(item["evidence_sentence_id"], "s1")
        self.assertAlmostEqual(item["score"], 1.0, places=6)
        self.assertTrue(item["covered"])

    def test_threshold_controls_covered(self):
        result = match(_embeddings([[0.0, 1.0, 0.0, 0.0]]), threshold=0.5)
        item = result["matches"][0]
        self.assertAlmostEqual(item["score"], 0.0, places=6)
        self.assertFalse(item["covered"])

    def test_zero_vector_rejected(self):
        with self.assertRaises(InvalidPayload):
            match(_embeddings([[0.0, 0.0, 0.0, 0.0]]))

    def test_dimension_mismatch(self):
        payload = _embeddings([[1.0, 0.0, 0.0, 0.0]])
        payload["dimension"] = 8
        with self.assertRaises(InvalidPayload):
            match(payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
