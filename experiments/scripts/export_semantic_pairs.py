"""Export calibration-only semantic pairs without treating draft labels as formal gold."""

import argparse
import hashlib
import json
from pathlib import Path


def export_pairs(manifest_path, output_path, asr_dir=None):
    manifest_path, output_path = Path(manifest_path), Path(output_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = []
    for sample in manifest:
        if sample["split"] != "calibration":
            continue
        sample_id = sample["sample_id"]
        if not sample.get("coverage_review_provenance", "").startswith("AI_TEXT_REVIEW_"):
            raise ValueError(f"{sample_id}: expected a recorded text-review provenance")
        if any(type(point.get("expected_covered")) is not bool for point in sample["keypoints"]):
            raise ValueError(f"{sample_id}: missing coverage labels")
        premise = sample["reference_text"]
        if asr_dir:
            observed = json.loads((Path(asr_dir) / f"{sample_id}.json").read_text(encoding="utf-8"))
            if observed["audio_sha256"] != sample["sha256"]:
                raise ValueError(f"{sample_id}: ASR and audio hash differ")
            premise = observed["transcript"]["full_text"]
        for point in sample["keypoints"]:
            records.append({
                "sample_id": sample_id,
                "topic_id": sample["topic_id"],
                "keypoint_id": point["keypoint_id"],
                "premise": premise,
                "hypothesis": point["text"],
                "covered": point["expected_covered"],
                "script_evidence_quote": point.get("script_evidence_quote", ""),
                "script_review_reason": point.get("script_review_reason", ""),
                "audio_sha256": sample["sha256"],
                "reference_sha256": hashlib.sha256(sample["reference_text"].encode("utf-8")).hexdigest(),
            })
    if len(records) != 60 or len({row["sample_id"] for row in records}) != 15:
        raise ValueError("Expected exactly 60 calibration pairs across 15 recordings")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "status": "WEAK_AI_TEXT_LABELS_NOT_HUMAN_AUDIO_GOLD",
        "split": "calibration_only",
        "premise_source": "ASR" if asr_dir else "USER_ATTESTED_REFERENCE_SCRIPT",
        "records": records,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(records)} calibration pairs to {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="experiments/samples/manifest.annotation-draft.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--asr-dir")
    args = parser.parse_args()
    export_pairs(args.manifest, args.output, args.asr_dir)


if __name__ == "__main__":
    main()
