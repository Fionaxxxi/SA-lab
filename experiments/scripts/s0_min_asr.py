#!/usr/bin/env python
"""S0-P2 最小转写调用：WAV -> transcript 契约对象。

用法：
  python experiments/scripts/s0_min_asr.py --wav <16k mono s16le wav> --out <json>
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules.asr import transcribe_segments  # noqa: E402
from server.modules.errors import ModuleError  # noqa: E402


def read_wav(path: Path) -> tuple[bytes, dict]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
        pcm = handle.readframes(frame_count)

    if channels != 1 or sample_width != 2 or frame_rate != 16000:
        raise ValueError(
            f"WAV 参数不符：channels={channels}, width={sample_width}, rate={frame_rate}；"
            "要求 16 kHz / 单声道 / 16 bit"
        )
    if len(pcm) % 2 != 0:
        raise ValueError(f"PCM 字节数不是 2 的整数倍：{len(pcm)}")

    meta = {
        "channels": channels,
        "sample_width_bytes": sample_width,
        "sample_rate_hz": frame_rate,
        "sample_count": len(pcm) // 2,
        "duration_sec": round(len(pcm) / 2 / frame_rate, 3),
    }
    return pcm, meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-strict", action="store_true", help="跳过度长度校验，仅用于对照实验")
    args = parser.parse_args()

    wav_path = Path(args.wav).resolve()
    out_path = Path(args.out).resolve()
    raw = wav_path.read_bytes()
    pcm, meta = read_wav(wav_path)

    segment = {
        "segment_id": "seg-1",
        "start_sample": 0,
        "end_sample": meta["sample_count"],
        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
    }

    started = time.perf_counter()
    try:
        result = transcribe_segments([segment], strict=not args.no_strict)
        error = None
    except ModuleError as exc:
        result = None
        error = exc.to_dict()
    elapsed_ms = (time.perf_counter() - started) * 1000

    payload = {
        "case": "S0-P2",
        "wav": wav_path.name,
        "wav_sha256": hashlib.sha256(raw).hexdigest().upper(),
        "audio": meta,
        "elapsed_ms": round(elapsed_ms, 1),
        "error": error,
        "transcript": (result or {}).get("transcript"),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": error is None, "out": str(out_path), "elapsed_ms": round(elapsed_ms, 1)}, ensure_ascii=False))
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
