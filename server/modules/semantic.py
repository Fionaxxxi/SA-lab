import re
import numpy as np
import onnxruntime as ort
import sentencepiece as spm
from server.gateway.protocol import ProtocolError


class Semantic:
    def __init__(self, model, tokenizer, dimension=384, max_length=128):
        self.session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        self.tokenizer = spm.SentencePieceProcessor(model_file=str(tokenizer))
        self.dimension, self.max_length = dimension, max_length

    def tokens(self, text):
        pieces = self.tokenizer.encode(text, out_type=int)
        return [[0] + [3 if x == 0 else x + 1 for x in pieces[i:i + self.max_length - 2]] + [2]
                for i in range(0, max(1, len(pieces)), self.max_length - 2)]

    def vector(self, text):
        vectors, weights = [], []
        for tokens in self.tokens(text):
            ids = np.asarray([tokens], dtype=np.int64)
            inputs = {"input_ids": ids, "attention_mask": np.ones_like(ids), "token_type_ids": np.zeros_like(ids)}
            output = self.session.run(None, {item.name: inputs[item.name] for item in self.session.get_inputs()})[0]
            vectors.append(output.mean(axis=1)[0] if output.ndim == 3 else output[0])
            weights.append(max(1, len(tokens) - 2))
        vector = np.average(vectors, axis=0, weights=weights)
        norm = np.linalg.norm(vector)
        if vector.shape != (self.dimension,) or not np.isfinite(vector).all() or norm == 0:
            raise ProtocolError("INVALID_PAYLOAD", "Invalid vector")
        return (vector / norm).tolist()

    def __call__(self, payload):
        sentences = [x.strip() for x in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", payload["transcript"]["full_text"]) if x.strip()]
        if not sentences:
            raise ProtocolError("NO_TRANSCRIPT", "No sentences")
        return {"embeddings": {
            "dimension": self.dimension,
            "answer_sentences": [{"sentence_id": f"s{i+1}", "text": text, "vector": self.vector(text)} for i, text in enumerate(sentences)],
            "keypoints": [{"keypoint_id": x["keypoint_id"], "vector": self.vector(x["text"])} for x in payload["keypoints"]],
        }}
