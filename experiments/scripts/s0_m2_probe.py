#!/usr/bin/env python
"""M2 补充探针：纯解码 RTF + 词级时间戳停顿切句效果。

做两件 S0 阶段没做的事：
1) 把“模型加载”与“解码”拆开，算纯解码 RTF（判断手机端能否实时跟上）；
2) 用 Vosk 词级时间戳按停顿切句，对比“按标点切”只有 1 句的问题。

输出：experiments/results/s0_m2_probe.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import statistics
import sys
import time
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules.asr import load_model, transcribe_pcm, transcribe_segments  # noqa: E402
from server.modules.match import match  # noqa: E402
from server.modules.semantic import SemanticEncoder  # noqa: E402

KEYPOINTS = [
    {"keypoint_id": "k1", "text": "耐心倾听并记录群众诉求"},
    {"keypoint_id": "k2", "text": "按职责分类处理，当场解决"},
    {"keypoint_id": "k3", "text": "说明办理时限并及时反馈"},
]


def read_wav(path: Path) -> tuple[bytes, dict]:
    raw = path.read_bytes()
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.getnframes()
        pcm = handle.readframes(frames)
    if (channels, width, rate) != (1, 2, 16000):
        raise ValueError(f"{path.name} 参数不符：{channels}/{width}/{rate}")
    meta = {
        "file": path.name,
        "sample_rate_hz": rate,
        "sample_count": len(pcm) // 2,
        "duration_sec": round(len(pcm) / 2 / rate, 3),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
    }
    return pcm, meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wav",
        default=str(PROJECT_ROOT / "experiments" / "samples" / "local" / "s0_case_a.wav"),
    )
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "experiments" / "results" / "s0_m2_probe.json"),
    )
    args = parser.parse_args()

    wav_path = Path(args.wav).resolve()
    pcm, meta = read_wav(wav_path)

    load_started = time.perf_counter()
    model = load_model()
    model_load_ms = (time.perf_counter() - load_started) * 1000

    segment = {
        "segment_id": "seg-a",
        "start_sample": 0,
        "end_sample": meta["sample_count"],
        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
    }

    decode_runs_ms: list[float] = []

    started = time.perf_counter()
    transcript = transcribe_segments([segment], include_words=True)["transcript"]
    decode_runs_ms.append((time.perf_counter() - started) * 1000)

    for _ in range(2):
        started = time.perf_counter()
        transcribe_pcm(pcm)
        decode_runs_ms.append((time.perf_counter() - started) * 1000)

    decode_median_ms = statistics.median(decode_runs_ms)
    rtf = round((decode_median_ms / 1000) / meta["duration_sec"], 4)

    words = transcript["segments"][0].get("words", [])
    gaps_ms = [
        (words[index + 1]["start_sample"] - words[index]["end_sample"]) / 16
        for index in range(len(words) - 1)
    ]

    encoder = SemanticEncoder()
    punct = encoder.encode_transcript(transcript, KEYPOINTS, with_timing=True)["embeddings"]
    pause = encoder.encode_transcript(
        transcript, KEYPOINTS, use_word_pauses=True, pause_ms=350, with_timing=True
    )["embeddings"]

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "audio": meta,
        "model_load_ms": round(model_load_ms, 1),
        "decode_runs_ms": [round(value, 1) for value in decode_runs_ms],
        "decode_median_ms": round(decode_median_ms, 1),
        "rtf_pure_decode": rtf,
        "rtf_note": "RTF = 纯解码耗时 / 音频时长；不含模型加载",
        "word_count": len(words),
        "gap_ms": {
            "max": round(max(gaps_ms), 1) if gaps_ms else None,
            "median": round(statistics.median(gaps_ms), 1) if gaps_ms else None,
            "ge_350ms": sum(1 for gap in gaps_ms if gap >= 350),
        },
        "split_by_punctuation": {
            "count": len(punct["answer_sentences"]),
            "sentences": punct["answer_sentences"],
        },
        "split_by_pause_350ms": {
            "count": len(pause["answer_sentences"]),
            "sentences": pause["answer_sentences"],
        },
        "matches_by_pause": {
            "0.5": match(pause, threshold=0.5),
            "0.8": match(pause, threshold=0.8),
        },
        "elapsed_ms": round((time.perf_counter() - load_started) * 1000, 1),
    }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "out": str(out_path),
                "rtf_pure_decode": rtf,
                "words": len(words),
                "sentences_punct": len(punct["answer_sentences"]),
                "sentences_pause": len(pause["answer_sentences"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
