"""M3：句向量编码（multilingual MiniLM ONNX）。

契约：
- 输入 transcript + keypoints[{keypoint_id, text}]；
- 输出 embeddings{dimension, answer_sentences[{sentence_id, text, vector}],
  keypoints[{keypoint_id, vector}]}；
- 384 维、max_length=128、mean pooling、L2 归一化，参数全部读 manifest；
- 空句丢弃；全部句子为空 → NO_TRANSCRIPT；
- 向量非法（维度不符、NaN/Inf）→ INVALID_PAYLOAD。

句子切分默认只按句末标点（。！？；）与换行，逗号不切，避免把口语长句
拆成碎片影响匹配。

补充（实验性，默认关闭）：当 M2 提供词级时间戳时，可按词间停顿切句，
解决 Vosk 中文输出无标点、整段被切成一句的问题。相关参数
`use_word_pauses` / `pause_ms` 尚未进入 schema，需 S0-P7 评审。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from . import config
from .errors import InvalidPayload, ModelUnavailable, NoTranscript

SENTENCE_DELIMITERS = {"。", "！", "？", "；", "\n"}
VECTOR_ROUND_DIGITS = 6
PAUSE_SPLIT_MS_DEFAULT = 350
SAMPLES_PER_MS = 16  # 16 kHz 下 1 ms = 16 个采样


def split_sentences(text: str) -> list[str]:
    """按句末标点切句，保留标点，丢弃空白句。"""
    sentences: list[str] = []
    buffer: list[str] = []
    for char in text:
        buffer.append(char)
        if char in SENTENCE_DELIMITERS:
            candidate = "".join(buffer).strip()
            if candidate:
                sentences.append(candidate)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)
    return sentences


def split_sentences_by_pauses(
    words: list[dict],
    pause_ms: int = PAUSE_SPLIT_MS_DEFAULT,
) -> list[dict]:
    """按词间静音切句。

    输入为 M2 的 words[{word,start_sample,end_sample}]；相邻词间隔
    >= pause_ms 时切开。返回 [{text,start_sample,end_sample}]，
    text 为词块直接拼接（中文不补空格）。
    """
    if not isinstance(words, list) or not words:
        return []

    pause_samples = max(1, int(pause_ms) * SAMPLES_PER_MS)
    groups: list[list[dict]] = []
    current: list[dict] = []

    for item in words:
        if not isinstance(item, dict) or not item.get("word"):
            continue
        if current:
            start = item.get("start_sample")
            prev_end = current[-1].get("end_sample")
            if isinstance(start, int) and isinstance(prev_end, int) and start - prev_end >= pause_samples:
                groups.append(current)
                current = []
        current.append(item)
    if current:
        groups.append(current)

    result: list[dict] = []
    for group in groups:
        text = "".join(str(item.get("word", "")) for item in group).strip()
        if not text:
            continue
        result.append(
            {
                "text": text,
                "start_sample": group[0].get("start_sample"),
                "end_sample": group[-1].get("end_sample"),
            }
        )
    return result


class SemanticEncoder:
    """一个进程内复用一个 ONNX 会话；构造失败统一抛 MODEL_UNAVAILABLE。"""

    def __init__(
        self,
        onnx_path: str | Path | None = None,
        tokenizer_path: str | Path | None = None,
        max_length: int | None = None,
        dimension: int | None = None,
        normalize: bool | None = None,
        intra_threads: int = 1,
    ) -> None:
        cfg = config.semantic_config()
        resolved_onnx, resolved_tok = config.semantic_paths()
        self.onnx_path = Path(onnx_path or resolved_onnx)
        self.tokenizer_path = Path(tokenizer_path or resolved_tok)
        self.max_length = int(max_length or cfg["max_length"])
        self.dimension = int(dimension or cfg["dimension"])
        self.normalize = cfg["normalize"] if normalize is None else bool(normalize)

        if not self.onnx_path.is_file():
            raise ModelUnavailable(f"语义模型不存在：{self.onnx_path}")
        if not self.tokenizer_path.is_file():
            raise ModelUnavailable(f"tokenizer 不存在：{self.tokenizer_path}")

        try:
            self._tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
            self._tokenizer.enable_truncation(max_length=self.max_length)
        except Exception as exc:
            raise ModelUnavailable("tokenizer 加载失败", {"reason": str(exc)}) from exc

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, int(intra_threads))
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            self._session = ort.InferenceSession(
                str(self.onnx_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise ModelUnavailable("ONNX 会话创建失败", {"reason": str(exc)}) from exc

        self._input_names = [item.name for item in self._session.get_inputs()]
        self._output_name = self._session.get_outputs()[0].name

    # ------------------------------------------------------------------ 内部

    def token_ids(self, text: str) -> list[int]:
        """只做 tokenize，用于金样例核对。"""
        if not isinstance(text, str) or not text.strip():
            raise InvalidPayload("text 为空")
        return list(self._tokenizer.encode(text).ids)

    def _forward(self, texts: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        encodings = self._tokenizer.encode_batch(texts)
        max_len = max(len(item.ids) for item in encodings)
        batch = len(texts)
        input_ids = np.zeros((batch, max_len), dtype=np.int64)
        attention_mask = np.zeros((batch, max_len), dtype=np.int64)
        token_type_ids = np.zeros((batch, max_len), dtype=np.int64)

        for row, encoding in enumerate(encodings):
            length = len(encoding.ids)
            input_ids[row, :length] = encoding.ids
            attention_mask[row, :length] = encoding.attention_mask
            type_ids = getattr(encoding, "type_ids", None)
            if type_ids:
                token_type_ids[row, :length] = type_ids

        feeds: dict[str, np.ndarray] = {}
        for name in self._input_names:
            if name == "input_ids":
                feeds[name] = input_ids
            elif name == "attention_mask":
                feeds[name] = attention_mask
            elif name == "token_type_ids":
                feeds[name] = token_type_ids
            else:
                raise InvalidPayload(
                    f"模型要求未登记的输入：{name}",
                    {"known_inputs": self._input_names},
                )

        hidden = self._session.run([self._output_name], feeds)[0]
        if hidden.ndim != 3 or hidden.shape[2] != self.dimension:
            raise InvalidPayload(
                "模型输出形状与 manifest 不一致",
                {"shape": list(hidden.shape), "expected_dimension": self.dimension},
            )
        return hidden, attention_mask, input_ids

    # ------------------------------------------------------------------ 公开

    def inspect(self, text: str) -> dict:
        """单句调试：返回 token、输入/输出形状，用于 S0 金样例取证。"""
        if not isinstance(text, str) or not text.strip():
            raise InvalidPayload("text 为空")
        hidden, mask, ids = self._forward([text])
        return {
            "text": text,
            "token_ids": ids[0].tolist(),
            "token_count": int(mask[0].sum()),
            "input_shape": list(ids.shape),
            "output_shape": list(hidden.shape),
            "output_dtype": str(hidden.dtype),
        }

    def encode(self, texts: list[str]) -> np.ndarray:
        """批量编码，返回 (n, dimension) 的 L2 归一化向量。"""
        if not isinstance(texts, list):
            raise InvalidPayload("texts 必须是数组")
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        for index, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise InvalidPayload(f"texts[{index}] 为空")

        hidden, attention_mask, _ = self._forward(texts)

        mask = attention_mask.astype(np.float32)[..., None]
        summed = (hidden.astype(np.float32) * mask).sum(axis=1)
        counts = np.maximum(mask.sum(axis=1), 1e-9)
        pooled = summed / counts

        if self.normalize:
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            pooled = pooled / np.maximum(norms, 1e-12)

        if not np.all(np.isfinite(pooled)):
            raise InvalidPayload("向量包含 NaN/Inf")
        return pooled.astype(np.float32)

    def encode_transcript(
        self,
        transcript: dict,
        keypoints: list[dict],
        use_word_pauses: bool = False,
        pause_ms: int = PAUSE_SPLIT_MS_DEFAULT,
        with_timing: bool = False,
    ) -> dict:
        """M3 完整契约：transcript + keypoints → embeddings。

        use_word_pauses=True 且段内带 words 时按停顿切句，否则按标点切句。
        with_timing=True 时在 answer_sentences 中附带 start_sample/end_sample
        （实验性字段，供切句效果核对，默认不输出以保持契约稳定）。
        """
        if not isinstance(transcript, dict):
            raise InvalidPayload("transcript 必须是对象")
        segments = transcript.get("segments")
        if not isinstance(segments, list) or not segments:
            raise InvalidPayload("transcript.segments 缺失或为空")

        sentence_items: list[dict] = []
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                raise InvalidPayload(f"transcript.segments[{index}] 不是对象")
            text = segment.get("text")
            if not isinstance(text, str):
                raise InvalidPayload(f"transcript.segments[{index}].text 不是字符串")

            words = segment.get("words")
            if use_word_pauses and isinstance(words, list) and words:
                items = split_sentences_by_pauses(words, pause_ms)
                if items:
                    sentence_items.extend(items)
                    continue

            for sentence in split_sentences(text):
                sentence_items.append(
                    {"text": sentence, "start_sample": None, "end_sample": None}
                )

        if not sentence_items:
            raise NoTranscript("transcript 未包含可编码的句子")

        if not isinstance(keypoints, list) or not keypoints:
            raise InvalidPayload("keypoints 缺失或为空")

        kp_texts: list[str] = []
        kp_ids: list[str] = []
        for index, item in enumerate(keypoints):
            if not isinstance(item, dict):
                raise InvalidPayload(f"keypoints[{index}] 不是对象")
            kp_id = item.get("keypoint_id")
            kp_text = item.get("text")
            if not isinstance(kp_id, str) or not kp_id:
                raise InvalidPayload(f"keypoints[{index}].keypoint_id 缺失")
            if kp_id in kp_ids:
                raise InvalidPayload(f"keypoint_id 重复：{kp_id}")
            if not isinstance(kp_text, str) or not kp_text.strip():
                raise InvalidPayload(f"keypoints[{index}].text 为空")
            kp_ids.append(kp_id)
            kp_texts.append(kp_text)

        sentence_vectors = self.encode([item["text"] for item in sentence_items])
        keypoint_vectors = self.encode(kp_texts)

        def _to_list(vector: np.ndarray) -> list[float]:
            return np.round(vector, VECTOR_ROUND_DIGITS).astype(float).tolist()

        answer_sentences = []
        for index, item in enumerate(sentence_items):
            entry = {
                "sentence_id": f"s{index + 1}",
                "text": item["text"],
                "vector": _to_list(sentence_vectors[index]),
            }
            if with_timing and item.get("start_sample") is not None:
                entry["start_sample"] = int(item["start_sample"])
                entry["end_sample"] = int(item["end_sample"])
            answer_sentences.append(entry)
        kp_entries = [
            {"keypoint_id": kp_ids[index], "vector": _to_list(keypoint_vectors[index])}
            for index in range(len(kp_ids))
        ]

        return {
            "embeddings": {
                "dimension": self.dimension,
                "answer_sentences": answer_sentences,
                "keypoints": kp_entries,
            }
        }
