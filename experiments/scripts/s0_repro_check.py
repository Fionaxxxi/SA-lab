#!/usr/bin/env python
"""金样例复现性核对：多次运行结果逐用例比对。

用途：golden-s0.json 是跨端对齐的基线，必须证明"同一环境、同一输入、
重复运行得到相同期望值"。本脚本只比较可复现字段，忽略 generated_at
与 elapsed_ms 这类每次都变的元数据。

用法：
  python experiments/scripts/s0_repro_check.py \
      --runs experiments/results/repro/golden_run_1.json \
             experiments/results/repro/golden_run_2.json \
             experiments/results/repro/golden_run_3.json \
      --out experiments/results/s0_repro_check.json

退出码：全部一致 0；存在差异 2。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

VOLATILE_TOP_KEYS = {"generated_at", "elapsed_ms"}


def load_run(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} 顶层不是对象")
    return payload


def strip_volatile(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key not in VOLATILE_TOP_KEYS}


def diff_paths(left, right, prefix: str = "") -> list[str]:
    """返回两棵 JSON 树的值差异路径；空列表表示完全相同。"""
    if type(left) is not type(right):
        return [f"{prefix or '<root>'}: type {type(left).__name__} != {type(right).__name__}"]

    if isinstance(left, dict):
        result: list[str] = []
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in left:
                result.append(f"{path}: only in later run")
            elif key not in right:
                result.append(f"{path}: only in earlier run")
            else:
                result.extend(diff_paths(left[key], right[key], path))
        return result

    if isinstance(left, list):
        result = []
        if len(left) != len(right):
            result.append(f"{prefix}: length {len(left)} != {len(right)}")
        for index in range(min(len(left), len(right))):
            result.extend(diff_paths(left[index], right[index], f"{prefix}[{index}]"))
        return result

    if isinstance(left, float) and isinstance(right, float):
        if left != right:
            return [f"{prefix}: {left!r} != {right!r}"]
        return []

    if left != right:
        return [f"{prefix}: {left!r} != {right!r}"]
    return []


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def case_index(payload: dict) -> dict[str, dict]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return {}
    return {
        str(case.get("case_id")): case
        for case in cases
        if isinstance(case, dict) and case.get("case_id")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    paths = [Path(item).resolve() for item in args.runs]
    for path in paths:
        if not path.is_file():
            print(f"缺少文件：{path}", file=sys.stderr)
            return 2

    payloads = [strip_volatile(load_run(path)) for path in paths]
    indexes = [case_index(payload) for payload in payloads]

    case_ids = sorted({case_id for index in indexes for case_id in index})
    case_reports: list[dict] = []
    for case_id in case_ids:
        present = [case_id in index for index in indexes]
        if not all(present):
            case_reports.append(
                {
                    "case_id": case_id,
                    "identical": False,
                    "diff": [f"用例缺失：runs {[i + 1 for i, ok in enumerate(present) if not ok]}"],
                }
            )
            continue
        base = indexes[0][case_id]
        diffs: list[str] = []
        for index in indexes[1:]:
            diffs.extend(diff_paths(base, index[case_id]))
        case_reports.append(
            {"case_id": case_id, "identical": not diffs, "diff": diffs}
        )

    top_diffs = diff_paths(payloads[0], payloads[1]) if len(payloads) > 1 else []

    report = {
        "schema_version": "v1",
        "runs": [{"path": str(path), "sha256": file_sha256(path)} for path in paths],
        "run_visible_keys": sorted(payloads[0].keys()),
        "ignored_volatile_keys": sorted(VOLATILE_TOP_KEYS),
        "case_count": len(case_ids),
        "all_cases_identical": all(item["identical"] for item in case_reports),
        "cases": case_reports,
        "non_case_field_diff": top_diffs,
        "summary": {
            "identical_cases": sum(1 for item in case_reports if item["identical"]),
            "different_cases": sum(1 for item in case_reports if not item["identical"]),
        },
    }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "out": str(out_path),
                "case_count": report["case_count"],
                "identical_cases": report["summary"]["identical_cases"],
                "different_cases": report["summary"]["different_cases"],
                "all_cases_identical": report["all_cases_identical"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["all_cases_identical"] and not top_diffs else 2


if __name__ == "__main__":
    raise SystemExit(main())
