import unittest

from server.modules.match import Matcher
from server.modules.semantic import answer_clauses


class ClauseMatchingTests(unittest.TestCase):
    def test_unpunctuated_answer_splits_before_negative_turn(self):
        text = "先调查骗局再和社区办案例宣传不过我不打算提醒居民保护验证码也不准备讲转账核实"
        self.assertEqual(answer_clauses(text), [
            "先调查骗局", "再和社区办案例宣传", "不过我不打算提醒居民保护验证码",
            "也不准备讲转账核实",
        ])

    def test_windows_keep_negative_clause_intact(self):
        positive = "先调查居民遇到的各种诈骗情况并联合社区工作人员讲解真实的案例"
        negative = "不过我不打算提醒居民保护验证码也不准备讲转账核实的具体办法"
        passages = answer_clauses(positive + negative)
        self.assertGreater(len(passages), 2)
        self.assertIn(negative[:negative.index("也不准备")], passages)
        self.assertFalse(any("不打算" not in passage and "保护验证码" in passage for passage in passages))

    def test_negated_action_cannot_supply_covered_evidence(self):
        payload = {"embeddings": {"dimension": 2,
            "answer_sentences": [
                {"sentence_id": "s1", "text": "我不打算提醒居民保护验证码", "vector": [1.0, 0.0]},
                {"sentence_id": "s2", "text": "先了解居民情况", "vector": [0.0, 1.0]},
            ],
            "keypoints": [{"keypoint_id": "k1", "vector": [1.0, 0.0]}]}}
        actual = Matcher(2, 0.54)(payload)["matches"][0]
        self.assertFalse(actual["covered"])

    def test_protective_warning_is_not_rejected(self):
        payload = {"embeddings": {"dimension": 2,
            "answer_sentences": [{"sentence_id": "s1", "text": "提醒大家不要泄露验证码", "vector": [1.0, 0.0]}],
            "keypoints": [{"keypoint_id": "k1", "vector": [1.0, 0.0]}]}}
        actual = Matcher(2, 0.54)(payload)["matches"][0]
        self.assertTrue(actual["covered"])
        payload["embeddings"]["answer_sentences"][0]["text"] = "提醒大家不会泄露验证码"
        self.assertTrue(Matcher(2, 0.54)(payload)["matches"][0]["covered"])


if __name__ == "__main__":
    unittest.main()
