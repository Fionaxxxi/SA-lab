"""Synthetic protocol fixtures. Never loaded in real module mode."""
from server.gateway.protocol import ProtocolError

TEXT = "先调查居民需求"


def vad(payload):
    audio = payload["audio"]
    if set(audio["pcm_b64"]) <= {"A", "="}:
        raise ProtocolError("NO_SPEECH", "Synthetic silent input")
    return {"segments": [{
        "segment_id": "seg1", "start_sample": 0, "end_sample": audio["sample_count"],
        "pcm_b64": audio["pcm_b64"],
    }]}


def asr(payload):
    segments = [
        {key: value for key, value in segment.items() if key != "pcm_b64"}
        | {"text": TEXT if index == 0 else ""}
        for index, segment in enumerate(payload["segments"])
    ]
    return {"transcript": {"full_text": TEXT, "segments": segments}}


def encode(payload):
    return {"embeddings": {
        "dimension": 2,
        "answer_sentences": [{"sentence_id": "s1", "text": TEXT, "vector": [1.0, 0.0]}],
        "keypoints": [{"keypoint_id": k["keypoint_id"], "vector": [1.0, 0.0]}
                      for k in payload["keypoints"]],
    }}


def match(payload):
    model = payload["embeddings"]
    sentence = model["answer_sentences"][0]
    return {"matches": [
        {"keypoint_id": k["keypoint_id"], "score": 1.0, "covered": True,
         "evidence_sentence_id": sentence["sentence_id"], "evidence_text": sentence["text"]}
        for k in model["keypoints"]
    ]}


def demo_handlers():
    return {"M1": vad, "M2": asr, "M3": encode, "M4": match}
