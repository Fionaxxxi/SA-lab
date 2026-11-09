"""M4：要点覆盖匹配（余弦相似度）。

契约：
- 输入 embeddings（M3 输出）；阈值与小数位由调用方从 manifest/config_version 传入；
- 每个要点取相似度最高的句子；并列（浮点相等）取输入顺序最早的句子；
- covered = score >= threshold；
- 零向量、维度不一致、非有限值 → INVALID_PAYLOAD。
"""

from __future__ import annotations

import math

import numpy as np

from . import config
from .errors import InvalidPayload

_ACCEPTED_VECTOR_TYPES = (list, tuple)


def _as_vector(value, where: str) -> np.ndarray:
    if not isinstance(value, _ACCEPTED_VECTOR_TYPES):
        raise InvalidPayload(f"{where} 不是数组")
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise InvalidPayload(f"{where} 含非数值元素", {"reason": str(exc)}) from exc
    if vector.ndim != 1 or vector.size == 0:
        raise InvalidPayload(f"{where} 维度非法：shape={list(vector.shape)}")
    if not np.all(np.isfinite(vector)):
        raise InvalidPayload(f"{where} 含 NaN/Inf")
    return vector


def match(
    embeddings: dict,
    threshold: float | None = None,
    score_round_digits: int | None = None,
) -> dict:
    cfg = config.matching_config()
    threshold_value = cfg["threshold"] if threshold is None else float(threshold)
    digits = cfg["score_round_digits"] if score_round_digits is None else int(score_round_digits)

    if not isinstance(embeddings, dict):
        raise InvalidPayload("embeddings 必须是对象")
    dimension = embeddings.get("dimension")
    if not isinstance(dimension, int) or dimension <= 0:
        raise InvalidPayload("embeddings.dimension 缺失或非法")

    sentences = embeddings.get("answer_sentences")
    keypoints = embeddings.get("keypoints")
    if not isinstance(sentences, list) or not sentences:
        raise InvalidPayload("embeddings.answer_sentences 缺失或为空")
    if not isinstance(keypoints, list):
        raise InvalidPayload("embeddings.keypoints 缺失")

    sentence_ids: list[str] = []
    sentence_texts: list[str] = []
    sentence_matrix: list[np.ndarray] = []
    for index, item in enumerate(sentences):
        if not isinstance(item, dict):
            raise InvalidPayload(f"answer_sentences[{index}] 不是对象")
        sentence_id = item.get("sentence_id")
        if not isinstance(sentence_id, str) or not sentence_id:
            raise InvalidPayload(f"answer_sentences[{index}].sentence_id 缺失")
        if sentence_id in sentence_ids:
            raise InvalidPayload(f"sentence_id 重复：{sentence_id}")
        text = item.get("text")
        vector = _as_vector(item.get("vector"), f"answer_sentences[{index}].vector")
        if vector.size != dimension:
            raise InvalidPayload(
                f"answer_sentences[{index}] 向量维度与 dimension 不一致",
                {"expected": dimension, "actual": int(vector.size)},
            )
        if float(np.linalg.norm(vector)) == 0.0:
            raise InvalidPayload(f"answer_sentences[{index}] 是零向量")
        sentence_ids.append(sentence_id)
        sentence_texts.append(text if isinstance(text, str) else "")
        sentence_matrix.append(vector)

    sentence_stack = np.vstack(sentence_matrix)
    sentence_norms = np.linalg.norm(sentence_stack, axis=1, keepdims=True)
    sentence_unit = sentence_stack / np.maximum(sentence_norms, 1e-12)

    matches: list[dict] = []
    seen_keypoints: set[str] = set()

    for index, item in enumerate(keypoints):
        if not isinstance(item, dict):
            raise InvalidPayload(f"keypoints[{index}] 不是对象")
        keypoint_id = item.get("keypoint_id")
        if not isinstance(keypoint_id, str) or not keypoint_id:
            raise InvalidPayload(f"keypoints[{index}].keypoint_id 缺失")
        if keypoint_id in seen_keypoints:
            raise InvalidPayload(f"keypoint_id 重复：{keypoint_id}")
        seen_keypoints.add(keypoint_id)

        vector = _as_vector(item.get("vector"), f"keypoints[{index}].vector")
        if vector.size != dimension:
            raise InvalidPayload(
                f"keypoints[{index}] 向量维度与 dimension 不一致",
                {"expected": dimension, "actual": int(vector.size)},
            )
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            raise InvalidPayload(f"keypoints[{index}] 是零向量")

        unit = vector / norm
        scores = sentence_unit @ unit
        best_index = int(np.argmax(scores))  # argmax 返回第一个最大值 → 并列取最早句
        raw_score = float(scores[best_index])
        if not math.isfinite(raw_score):
            raise InvalidPayload(f"keypoint {keypoint_id} 相似度非有限值")

        matches.append(
            {
                "keypoint_id": keypoint_id,
                "score": round(raw_score, digits),
                "covered": bool(raw_score >= threshold_value),
                "evidence_sentence_id": sentence_ids[best_index],
                "evidence_text": sentence_texts[best_index],
            }
        )

    return {"matches": matches}


def coverage_summary(matches: list[dict]) -> dict:
    """便于实验统计的派生指标；不改变契约输出。"""
    total = len(matches)
    covered = sum(1 for item in matches if item.get("covered"))
    return {
        "keypoints_total": total,
        "keypoints_covered": covered,
        "coverage_rate": (covered / total) if total else 0.0,
    }
