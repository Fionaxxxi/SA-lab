"""模块公共配置：模型清单读取与路径解析。

约定：所有模型参数（维度、max_length、pooling、阈值）都从
models/manifest.json 读取，不在模块代码里写死。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"
WEIGHTS_DIR = MODELS_DIR / "weights"
MANIFEST_PATH = MODELS_DIR / "manifest.json"

VOSK_ASSET_ID = "m2-vosk-cn-0.22"
SEMANTIC_ASSET_ID = "m3-minilm-multilingual-l12-onnx"
TOKENIZER_ASSET_ID = "m3-tokenizer-multilingual"


class ConfigError(RuntimeError):
    """清单缺失、字段缺失或路径不可用。"""


@lru_cache(maxsize=1)
def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        raise ConfigError(f"模型清单不存在：{MANIFEST_PATH}")
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_asset(asset_id: str) -> dict:
    for asset in load_manifest().get("assets", []):
        if asset.get("asset_id") == asset_id:
            return asset
    raise ConfigError(f"模型清单中没有 asset_id={asset_id}")


def _local_path(asset: dict) -> Path:
    rel = asset.get("local_path")
    if not rel:
        raise ConfigError(f"asset {asset.get('asset_id')} 缺少 local_path")
    path = (PROJECT_ROOT / rel).resolve()
    return path


def vosk_model_path() -> Path:
    path = _local_path(get_asset(VOSK_ASSET_ID))
    if not (path / "am" / "final.mdl").is_file():
        raise ConfigError(f"Vosk 模型目录不完整（缺 am/final.mdl）：{path}")
    return path


def semantic_paths() -> tuple[Path, Path]:
    onnx_path = _local_path(get_asset(SEMANTIC_ASSET_ID))
    tokenizer_path = _local_path(get_asset(TOKENIZER_ASSET_ID))
    if not onnx_path.is_file():
        raise ConfigError(f"语义模型不存在：{onnx_path}")
    if not tokenizer_path.is_file():
        raise ConfigError(f"tokenizer 不存在：{tokenizer_path}")
    return onnx_path, tokenizer_path


def semantic_config() -> dict:
    cfg = get_asset(SEMANTIC_ASSET_ID).get("config", {})
    return {
        "dimension": int(cfg.get("dimension", 384)),
        "max_length": int(cfg.get("max_length", 128)),
        "pooling": cfg.get("pooling", "mean"),
        "normalize": bool(cfg.get("normalize", True)),
    }


def matching_config() -> dict:
    cfg = load_manifest().get("configs", {}).get("m4_matching", {})
    return {
        "threshold": float(cfg.get("threshold", 0.5)),
        "score_round_digits": int(cfg.get("score_round_digits", 6)),
        "threshold_status": cfg.get("threshold_status", "provisional"),
    }
