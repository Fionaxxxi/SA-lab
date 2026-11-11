import base64
import io
import unittest
import wave
from server.modules.match import Matcher
from experiments.scripts.compute_metrics import aggregate, percentile, edits, normalize
from server.gateway.protocol import ProtocolError


class RealContracts(unittest.TestCase):
    def test_match_tie_threshold_and_invalid_vector(self):
        model = {"dimension": 2, "answer_sentences": [
            {"sentence_id": "s1", "text": "先调查需求", "vector": [1, 0]},
            {"sentence_id": "s2", "text": "调查需求", "vector": [1, 0]}],
            "keypoints": [{"keypoint_id": "k1", "vector": [1, 0]}]}
        result = Matcher(2, 0.8)({"embeddings": model})["matches"][0]
        self.assertEqual(result["evidence_sentence_id"], "s1")
        self.assertTrue(result["covered"])
        model["keypoints"][0]["vector"] = [0, 0]
        with self.assertRaises(ProtocolError):
            Matcher(2, 0.8)({"embeddings": model})

    def test_quality_and_accounting(self):
        self.assertEqual(edits(normalize("调查，需求"), "调查居民需求"), 2)
        self.assertEqual(percentile([1800, 2400], .9), 2340)
        base = {"run_id": "r", "device_id": "d", "mode": "LOCAL", "input_source": "IMPORT",
                "effective_input": True, "elapsed_ms": 100, "audio_samples": 160000}
        success = base | {"task_id": "a", "event": "TASK_TERMINAL", "status": "SUCCEEDED"}
        rows = [success, success, base | {"task_id": "a", "event": "FEEDBACK_VISIBLE", "status": "OK"},
                base | {"task_id": "b", "event": "TASK_TERMINAL", "status": "CANCELLED"}]
        result = aggregate(rows)[0]
        self.assertEqual(result["effective_tasks"], 2)
        self.assertEqual(result["completion_rate"], .5)
        self.assertEqual(result["latency_n"], 1)
