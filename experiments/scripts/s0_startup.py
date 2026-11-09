#!/usr/bin/env python
"""S0-P5：冷启动 / 热启动与内存占用测量。

- 语义模型：子进程冷启动 N 次（含 import、模型加载、首次推理），再在本进程做热启动 M 次；
- Vosk 模型：子进程冷启动 N 次（仅加载模型并做 1 秒静音识别）。

用法：
  python experiments/scripts/s0_startup.py --out experiments/results/s0_startup.csv
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEXT = "面对群众诉求，我会先耐心倾听并记录关键信息。"


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def peak_rss_mb() -> float:
    counters = _PMC()
    counters.cb = ctypes.sizeof(_PMC)
    psapi = ctypes.WinDLL("psapi.dll")
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PMC),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(handle)), ctypes.byref(counters), counters.cb):
        return float("nan")
    return round(counters.PeakWorkingSetSize / (1024 * 1024), 1)


def child(kind: str, out_path: Path) -> int:
    started = time.perf_counter()
    if kind == "semantic":
        from server.modules.semantic import SemanticEncoder

        encoder = SemanticEncoder()
        load_ms = (time.perf_counter() - started) * 1000
        infer_started = time.perf_counter()
        encoder.encode([TEXT])
        infer_ms = (time.perf_counter() - infer_started) * 1000
    elif kind == "vosk":
        import vosk
        from server.modules import config

        load_started = time.perf_counter()
        model = vosk.Model(str(config.vosk_model_path()))
        load_ms = (time.perf_counter() - load_started) * 1000
        infer_started = time.perf_counter()
        recognizer = vosk.KaldiRecognizer(model, 16000)
        recognizer.AcceptWaveform(b"\x00\x00" * 16000)
        recognizer.FinalResult()
        infer_ms = (time.perf_counter() - infer_started) * 1000
    else:
        raise ValueError(kind)

    payload = {
        "kind": kind,
        "load_ms": round(load_ms, 1),
        "infer_ms": round(infer_ms, 1),
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
        "peak_rss_mb": peak_rss_mb(),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


def run_child(kind: str, index: int) -> dict:
    out = PROJECT_ROOT / "experiments" / "results" / f"_startup_{kind}_{index}.json"
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", kind, "--child-out", str(out)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    out.unlink(missing_ok=True)
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=["semantic", "vosk"])
    parser.add_argument("--child-out")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "experiments" / "results" / "s0_startup.csv"))
    parser.add_argument("--cold", type=int, default=5)
    parser.add_argument("--warm", type=int, default=20)
    parser.add_argument("--vosk-cold", type=int, default=2)
    args = parser.parse_args()

    if args.child:
        return child(args.child, Path(args.child_out))

    rows: list[dict] = []
    for index in range(1, args.cold + 1):
        data = run_child("semantic", index)
        rows.append({"run_type": "cold", "model": "semantic", "index": index, **data})
    for index in range(1, args.vosk_cold + 1):
        data = run_child("vosk", index)
        rows.append({"run_type": "cold", "model": "vosk", "index": index, **data})

    from server.modules.semantic import SemanticEncoder

    encoder = SemanticEncoder()
    for index in range(1, args.warm + 1):
        started = time.perf_counter()
        encoder.encode([TEXT])
        elapsed_ms = (time.perf_counter() - started) * 1000
        rows.append(
            {
                "run_type": "warm",
                "model": "semantic",
                "index": index,
                "load_ms": 0.0,
                "infer_ms": round(elapsed_ms, 1),
                "total_ms": round(elapsed_ms, 1),
                "peak_rss_mb": peak_rss_mb(),
            }
        )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["run_type", "model", "index", "load_ms", "infer_ms", "total_ms", "peak_rss_mb"]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"out": str(out_path), "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
