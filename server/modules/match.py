from server.gateway.protocol import embeddings


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
            index = max(range(len(scores)), key=scores.__getitem__)
            sentence = model["answer_sentences"][index]
            score = max(-1.0, min(1.0, scores[index]))
            result.append({"keypoint_id": keypoint["keypoint_id"], "score": score,
                           "covered": score >= self.threshold, "evidence_sentence_id": sentence["sentence_id"],
                           "evidence_text": sentence["text"]})
        return {"matches": result}
