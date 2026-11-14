import re

from server.gateway.protocol import embeddings


NEGATED_ACTION = re.compile(r"不打算|不准备|无需|不用|不做|不考虑|不安排|不需要|不会(?:做|再|去|提供|回访|调整|记录|设置|组织|提醒)")

# 取依据句的分数容差带。短句在余弦空间里天然占优：句中概念越少，单个概念在归一化向量里的
# 权重越高，于是短句常以微弱优势压过长句。分数与覆盖判定仍用最高分句，只把“依据”换成
# 分数相近、且与要点原文重合更长的句子；找不到合格候选就退回最高分句。
EVIDENCE_BAND = 0.85
EVIDENCE_MIN_OVERLAP = 2


def longest_common_substring(left, right):
    """最长公共子串长度，滚动数组实现。"""
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for index in range(1, len(left) + 1):
        current = [0] * (len(right) + 1)
        char = left[index - 1]
        for other in range(1, len(right) + 1):
            if char == right[other - 1]:
                current[other] = previous[other - 1] + 1
                if current[other] > best:
                    best = current[other]
        previous = current
    return best


class Matcher:
    def __init__(self, dimension, threshold):
        if not 0 <= threshold <= 1:
            raise ValueError("Invalid threshold")
        self.dimension, self.threshold = dimension, threshold

    def __call__(self, payload):
        model = payload["embeddings"]
        embeddings(model, self.dimension)
        result = []
        for keypoint in model["keypoints"]:
            sentences = model["answer_sentences"]
            scores = [sum(a * b for a, b in zip(keypoint["vector"], sentence["vector"]))
                      for sentence in sentences]
            eligible = [i for i, sentence in enumerate(sentences)
                        if not NEGATED_ACTION.search(sentence["text"])]
            pool = eligible or list(range(len(scores)))
            index = max(pool, key=scores.__getitem__)
            score = max(-1.0, min(1.0, scores[index]))
            band = [i for i in pool if scores[i] >= scores[index] * EVIDENCE_BAND]
            usable = [(longest_common_substring(sentences[i]["text"], keypoint["text"]), i) for i in band]
            usable = [item for item in usable if item[0] >= EVIDENCE_MIN_OVERLAP]
            evidence = max(usable, key=lambda item: (item[0], scores[item[1]]))[1] if usable else index
            sentence = sentences[evidence]
            result.append({"keypoint_id": keypoint["keypoint_id"], "score": score,
                           "covered": bool(eligible) and score >= self.threshold,
                           "evidence_sentence_id": sentence["sentence_id"], "evidence_text": sentence["text"]})
        return {"matches": result}
