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
for sample in samples:
    if sample["sample_id"] in ids:
        raise ValueError("Duplicate sample id")
    ids.add(sample["sample_id"])
    split = sample["split"]
    if split not in ("calibration", "evaluation"):
        raise ValueError("Unknown split")
    if topics.setdefault(sample["topic_id"], split) != split:
        raise ValueError("Same topic occurs in both splits")
    if not all(sample.get(key) for key in ("reference_text", "annotator", "reviewer", "consent")):
        raise ValueError("Missing human annotation/review/consent")
    path = args.manifest.parent / sample["wav_path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != sample["sha256"]:
        raise ValueError("Audio hash mismatch")
    with wave.open(str(path), "rb") as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError("Unsupported WAV")
        if not 0 < audio.getnframes() <= 960000:
            raise ValueError("Invalid duration")
print(f"Validated {len(samples)} recordings in {len(topics)} topic groups")
