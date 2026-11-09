#!/usr/bin/env python
"""S2 指标计算：CER、端到端 P50/P90、RTF、完成率、要点覆盖率。

输入为 JSONL（每行一条作答记录），字段约定：

{
  "case_id": "c001",
  "device": "mi14",              # 设备标识
  "success": true,               # 链路是否成功产出结果
  "cancelled": false,            # 是否被用户取消
  "ref": "人工转写的参考文本",
  "hyp": "系统转写文本",
  "end_to_end_ms": 3120,         # 从录音结束到反馈展示
  "audio_ms": 15000,             # 作答音频时长
  "rtf": 0.21,                   # 整链 RTF（可选；缺省时用 end_to_end_ms/audio_ms）
  "keypoints": {"k1": true, "k2": false, "k3": true}
}

口径（必须与报告一致）：
- CER 在“去空白、去标点、英文小写”后按字符编辑距离计算，分母为参考文本字符数；
- 耗时分位数只统计 success=true 且 cancelled=false 的记录；
- 完成率 = 成功数 / 有效记录数（有效 = 未取消），取消记录单列；
  同时输出 completion_rate_including_cancelled = 成功数 / 全部记录，供口径核对；
- P90 用线性插值（与 numpy percentile 默认一致）。

用法：
  python experiments/scripts/compute_metrics.py \
      --input experiments/results/s2_records.jsonl \
      --out experiments/results/s2_summary.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PUNCTUATION = set("，。！？；：、,.!?;:()（）[]【】\"'“”‘’—-…·《》<>/\\|")

REQUIRED_FIELDS = ("case_id", "success")


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("文本必须是字符串")
    return "".join(
        char for char in text.lower() if not char.isspace() and char not in PUNCTUATION
    )


def edit_distance(ref: str, hyp: str) -> int:
    """Levenshtein 距离（字符级）。"""
    if len(ref) < len(hyp):
        ref, hyp = hyp, ref
    previous = list(range(len(hyp) + 1))
    for i, ref_char in enumerate(ref, start=1):
        current = [i]
        for j, hyp_char in enumerate(hyp, start=1):
            insert = previous[j] + 1
            delete = current[j - 1] + 1
            substitute = previous[j - 1] + (ref_char != hyp_char)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def char_error_rate(ref: str, hyp: str) -> dict:
    ref_norm = normalize_text(ref)
    hyp_norm = normalize_text(hyp)
    if not ref_norm:
        raise ValueError("参考文本去标点后为空，无法计算 CER")
    distance = edit_distance(ref_norm, hyp_norm)
    return {
        "cer": round(distance / len(ref_norm), 6),
        "edit_distance": distance,
        "ref_chars": len(ref_norm),
        "hyp_chars": len(hyp_norm),
    }


def percentile(values: list[float], p: float) -> float | None:
    """线性插值分位数，与 numpy.percentile 默认口径一致。"""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (p / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(records: list[dict]) -> dict:
    valid = [item for item in records if not item.get("cancelled")]
    succeeded = [item for item in valid if item.get("success")]

    cer_values: list[float] = []
    for item in succeeded:
        ref = item.get("ref")
        hyp = item.get("hyp")
        if isinstance(ref, str) and isinstance(hyp, str) and ref.strip():
            cer_values.append(char_error_rate(ref, hyp)["cer"])

    e2e_values = [
        float(item["end_to_end_ms"])
        for item in succeeded
        if isinstance(item.get("end_to_end_ms"), (int, float))
    ]

    rtf_values: list[float] = []
    for item in succeeded:
        if isinstance(item.get("rtf"), (int, float)):
            rtf_values.append(float(item["rtf"]))
        elif isinstance(item.get("end_to_end_ms"), (int, float)) and item.get("audio_ms"):
            rtf_values.append(float(item["end_to_end_ms"]) / float(item["audio_ms"]))

    covered = 0
    total_keypoints = 0
    for item in succeeded:
        keypoints = item.get("keypoints")
        if isinstance(keypoints, dict):
            total_keypoints += len(keypoints)
            covered += sum(1 for value in keypoints.values() if value)

    return {
        "n_records": len(records),
        "n_valid": len(valid),
        "n_success": len(succeeded),
        "n_cancelled": len(records) - len(valid),
        "completion_rate": round(len(succeeded) / len(valid), 6) if valid else None,
        "completion_rate_including_cancelled": (
            round(len(succeeded) / len(records), 6) if records else None
        ),
        "cer": {
            "n": len(cer_values),
            "mean": round(sum(cer_values) / len(cer_values), 6) if cer_values else None,
            "p90": round(percentile(cer_values, 90), 6) if cer_values else None,
            "max": round(max(cer_values), 6) if cer_values else None,
        },
        "end_to_end_ms": {
            "n": len(e2e_values),
            "p50": round(percentile(e2e_values, 50), 1) if e2e_values else None,
            "p90": round(percentile(e2e_values, 90), 1) if e2e_values else None,
            "max": round(max(e2e_values), 1) if e2e_values else None,
        },
        "rtf": {
            "n": len(rtf_values),
            "p50": round(percentile(rtf_values, 50), 4) if rtf_values else None,
            "p90": round(percentile(rtf_values, 90), 4) if rtf_values else None,
            "max": round(max(rtf_values), 4) if rtf_values else None,
        },
        "keypoint_coverage": {
            "covered": covered,
            "total": total_keypoints,
            "rate": round(covered / total_keypoints, 6) if total_keypoints else None,
        },
    }


def load_records(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{line_no} 不是合法 JSON：{exc}") from exc
            missing = [field for field in REQUIRED_FIELDS if field not in record]
            if missing:
                raise ValueError(f"{path.name}:{line_no} 缺少字段：{missing}")
            records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default=None, help="只统计指定设备")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    records = load_records(input_path)
    if args.device:
        records = [item for item in records if item.get("device") == args.device]
    summary = summarize(records)
    summary["source"] = {
        "input": str(input_path),
        "device_filter": args.device,
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
    }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
