"""Record a text-only review of the 15 user-attested calibration scripts."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
draft_path = ROOT / "manifest.annotation-draft.json"
proposal_path = ROOT / "manifest.ai-coverage-proposal.json"
draft = json.loads(draft_path.read_text(encoding="utf-8"))
proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
if any(record.get("annotator") or record.get("reviewer") for record in draft[:15]):
    raise SystemExit("Refusing to overwrite records with human annotation or review.")

# Script-only judgments where the original design intent is too broad.
overrides = {
    ("S05", "k1"): (False, "仅说调查骗局，未明确调查居民需求；完整要点不成立。"),
    ("S08", "k2"): (False, "志愿者挨家联系老人，但未说明联合网格员，也未明确高温提醒。"),
    ("S10", "k2"): (False, "只请网格员上门，未明确联系老人或作高温提醒。"),
    ("S13", "k4"): (False, "查看错投记录并调整，但未向居民反馈改进效果。"),
}

negative_reasons = {
    "S02": {"k4": "没有活动后的反馈与回访。"},
    "S03": {"k2": "仅提个人提醒，未联合社区分人群组织案例宣传。"},
    "S04": {k: "回答离题，没有该要点的行动。" for k in ("k1", "k2", "k3", "k4")},
    "S05": {"k3": "明确否定验证码与转账提醒。", "k4": "明确否定反馈和回访。"},
    "S07": {"k3": "没有饮水、避暑或就医协助。"},
    "S08": {"k1": "没有排查独居老人及高风险住户。"},
    "S09": {k: "回答自己的避暑安排，没有社区老人关怀行动。" for k in ("k1", "k2", "k3", "k4")},
    "S10": {"k3": "明确否定避暑与就医帮助。", "k4": "明确否定后续回访。"},
    "S12": {"k3": "没有优化桶点或清运安排。"},
    "S13": {"k2": "没有分类讲解或现场示范。"},
    "S14": {k: "回答社区绿化与休憩设施，没有垃圾分类行动。" for k in ("k1", "k2", "k3", "k4")},
    "S15": {"k3": "明确否定调整桶点和清运。", "k4": "明确否定记录错误，且没有反馈效果。"},
}

for record, proposed in zip(draft[:15], proposal[:15]):
    assert record["sample_id"] == proposed["sample_id"]
    sid = record["sample_id"]
    assert record["reference_text"] == proposed["reference_text"]
    for point, suggestion in zip(record["keypoints"], proposed["keypoints"]):
        kid = point["keypoint_id"]
        covered, reason = overrides.get((sid, kid), (suggestion["expected_covered"], ""))
        quote = suggestion.get("proposed_evidence_quote", "") if covered else ""
        if covered:
            assert quote and quote in record["reference_text"], (sid, kid, quote)
            reason = "引文直接支持该要点；按引导稿原文判定。"
        else:
            reason = reason or negative_reasons[sid][kid]
        point["expected_covered"] = covered
        point["script_evidence_quote"] = quote
        point["script_review_reason"] = reason
    record["coverage_review_provenance"] = "AI_TEXT_REVIEW_OF_USER_ATTESTED_SCRIPT_NOT_AUDIO_OR_SECOND_HUMAN_REVIEW_2026-11-13"

draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Reviewed 15 calibration scripts and 60 keypoints; formal reviewer and consent fields remain blank.")
