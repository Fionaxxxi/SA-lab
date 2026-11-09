#!/usr/bin/env python
"""Android 端 M3 tokenizer 可行性探针。

multilingual MiniLM 的 tokenizer.json 使用 SentencePiece 的
Precompiled normalizer（precompiled_charsmap），Android/Java 端没有现成实现。
本脚本量化“去掉 normalizer”后 token 序列是否会变，为 S1 选型提供依据。

输出：experiments/results/s0_android_tokenizer_probe.json
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from tokenizers import Tokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.modules import config  # noqa: E402

SAMPLES = [
    "面对群众诉求我会先耐心倾听准确记录问题",  # ASR 实际输出形态（无标点）
    "面对群众诉求，我会先耐心倾听。",  # 全角标点
    "面对群众诉求,我会先耐心倾听.",  # 半角标点
    "2024年招录公告",  # 半角数字
    "２０２４年招录公告",  # 全角数字
    "Hello World",
    "hello world",
]


def main() -> int:
    _, tokenizer_path = config.semantic_paths()
    raw = json.loads(Path(tokenizer_path).read_text(encoding="utf-8"))

    baseline = Tokenizer.from_str(json.dumps(raw, ensure_ascii=False))

    stripped = copy.deepcopy(raw)
    stripped["normalizer"] = None
    no_normalizer = Tokenizer.from_str(json.dumps(stripped, ensure_ascii=False))

    results = []
    matched = 0
    for text in SAMPLES:
        ids_base = baseline.encode(text).ids
        ids_stripped = no_normalizer.encode(text).ids
        same = ids_base == ids_stripped
        matched += int(same)
        results.append(
            {
                "text": text,
                "same_ids": same,
                "len_base": len(ids_base),
                "len_no_normalizer": len(ids_stripped),
                "ids_base_head": ids_base[:24],
                "ids_no_normalizer_head": ids_stripped[:24],
            }
        )

    payload = {
        "tokenizer": str(tokenizer_path),
        "normalizer_type": (raw.get("normalizer") or {}).get("type"),
        "pre_tokenizer": (raw.get("pre_tokenizer") or {}).get("type"),
        "model_type": (raw.get("model") or {}).get("type"),
        "vocab_size": len((raw.get("model") or {}).get("vocab") or []),
        "n_samples": len(SAMPLES),
        "n_same": matched,
        "samples": results,
        "interpretation": (
            "所有样本一致 → 去掉 normalizer 不会改变编码，Android 可跳过 charsmap；"
            "仅部分一致 → 需在 Android 侧补轻量归一化（至少 NFKC + 去标点）；"
            "全部不一致 → 必须实现 precompiled_charsmap 或更换 tokenizer 方案。"
        ),
    }

    out = PROJECT_ROOT / "experiments" / "results" / "s0_android_tokenizer_probe.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "n_same": matched, "n_total": len(SAMPLES)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
