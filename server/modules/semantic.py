import re
import numpy as np
import onnxruntime as ort
import sentencepiece as spm
from server.gateway.protocol import ProtocolError
from server.modules.match import NEGATED_ACTION


CLAUSE_START = re.compile(r"然后|接下来|之后|结束后|活动结束|同时|现场|不过|但是|但我|但不|也不|不会|不做|再和|再去|再请|最后|每天|每周")


def answer_clauses(text):
    """Create spoken clauses and bounded windows without cutting negation cues away."""
    pieces = []
    for sentence in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        starts = [0] + [match.start() for match in CLAUSE_START.finditer(sentence) if match.start()]
        parts = [sentence[left:right].strip() for left, right in zip(starts, starts[1:] + [len(sentence)])]
        pieces.extend(part for part in parts if len(part) >= 5)
    clauses = pieces or ([text.strip()] if text.strip() else [])
    passages = []
    for clause in clauses:
        passages.append(clause)
        if len(clause) > 28 and not NEGATED_ACTION.search(clause):
            passages.extend(clause[start:start + 28] for start in range(0, len(clause), 14)
                           if len(clause[start:start + 28]) >= 8)
    return list(dict.fromkeys(passages))


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
        sentences = answer_clauses(payload["transcript"]["full_text"])
        if not sentences:
            raise ProtocolError("NO_TRANSCRIPT", "No sentences")
        return {"embeddings": {
            "dimension": self.dimension,
            "answer_sentences": [{"sentence_id": f"s{i+1}", "text": text, "vector": self.vector(text)} for i, text in enumerate(sentences)],
            "keypoints": [{"keypoint_id": x["keypoint_id"], "text": x["text"], "vector": self.vector(x["text"])}
                          for x in payload["keypoints"]],
        }}
