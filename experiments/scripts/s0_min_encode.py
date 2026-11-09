#!/usr/bin/env python
"""S0-P3 最小编码调用：固定文本 -> token / 向量 / 余弦 / 匹配。

用法：
  python experiments/scripts/s0_min_encode.py --out <json>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules.errors import ModuleError  # noqa: E402
from server.modules.match import match  # noqa: E402
from server.modules.semantic import SemanticEncoder, split_sentences  # noqa: E402

DEFAULT_TEXTS = [
    "面对群众诉求，我会先耐心倾听并记录关键信息。",
    "然后按职责范围分类处理，能当场解决的立即解决。",
    "需要协调的事项会说明办理时限，并及时反馈进展。",
]
DEFAULT_KEYPOINTS = [
    {"keypoint_id": "k1", "text": "耐心倾听并记录群众诉求"},
    {"keypoint_id": "k2", "text": "按职责分类处理，当场解决"},
    {"keypoint_id": "k3", "text": "说明办理时限并及时反馈"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_path = Path(args.out).resolve()

    started = time.perf_counter()
    result: dict = {}
    error = None
    try:
        encoder = SemanticEncoder()
        tokens = [encoder.inspect(text) for text in DEFAULT_TEXTS]
        vectors = encoder.encode(DEFAULT_TEXTS)
        norms = np.linalg.norm(vectors, axis=1)
        cos_01 = float(np.dot(vectors[0], vectors[1]))
        transcript = {
            "full_text": "\n".join(DEFAULT_TEXTS),
            "segments": [
                {
                    "segment_id": "seg-1",
                    "start_sample": 0,
                    "end_sample": 0,
                    "text": "".join(DEFAULT_TEXTS),
                }
            ],
        }
        embeddings = encoder.encode_transcript(transcript, DEFAULT_KEYPOINTS)
        matches_05 = match(embeddings["embeddings"], threshold=0.5)
        matches_08 = match(embeddings["embeddings"], threshold=0.8)

        result = {
            "case": "S0-P3",
            "texts": DEFAULT_TEXTS,
            "sentences": split_sentences("".join(DEFAULT_TEXTS)),
            "token_check": tokens,
            "vector_dimension": int(vectors.shape[1]),
            "vector_count": int(vectors.shape[0]),
            "vector_norms": [round(float(value), 8) for value in norms],
            "cos_text0_text1": round(cos_01, 8),
            "vector_head": [round(float(value), 8) for value in vectors[0][:8]],
            "embeddings": embeddings["embeddings"],
            "matches_threshold_0_5": matches_05,
            "matches_threshold_0_8": matches_08,
        }
    except ModuleError as exc:
        error = exc.to_dict()

    elapsed_ms = (time.perf_counter() - started) * 1000
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_ms": round(elapsed_ms, 1),
        "error": error,
        **result,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": error is None, "out": str(out_path), "elapsed_ms": round(elapsed_ms, 1)}, ensure_ascii=False))
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
