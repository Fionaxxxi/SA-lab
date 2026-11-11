"""HTTP v1 schema and checks involving multiple fields."""
import base64
import binascii
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

MODULES = ("M1", "M2", "M3", "M4")
IDENTITY = (
    "schema_version", "task_id", "attempt", "module_id", "plan_version",
    "model_version", "config_version",
)
MAX_BODY = 4 * 1024 * 1024
MAX_SAMPLES = 60 * 16000
SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "contracts"
HTTP_STATUS = {
  "INVALID_PAYLOAD": 400,
  "UNAUTHORIZED": 401,
  "UNKNOWN_MODULE": 404,
  "VERSION_MISMATCH": 409,
  "IN_PROGRESS": 409,
  "REQUEST_CONFLICT": 409,
  "PAYLOAD_TOO_LARGE": 413,
  "NO_SPEECH": 422,
  "NO_TRANSCRIPT": 422,
  "INTERNAL_ERROR": 500,
  "MODEL_UNAVAILABLE": 503,
  "BUSY": 503,
  "DEADLINE_EXCEEDED": 504
}
VALIDATORS = {
    name: Draft202012Validator(json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text("utf-8")))
    for name in ("module-request", "module-result", "execution-plan")
}


class ProtocolError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, message):
    if not condition:
        raise ProtocolError("INVALID_PAYLOAD", message)


def parse_json(data):
    def unique(pairs):
        result = dict(pairs)
        require(len(result) == len(pairs), "Duplicate JSON field")
        return result

    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), "Non-finite number")
        return number

    def invalid_constant(value):
        raise ProtocolError("INVALID_PAYLOAD", "Non-finite number")

    return json.loads(
        data.decode("utf-8"), object_pairs_hook=unique,
        parse_float=finite_float, parse_constant=invalid_constant,
    )


def check_schema(name, document):
    error = next(VALIDATORS[name].iter_errors(document), None)
    if error is not None:
        location = ".".join(map(str, error.absolute_path)) or "$"
        raise ProtocolError("INVALID_PAYLOAD", f"Invalid fields at {location}")


def pcm_length(encoded, samples):
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ProtocolError("INVALID_PAYLOAD", "Invalid PCM Base64") from None
    require(len(data) == samples * 2, "PCM length does not match sample count")


def spans(segments, *, pcm=False, limit=MAX_SAMPLES):
    unique_ids(segments, "segment_id")
    previous_end = 0
    for seg in segments:
        start, end = seg["start_sample"], seg["end_sample"]
        require(previous_end <= start < end <= limit, "Unordered, overlapping or out-of-range segment")
        if pcm:
            pcm_length(seg["pcm_b64"], end - start)
        previous_end = end


def unique_ids(items, field):
    require(len({item[field] for item in items}) == len(items), f"Duplicate {field}")


def transcript(value):
    segments = value["segments"]
    spans(segments)
    expected = "\n".join(segment["text"].strip() for segment in segments if segment["text"].strip())
    require(bool(expected) and expected == value["full_text"], "Invalid full_text or segment join")


def embeddings(value, dimension):
    require(value["dimension"] == dimension, "Unexpected vector dimension")
    for group, field in (("answer_sentences", "sentence_id"), ("keypoints", "keypoint_id")):
        unique_ids(value[group], field)
        for item in value[group]:
            vector = item["vector"]
            require(
                len(vector) == dimension
                and all(-1.00001 <= x <= 1.00001 for x in vector)
                and abs(math.hypot(*vector) - 1.0) <= 1e-5,
                "Expected a finite L2-normalized vector",
            )


def check_request(data, module, model_version, config_version, dimension):
    if type(data.get("schema_version")) is int and data["schema_version"] != 1:
        raise ProtocolError("VERSION_MISMATCH", "Unsupported schema version")
    check_schema("module-request", data)
    require(data["module_id"] == module, "Path and body module differ")
    if (data["model_version"], data["config_version"]) != (model_version, config_version):
        raise ProtocolError("VERSION_MISMATCH", "Unsupported model or configuration")
    payload = data["payload"]
    if module == "M1":
        audio = payload["audio"]
        pcm_length(audio["pcm_b64"], audio["sample_count"])
    elif module == "M2":
        spans(payload["segments"], pcm=True)
    elif module == "M3":
        transcript(payload["transcript"])
        unique_ids(payload["keypoints"], "keypoint_id")
    else:
        embeddings(payload["embeddings"], dimension)


def check_output(data, request, dimension):
    check_schema("module-result", data)
    if data["status"] != "OK":
        return
    source, output = request["payload"], data["output"]
    if data["module_id"] == "M1":
        spans(output["segments"], pcm=True, limit=source["audio"]["sample_count"])
    elif data["module_id"] == "M2":
        transcript(output["transcript"])
        fields = ("segment_id", "start_sample", "end_sample")
        before = [tuple(item[key] for key in fields) for item in source["segments"]]
        after = [tuple(item[key] for key in fields) for item in output["transcript"]["segments"]]
        require(before == after, "Transcript must preserve all segment coordinates")
    elif data["module_id"] == "M3":
        embeddings(output["embeddings"], dimension)
        require(
            [k["keypoint_id"] for k in output["embeddings"]["keypoints"]]
            == [k["keypoint_id"] for k in source["keypoints"]],
            "Encoder changed keypoint identities",
        )
    else:
        model = source["embeddings"]
        sentences = {item["sentence_id"]: item["text"] for item in model["answer_sentences"]}
        matches = output["matches"]
        require(
            [k["keypoint_id"] for k in matches] == [k["keypoint_id"] for k in model["keypoints"]]
            and all(sentences.get(item["evidence_sentence_id"]) == item["evidence_text"] for item in matches),
            "Matches must preserve keypoint identities and refer to a source sentence",
        )


def envelope(data):
    result = {}
    properties = VALIDATORS["module-request"].schema["properties"]
    for key in IDENTITY:
        value = data.get(key)
        result[key] = value if Draft202012Validator(properties[key]).is_valid(value) else None
    return result
