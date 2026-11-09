#!/usr/bin/env python
"""生成 S0 金样例（contracts/examples/golden-s0.json）。

两条基线：
1) 真实链路基线：两段固定 WAV → M2 转写 → M3/M4（Vosk 输出无标点，整段为一句）；
2) 可控文本基线：三句带标点文本 → M3 切句 → M4，用于锁定句子级匹配行为。

用法：
  python experiments/scripts/make_golden_s0.py \
      --wav-a experiments/samples/local/s0_case_a.wav \
      --wav-b experiments/samples/local/s0_case_b.wav \
      --out contracts/examples/golden-s0.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules import config  # noqa: E402
from server.modules.asr import transcribe_segments  # noqa: E402
from server.modules.match import match  # noqa: E402
from server.modules.semantic import SemanticEncoder, split_sentences  # noqa: E402

KEYPOINTS = [
    {"keypoint_id": "k1", "text": "耐心倾听并记录群众诉求"},
    {"keypoint_id": "k2", "text": "按职责分类处理，当场解决"},
    {"keypoint_id": "k3", "text": "说明办理时限并及时反馈"},
]

TOKEN_PROBES = [
    "面对群众诉求，我会先耐心倾听并记录关键信息。",
    "公务员面试中如何回应群众诉求",
]

TEXT_SENTENCES = [
    "面对群众诉求，我会先耐心倾听并记录关键信息。",
    "然后按职责范围分类处理，能当场解决的立即解决。",
    "需要协调的事项会说明办理时限，并及时反馈进展。",
]


def read_wav(path: Path) -> tuple[bytes, dict, str]:
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
        "sample_rate_hz": rate,
        "channels": channels,
        "sample_format": "s16le",
        "sample_count": len(pcm) // 2,
        "duration_sec": round(len(pcm) / 2 / rate, 3),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
    }
    return pcm, meta, path.name


def segment_of(pcm: bytes, meta: dict, segment_id: str) -> dict:
    return {
        "segment_id": segment_id,
        "start_sample": 0,
        "end_sample": meta["sample_count"],
        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
    }


def vector_hash(vector: list[float]) -> str:
    array = np.round(np.asarray(vector, dtype=np.float64), 6).astype(np.float32)
    return hashlib.sha256(array.tobytes()).hexdigest().upper()


def vector_summary(embeddings: dict) -> dict:
    return {
        "dimension": embeddings["dimension"],
        "answer_sentences": [
            {
                "sentence_id": item["sentence_id"],
                "text": item["text"],
                "vector_sha256": vector_hash(item["vector"]),
                "vector_head8": item["vector"][:8],
            }
            for item in embeddings["answer_sentences"]
        ],
        "keypoints": [
            {
                "keypoint_id": item["keypoint_id"],
                "vector_sha256": vector_hash(item["vector"]),
                "vector_head8": item["vector"][:8],
            }
            for item in embeddings["keypoints"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav-a", required=True)
    parser.add_argument("--wav-b", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    wav_a = Path(args.wav_a).resolve()
    wav_b = Path(args.wav_b).resolve()
    out_path = Path(args.out).resolve()

    pcm_a, meta_a, name_a = read_wav(wav_a)
    pcm_b, meta_b, name_b = read_wav(wav_b)

    transcript_a = transcribe_segments([segment_of(pcm_a, meta_a, "seg-a")])["transcript"]
    transcript_b = transcribe_segments([segment_of(pcm_b, meta_b, "seg-b")])["transcript"]

    encoder = SemanticEncoder()
    tokens = [encoder.inspect(text) for text in TOKEN_PROBES]

    # 基线 1：真实转写（无标点，整段一句）
    embeddings_a = encoder.encode_transcript(transcript_a, KEYPOINTS)["embeddings"]
    matches_a_05 = match(embeddings_a, threshold=0.5)
    matches_a_08 = match(embeddings_a, threshold=0.8)

    # 基线 2：可控三句文本
    text_transcript = {
        "full_text": "".join(TEXT_SENTENCES),
        "segments": [
            {
                "segment_id": "seg-text",
                "start_sample": 0,
                "end_sample": 0,
                "text": "".join(TEXT_SENTENCES),
            }
        ],
    }
    embeddings_text = encoder.encode_transcript(text_transcript, KEYPOINTS)["embeddings"]
    matches_text_05 = match(embeddings_text, threshold=0.5)
    matches_text_08 = match(embeddings_text, threshold=0.8)

    payload = {
        "schema_version": "v1",
        "case_set": "S0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "generated_by": "彭雯青",
        "provenance": {
            "audio": "本机 Microsoft Huihui Desktop 合成的测试语音，非真人录音；仅用于链路与格式验证，不计入 S2 语料",
            "audio_storage": "experiments/samples/local/（已被 .gitignore 排除，文件不入库）",
            "note": "期望值由实现方首次运行生成并人工核对，属于基线锁定而非第三方独立预期；S1 由刘慧芳在手机端复跑比对",
            "known_limit": "Vosk 中文输出为空格分词且不带标点，真实转写基线中整段被切成一句；接入 M1 后以 VAD 段作为句子单位，句子粒度问题在 S1 解决",
        },
        "model_versions": {
            "m2": config.get_asset(config.VOSK_ASSET_ID)["version"],
            "m2_sha256": config.get_asset(config.VOSK_ASSET_ID)["sha256"],
            "m3": config.get_asset(config.SEMANTIC_ASSET_ID)["version"],
            "m3_sha256": config.get_asset(config.SEMANTIC_ASSET_ID)["sha256"],
            "m3_config": config.semantic_config(),
            "m4_threshold": config.matching_config(),
        },
        "cases": [
            {
                "case_id": "S0-T2-M2-A",
                "module": "M2",
                "input": {"wav": name_a, **meta_a},
                "expected": {"transcript": transcript_a},
            },
            {
                "case_id": "S0-T2-M2-B",
                "module": "M2",
                "input": {"wav": name_b, **meta_b},
                "expected": {"transcript": transcript_b},
            },
            {
                "case_id": "S0-T2-M3-TOKEN",
                "module": "M3",
                "input": {"texts": TOKEN_PROBES},
                "expected": {"inspect": tokens},
            },
            {
                "case_id": "S0-T2-M3-VECTOR-A",
                "module": "M3",
                "input": {"source_case": "S0-T2-M2-A", "keypoints": KEYPOINTS},
                "expected": vector_summary(embeddings_a),
            },
            {
                "case_id": "S0-T2-M4-A-0.5",
                "module": "M4",
                "input": {"source_case": "S0-T2-M3-VECTOR-A", "threshold": 0.5},
                "expected": matches_a_05,
            },
            {
                "case_id": "S0-T2-M4-A-0.8",
                "module": "M4",
                "input": {"source_case": "S0-T2-M3-VECTOR-A", "threshold": 0.8},
                "expected": matches_a_08,
            },
            {
                "case_id": "S0-T2-M3-VECTOR-TEXT",
                "module": "M3",
                "input": {"transcript": text_transcript, "keypoints": KEYPOINTS},
                "expected": {
                    "sentences_split": split_sentences("".join(TEXT_SENTENCES)),
                    **vector_summary(embeddings_text),
                },
            },
            {
                "case_id": "S0-T2-M4-TEXT-0.5",
                "module": "M4",
                "input": {"source_case": "S0-T2-M3-VECTOR-TEXT", "threshold": 0.5},
                "expected": matches_text_05,
            },
            {
                "case_id": "S0-T2-M4-TEXT-0.8",
                "module": "M4",
                "input": {"source_case": "S0-T2-M3-VECTOR-TEXT", "threshold": 0.8},
                "expected": matches_text_08,
            },
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out_path), "cases": len(payload["cases"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
