#!/usr/bin/env python
"""M3 ONNX 动态量化探针：fp32 vs int8 的体积、精度与耗时。

背景：S1 要在手机端跑 M3，fp32 模型 470 MB 有 OOM 风险。本探针在电脑端
量化并量化前后对比，给出"体积降多少、向量偏多少、分数变多少"的可核验
数据，供 S1 决定是否换 int8、以及新容差怎么定。

注意：本探针只做动态量化（权重 int8、激活 fp32），不改变输入输出契约；
结果不代表手机端性能，手机端仍需真机实测。

用法：
  python experiments/scripts/s0_m3_quant_probe.py \
      --model models/weights/minilm-multilingual/model.onnx \
      --tokenizer models/weights/minilm-multilingual/tokenizer.json \
      --out-model models/weights/minilm-multilingual/model_int8.onnx \
      --out experiments/results/s0_m3_quant_probe.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules.semantic import SemanticEncoder  # noqa: E402

SENTENCES = [
    "面对群众诉求，我会先耐心倾听并记录关键信息。",
    "然后按职责范围分类处理，能当场解决的立即解决。",
    "需要协调的事项会说明办理时限，并及时反馈进展。",
    "考生开始作答",
    "首先我会稳定情绪，弄清对方最关心的问题。",
    "然后核实事实依据，避免主观判断。",
    "最后提出可执行的方案，并约定下一次沟通时间。",
    "能够当场解决的立即解决，需要协调的说明办理时限并及时反馈进展。",
    "群众来办事时情绪激动是常见情况，我会先把人请到安静的地方坐下，倒一杯水，"
    "让对方把话说完，不打断、不反驳，同时把时间、地点、涉及人员和诉求逐项记下来，"
    "再复述一遍确认没有理解偏差，最后说明我接下来会怎么处理、多久给答复。",
    "如果事项超出我的职责范围，我会明确告知应该找哪个窗口、需要带哪些材料，"
    "并帮忙对接经办人，避免群众来回跑。",
]

KEYPOINTS = [
    {"keypoint_id": "k1", "text": "耐心倾听并记录群众诉求"},
    {"keypoint_id": "k2", "text": "按职责分类处理，当场解决"},
    {"keypoint_id": "k3", "text": "说明办理时限并及时反馈"},
]


def file_meta(path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(raw),
        "mb": round(len(raw) / 1024 / 1024, 2),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
    }


def encode_all(encoder: SemanticEncoder, texts: list[str]) -> np.ndarray:
    return encoder.encode(texts)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def latency(encoder: SemanticEncoder, text: str, repeat: int, warmup: int) -> dict:
    for _ in range(warmup):
        encoder.encode([text])
    times: list[float] = []
    for _ in range(repeat):
        started = time.perf_counter()
        encoder.encode([text])
        times.append((time.perf_counter() - started) * 1000)
    ordered = sorted(times)
    return {
        "repeat": repeat,
        "warmup": warmup,
        "p50_ms": round(statistics.median(ordered), 3),
        "p90_ms": round(ordered[int(round(0.9 * (len(ordered) - 1)))], 3),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
        "mean_ms": round(sum(ordered) / len(ordered), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--out-model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--repeat", type=int, default=15)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()

    model_path = Path(args.model).resolve()
    tokenizer_path = Path(args.tokenizer).resolve()
    out_model = Path(args.out_model).resolve()
    out_json = Path(args.out).resolve()
    for path in (model_path, tokenizer_path):
        if not path.is_file():
            print(f"缺少文件：{path}", file=sys.stderr)
            return 2

    started = time.perf_counter()
    fp32_meta = file_meta(model_path)
    load_fp32_started = time.perf_counter()
    encoder_fp32 = SemanticEncoder(
        onnx_path=model_path, tokenizer_path=tokenizer_path, intra_threads=1
    )
    load_fp32_ms = round((time.perf_counter() - load_fp32_started) * 1000, 1)

    # ---------------------------------------------------------------- 量化
    from onnxruntime.quantization import QuantType, quantize_dynamic

    out_model.parent.mkdir(parents=True, exist_ok=True)
    quant_started = time.perf_counter()
    quantize_dynamic(str(model_path), str(out_model), weight_type=QuantType.QInt8)
    quant_ms = round((time.perf_counter() - quant_started) * 1000, 1)
    int8_meta = file_meta(out_model)

    load_int8_started = time.perf_counter()
    encoder_int8 = SemanticEncoder(
        onnx_path=out_model, tokenizer_path=tokenizer_path, intra_threads=1
    )
    load_int8_ms = round((time.perf_counter() - load_int8_started) * 1000, 1)

    # ---------------------------------------------------------------- 向量对比
    vec_fp32 = encode_all(encoder_fp32, SENTENCES)
    vec_int8 = encode_all(encoder_int8, SENTENCES)

    if vec_fp32.shape != vec_int8.shape:
        raise RuntimeError(f"形状不一致：{vec_fp32.shape} vs {vec_int8.shape}")

    cos_values = [cosine(vec_fp32[i], vec_int8[i]) for i in range(len(SENTENCES))]
    abs_diff = np.abs(vec_fp32 - vec_int8)
    row_abs_max = abs_diff.max(axis=1)

    # ---------------------------------------------------------------- 匹配对比
    kp_fp32 = encode_all(encoder_fp32, [item["text"] for item in KEYPOINTS])
    kp_int8 = encode_all(encoder_int8, [item["text"] for item in KEYPOINTS])

    score_fp32 = vec_fp32 @ kp_fp32.T
    score_int8 = vec_int8 @ kp_int8.T
    score_diff = np.abs(score_fp32 - score_int8)
    top1_fp32 = score_fp32.argmax(axis=0)
    top1_int8 = score_int8.argmax(axis=0)

    matching_rows = []
    for kp_index, keypoint in enumerate(KEYPOINTS):
        matching_rows.append(
            {
                "keypoint_id": keypoint["keypoint_id"],
                "fp32_best_sentence": int(top1_fp32[kp_index]),
                "fp32_best_score": round(float(score_fp32[top1_fp32[kp_index], kp_index]), 6),
                "int8_best_sentence": int(top1_int8[kp_index]),
                "int8_best_score": round(float(score_int8[top1_int8[kp_index], kp_index]), 6),
                "top1_same": bool(top1_fp32[kp_index] == top1_int8[kp_index]),
                "max_score_abs_diff": round(float(score_diff[:, kp_index].max()), 6),
                "threshold_0_5_flip": bool(
                    np.any((score_fp32[:, kp_index] >= 0.5) != (score_int8[:, kp_index] >= 0.5))
                ),
                "threshold_0_8_flip": bool(
                    np.any((score_fp32[:, kp_index] >= 0.8) != (score_int8[:, kp_index] >= 0.8))
                ),
            }
        )

    # ---------------------------------------------------------------- 耗时
    probe_text = SENTENCES[0]
    lat_fp32 = latency(encoder_fp32, probe_text, args.repeat, args.warmup)
    lat_int8 = latency(encoder_int8, probe_text, args.repeat, args.warmup)

    payload = {
        "schema_version": "v1",
        "probe": "M3 dynamic quantization (int8 weights)",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host_note": "本机 CPU、单线程 intra_op；不代表手机端性能",
        "fp32": {
            **fp32_meta,
            "session_load_ms": load_fp32_ms,
            "input_names": encoder_fp32._input_names,
        },
        "int8": {
            **int8_meta,
            "session_load_ms": load_int8_ms,
            "size_ratio_vs_fp32": round(int8_meta["bytes"] / fp32_meta["bytes"], 4),
            "quantize_ms": quant_ms,
        },
        "dimension": int(vec_fp32.shape[1]),
        "vector_cosine_fp32_vs_int8": {
            "min": round(min(cos_values), 8),
            "mean": round(sum(cos_values) / len(cos_values), 8),
            "max": round(max(cos_values), 8),
            "per_sentence": [round(value, 8) for value in cos_values],
        },
        "vector_abs_diff": {
            "max": round(float(abs_diff.max()), 8),
            "mean": round(float(abs_diff.mean()), 8),
            "per_sentence_max": [round(float(value), 8) for value in row_abs_max],
        },
        "matching": {
            "sentence_count": len(SENTENCES),
            "keypoint_count": len(KEYPOINTS),
            "max_score_abs_diff": round(float(score_diff.max()), 6),
            "mean_score_abs_diff": round(float(score_diff.mean()), 6),
            "top1_same_count": int((top1_fp32 == top1_int8).sum()),
            "rows": matching_rows,
        },
        "latency_ms": {
            "fp32": lat_fp32,
            "int8": lat_int8,
            "speedup_p50": round(lat_fp32["p50_ms"] / max(lat_int8["p50_ms"], 1e-9), 3),
        },
        "sentences": SENTENCES,
        "keypoints": KEYPOINTS,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "out": str(out_json),
                "fp32_mb": fp32_meta["mb"],
                "int8_mb": int8_meta["mb"],
                "ratio": payload["int8"]["size_ratio_vs_fp32"],
                "cosine_min": payload["vector_cosine_fp32_vs_int8"]["min"],
                "score_max_abs_diff": payload["matching"]["max_score_abs_diff"],
                "top1_same": payload["matching"]["top1_same_count"],
                "p50_fp32_ms": lat_fp32["p50_ms"],
                "p50_int8_ms": lat_int8["p50_ms"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
