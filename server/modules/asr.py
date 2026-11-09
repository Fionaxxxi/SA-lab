"""M2：语音转写（Vosk）。

契约（总计划 4.2 / 本组 S0 契约）：
- 输入 segments[{segment_id, start_sample, end_sample, pcm_b64}]，16 kHz 单声道 s16le；
- 输出 transcript{full_text, segments[{segment_id, start_sample, end_sample, text}]}；
- 时间戳沿用输入段的原始采样索引，左闭右开；
- 段内无文本时保留段、text 为空；全部段无文本 → NO_TRANSCRIPT；
- 模型缺失 → MODEL_UNAVAILABLE。

已知限制：每段独立创建 KaldiRecognizer，段间不共享解码上下文，
因此跨段的长句不会被模型自动接续；这是段级契约的代价，S1 需在
手机上用同一段输入复核是否可接受。

扩展字段（实验性，默认关闭）：`include_words=True` 时每段附加
`words[{word,start_sample,end_sample,conf}]`，用于 M3 按停顿切句。
该字段尚未进入 schema，需 S0-P7 评审后再决定是否默认开启。
"""

from __future__ import annotations

import base64
import binascii
import json
from functools import lru_cache
from pathlib import Path

import vosk

from . import config
from .errors import InvalidPayload, ModelUnavailable, NoSpeech, NoTranscript

SAMPLE_RATE_HZ = 16000
BYTES_PER_SAMPLE = 2
SEGMENT_JOINER = "\n"
_CHUNK_BYTES = 8000  # 0.25 s

try:  # 降低 Vosk/Kaldi 日志噪声；不同版本可能没有该函数
    vosk.SetLogLevel(-1)
except Exception:
    pass


@lru_cache(maxsize=2)
def _load_model_cached(model_dir: str) -> vosk.Model:
    try:
        return vosk.Model(model_dir)
    except Exception as exc:  # 模型损坏、内存不足、目录缺文件
        raise ModelUnavailable(
            f"Vosk 模型加载失败：{model_dir}",
            {"reason": str(exc)},
        ) from exc


def load_model(model_dir: str | Path | None = None) -> vosk.Model:
    """公开入口：加载（并缓存）Vosk 模型，供转写与基准脚本共用。"""
    return _load_model_cached(str(model_dir or config.vosk_model_path()))


def _decode_segment(item: dict, index: int, strict: bool) -> tuple[str, int, int, bytes]:
    if not isinstance(item, dict):
        raise InvalidPayload(f"segments[{index}] 不是对象")

    segment_id = item.get("segment_id")
    if not isinstance(segment_id, str) or not segment_id:
        raise InvalidPayload(f"segments[{index}].segment_id 缺失或不是非空字符串")

    start = item.get("start_sample")
    end = item.get("end_sample")
    if not isinstance(start, int) or not isinstance(end, int):
        raise InvalidPayload(f"segments[{index}] 的 start_sample/end_sample 必须是整数")
    if start < 0 or end <= start:
        raise InvalidPayload(f"segments[{index}] 区间非法：start={start}, end={end}")

    pcm_b64 = item.get("pcm_b64")
    if not isinstance(pcm_b64, str) or not pcm_b64:
        raise InvalidPayload(f"segments[{index}].pcm_b64 缺失或为空")
    try:
        pcm = base64.b64decode(pcm_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidPayload(
            f"segments[{index}].pcm_b64 不是合法 Base64",
            {"reason": str(exc)},
        ) from exc

    if len(pcm) % BYTES_PER_SAMPLE != 0:
        raise InvalidPayload(
            f"segments[{index}] PCM 字节数不是 2 的整数倍：{len(pcm)}"
        )
    expected = (end - start) * BYTES_PER_SAMPLE
    if strict and len(pcm) != expected:
        raise InvalidPayload(
            f"segments[{index}] PCM 字节数与区间不匹配",
            {"expected_bytes": expected, "actual_bytes": len(pcm)},
        )
    return segment_id, start, end, pcm


def _recognize(model: vosk.Model, pcm: bytes, with_words: bool = False) -> tuple[str, list[dict]]:
    recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE_HZ)
    if hasattr(recognizer, "SetWords"):
        recognizer.SetWords(bool(with_words))
    for offset in range(0, len(pcm), _CHUNK_BYTES):
        recognizer.AcceptWaveform(pcm[offset : offset + _CHUNK_BYTES])
    result = json.loads(recognizer.FinalResult())
    text = (result.get("text") or "").strip()
    words = list(result.get("result") or []) if with_words else []
    return text, words


def _word_entries(words: list[dict], segment_start: int, segment_end: int) -> list[dict]:
    """把 Vosk 的相对秒级词时间戳转成绝对采样索引，并夹在段边界内。"""
    entries: list[dict] = []
    for item in words:
        word = (item.get("word") or "").strip()
        if not word:
            continue
        try:
            start_sec = float(item.get("start"))
            end_sec = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        start_sample = segment_start + int(round(start_sec * SAMPLE_RATE_HZ))
        end_sample = segment_start + int(round(end_sec * SAMPLE_RATE_HZ))
        start_sample = max(segment_start, min(start_sample, segment_end))
        end_sample = max(start_sample, min(end_sample, segment_end))
        entry = {"word": word, "start_sample": start_sample, "end_sample": end_sample}
        conf = item.get("conf")
        if isinstance(conf, (int, float)):
            entry["conf"] = round(float(conf), 4)
        entries.append(entry)
    return entries


def transcribe_pcm(pcm: bytes, model_dir: str | Path | None = None) -> str:
    """单段 PCM 转写，返回文本（可能为空字符串）。"""
    if not isinstance(pcm, (bytes, bytearray)):
        raise InvalidPayload("pcm 必须是 bytes")
    if len(pcm) == 0:
        raise InvalidPayload("pcm 为空")
    if len(pcm) % BYTES_PER_SAMPLE != 0:
        raise InvalidPayload(f"PCM 字节数不是 2 的整数倍：{len(pcm)}")

    model = load_model(model_dir)
    return _recognize(model, bytes(pcm))[0]


def transcribe_segments(
    segments: list[dict],
    model_dir: str | Path | None = None,
    strict: bool = True,
    include_words: bool = False,
) -> dict:
    """把 M1 片段列表转成 transcript 契约对象。"""
    if not isinstance(segments, list):
        raise InvalidPayload("segments 必须是数组")
    if not segments:
        raise NoSpeech("segments 为空，没有可转写内容")

    model = load_model(model_dir)

    out_segments: list[dict] = []
    seen_ids: set[str] = set()
    last_end = -1
    texts: list[str] = []

    for index, item in enumerate(segments):
        segment_id, start, end, pcm = _decode_segment(item, index, strict)

        if segment_id in seen_ids:
            raise InvalidPayload(f"segment_id 重复：{segment_id}")
        seen_ids.add(segment_id)

        if start < last_end:
            raise InvalidPayload(
                f"segments 未按起点升序或存在重叠：{segment_id} start={start}, 上一段 end={last_end}"
            )
        last_end = end

        text, words = _recognize(model, pcm, include_words)
        if text:
            texts.append(text)
        entry = {
            "segment_id": segment_id,
            "start_sample": start,
            "end_sample": end,
            "text": text,
        }
        if include_words:
            entry["words"] = _word_entries(words, start, end)
        out_segments.append(entry)

    if not texts:
        raise NoTranscript("所有片段均未产生转写文本")

    return {
        "transcript": {
            "full_text": SEGMENT_JOINER.join(texts),
            "segments": out_segments,
        }
    }
