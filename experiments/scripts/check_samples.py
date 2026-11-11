"""Validate real sample manifests and topic-disjoint splits."""
import argparse
import hashlib
import json
import wave
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("manifest", type=Path)
args = parser.parse_args()
samples = json.loads(args.manifest.read_text("utf-8"))
if len(samples) < 30:
    raise ValueError("At least 30 real labeled recordings required")
topics, ids = {}, set()
splits = set()
for sample in samples:
    if sample["sample_id"] in ids:
        raise ValueError("Duplicate sample id")
    ids.add(sample["sample_id"])
    split = sample["split"]
    splits.add(split)
    if split not in ("calibration", "evaluation"):
        raise ValueError("Unknown split")
    if topics.setdefault(sample["topic_id"], split) != split:
        raise ValueError("Same topic occurs in both splits")
    if not all(sample.get(key) for key in ("reference_text", "annotator", "reviewer", "consent")):
        raise ValueError("Missing human annotation/review/consent")
    if sample["consent"] is not True or type(sample.get("effective_input")) is not bool:
        raise ValueError("Consent must be true and effective_input must be a boolean")
    if sample["annotator"].strip() == sample["reviewer"].strip():
        raise ValueError("A different human reviewer is required")
    if not sample["reference_text"].strip() or not sample.get("keypoints"):
        raise ValueError("Missing reference text or keypoints")
    if any(type(point.get("expected_covered")) is not bool or not point.get("text", "").strip()
           for point in sample["keypoints"]):
        raise ValueError("Every keypoint needs reviewed coverage and text")
    path = (args.manifest.parent / sample["wav_path"]).resolve()
    if not path.is_relative_to(args.manifest.parent.resolve()):
        raise ValueError("Audio must stay within the sample directory")
    if hashlib.sha256(path.read_bytes()).hexdigest() != sample["sha256"]:
        raise ValueError("Audio hash mismatch")
    with wave.open(str(path), "rb") as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Unsupported WAV")
        if not 0 < audio.getnframes() <= 960000:
            raise ValueError("Invalid duration")
if splits != {"calibration", "evaluation"}:
    raise ValueError("Both calibration and evaluation splits are required")
print(f"Validated {len(samples)} recordings in {len(topics)} topic groups")
