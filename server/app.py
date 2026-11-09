"""S0 protocol probe with one documented fixed response."""
import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
MODULES = ("M1", "M2", "M3", "M4")
BODY_LIMIT = 4 * 1024 * 1024
IDENTITY = ("schema_version", "task_id", "attempt", "module_id", "plan_version", "model_version", "config_version")


def read_json(path):
    return json.loads(path.read_text("utf-8"))


def create():
    token = os.environ.get("SA_GATEWAY_TOKEN")
    if not token or not token.isascii() or any(character.isspace() for character in token):
        raise RuntimeError("Set SA_GATEWAY_TOKEN to an ASCII token without whitespace")
    fixture = read_json(CONTRACTS / "examples/ljx-s0-protocol.json")
    success = fixture["cases"][0]
    validator = Draft202012Validator(read_json(CONTRACTS / "module-request.schema.json"))
    identity_checks = {
        key: Draft202012Validator(validator.schema["properties"][key]) for key in IDENTITY
    }
    app = FastAPI(title="S0 protocol probe", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def health():
        return {
            "service_version": "0.0.1-s0",
            "schema_version": 1,
            "mode": "FIXED_PROTOCOL_FIXTURE",
            "modules": {
                name: {"available": False, "fixture_available": name == "M4"}
                for name in MODULES
            },
        }

    @app.post("/api/v1/modules/{module_id}/execute")
    async def execute(module_id: str, request: Request):
        data = {}

        def identity():
            return {
                key: data.get(key) if check.is_valid(data.get(key)) else None
                for key, check in identity_checks.items()
            }

        def error(status, code):
            return JSONResponse(status_code=status, content={
                **identity(), "executor": "REMOTE", "elapsed_ms": 0, "status": "ERROR",
                "error": {"code": code, "message": code.replace("_", " ").capitalize()},
            })

        authorization = request.headers.get("Authorization", "")
        if not secrets.compare_digest(authorization.encode("utf-8"), f"Bearer {token}".encode("ascii")):
            return error(401, "UNAUTHORIZED")
        if module_id not in MODULES:
            return error(404, "UNKNOWN_MODULE")
        content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return error(400, "INVALID_PAYLOAD")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > BODY_LIMIT:
                return error(413, "PAYLOAD_TOO_LARGE")
            body.extend(chunk)
        try:
            # Re-encoding rejects non-finite JSON constants and overflowing floats.
            parsed = json.loads(body.decode("utf-8"))
            json.dumps(parsed, allow_nan=False)
        except (ValueError, RecursionError, OverflowError):
            return error(400, "INVALID_PAYLOAD")
        if not isinstance(parsed, dict):
            return error(400, "INVALID_PAYLOAD")
        data = parsed
        version = data.get("schema_version")
        if type(version) is int and version != 1:
            return error(409, "VERSION_MISMATCH")
        if not validator.is_valid(data) or data["module_id"] != module_id:
            return error(400, "INVALID_PAYLOAD")
        if (data["model_version"], data["config_version"]) != (fixture["model_version"], fixture["config_version"]):
            return error(409, "VERSION_MISMATCH")
        if data["remaining_budget_ms"] == 0:
            return error(504, "DEADLINE_EXCEEDED")
        if module_id != "M4" or data["payload"] != success["request"]["payload"]:
            return error(503, "MODEL_UNAVAILABLE")
        return success["expected"]["body"] | identity()

    return app
