import re

from server.gateway.protocol import embeddings


NEGATED_ACTION = re.compile(r"不打算|不准备|无需|不用|不做|不考虑|不安排|不需要|不会(?:做|再|去|提供|回访|调整|记录|设置|组织|提醒)")


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
            scores = [sum(a * b for a, b in zip(keypoint["vector"], sentence["vector"]))
                      for sentence in model["answer_sentences"]]
            eligible = [i for i, sentence in enumerate(model["answer_sentences"])
                        if not NEGATED_ACTION.search(sentence["text"])]
            index = max(eligible or range(len(scores)), key=scores.__getitem__)
            sentence = model["answer_sentences"][index]
            score = max(-1.0, min(1.0, scores[index]))
            result.append({"keypoint_id": keypoint["keypoint_id"], "score": score,
                           "covered": bool(eligible) and score >= self.threshold, "evidence_sentence_id": sentence["sentence_id"],
                           "evidence_text": sentence["text"]})
        return {"matches": result}
