#!/usr/bin/env python
"""S0-P6 异常样例：逐项断言模块错误码。

用法：
  python experiments/scripts/s0_negative.py --out <json>
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules.asr import transcribe_pcm, transcribe_segments  # noqa: E402
from server.modules.errors import ModuleError  # noqa: E402
from server.modules.match import match  # noqa: E402
from server.modules.semantic import SemanticEncoder  # noqa: E402

SILENCE_PCM = b"\x00\x00" * 16000  # 1 秒静音


def run_case(case_id: str, expected_code: str, func) -> dict:
    try:
        func()
        actual = "NO_ERROR"
        passed = False
    except ModuleError as exc:
        actual = exc.code
        passed = actual == expected_code
    except Exception as exc:  # 非契约异常也算失败
        actual = f"UNEXPECTED:{type(exc).__name__}"
        passed = False
    return {"case_id": case_id, "expected": expected_code, "actual": actual, "passed": passed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_path = Path(args.out).resolve()

    started = time.perf_counter()
    cases = [
        run_case("N1-odd-pcm", "INVALID_PAYLOAD", lambda: transcribe_pcm(b"\x00\x00\x00")),
        run_case("N2-empty-segments", "NO_SPEECH", lambda: transcribe_segments([])),
        run_case(
            "N3-bad-base64",
            "INVALID_PAYLOAD",
            lambda: transcribe_segments(
                [
                    {
                        "segment_id": "s1",
                        "start_sample": 0,
                        "end_sample": 10,
                        "pcm_b64": "!!!not-base64!!!",
                    }
                ]
            ),
        ),
        run_case(
            "N4-length-mismatch",
            "INVALID_PAYLOAD",
            lambda: transcribe_segments(
                [
                    {
                        "segment_id": "s1",
                        "start_sample": 0,
                        "end_sample": 60,
                        "pcm_b64": base64.b64encode(SILENCE_PCM[:100]).decode("ascii"),
                    }
                ]
            ),
        ),
        run_case(
            "N5-model-missing",
            "MODEL_UNAVAILABLE",
            lambda: transcribe_segments(
                [
                    {
                        "segment_id": "s1",
                        "start_sample": 0,
                        "end_sample": 16000,
                        "pcm_b64": base64.b64encode(SILENCE_PCM).decode("ascii"),
                    }
                ],
                model_dir=str(PROJECT_ROOT / "models" / "weights" / "no-such-model"),
            ),
        ),
    ]

    encoder = SemanticEncoder()
    cases.append(
        run_case(
            "N6-empty-text",
            "INVALID_PAYLOAD",
            lambda: encoder.encode([""]),
        )
    )
    cases.append(
        run_case(
            "N7-zero-vector",
            "INVALID_PAYLOAD",
            lambda: match(
                {
                    "dimension": encoder.dimension,
                    "answer_sentences": [
                        {"sentence_id": "s1", "text": "x", "vector": [0.0] * encoder.dimension}
                    ],
                    "keypoints": [{"keypoint_id": "k1", "vector": [1.0] + [0.0] * (encoder.dimension - 1)}],
                }
            ),
        )
    )

    payload = {
        "case_set": "S0-P6",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "total": len(cases),
        "passed": sum(1 for item in cases if item["passed"]),
        "cases": cases,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "total": payload["total"], "out": str(out_path)}, ensure_ascii=False))
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
