"""Single-worker LAN gateway. Each request routes to exactly one module."""
import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from time import monotonic
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.gateway.protocol import (
    HTTP_STATUS, MAX_BODY, MODULES, ProtocolError, check_output, check_request,
    envelope, parse_json, require,
)

SERVICE_VERSION = "0.1.0-s3"
CACHE_TTL_SECONDS = 60
MAX_CACHE_ENTRIES = 128
MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_RUNNING = 4
MAX_EXECUTION_MS = 30_000
Handler = Callable[[dict], dict]


@dataclass
class Entry:
    digest: bytes
    task: asyncio.Task | None = None
    result: tuple[int, dict] | None = None
    expires: float = 0
    result_size: int = 0


def elapsed(start):
    return max(0, int((monotonic() - start) * 1000))


def error(data, code, message, duration=0):
    return HTTP_STATUS[code], {
        **envelope(data), "status": "ERROR", "executor": "REMOTE",
        "elapsed_ms": duration, "error": {"code": code, "message": message},
    }


def reply(result):
    status, body = result
    return JSONResponse(status_code=status, content=body)


async def read_body(request):
    length = request.headers.get("content-length")
    if length is not None:
        require(length.isdecimal() and len(length) <= 20, "Invalid Content-Length")
        if int(length) > MAX_BODY:
            raise ProtocolError("PAYLOAD_TOO_LARGE", "Maximum body size is 4 MiB")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise ProtocolError("PAYLOAD_TOO_LARGE", "Maximum body size is 4 MiB")
        body.extend(chunk)
    return body


def create_app(*, token, model_version, config_version, dimension, handlers=None,
               demo=False, cache_ttl=CACHE_TTL_SECONDS):
    if not token or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("An ASCII bearer token without whitespace is required")
    handlers = dict(handlers or {})
    if not set(handlers).issubset(MODULES) or not all(map(callable, handlers.values())):
        raise ValueError("Invalid gateway module registry")
    app = FastAPI(title="Interview feedback gateway", docs_url=None, redoc_url=None, openapi_url=None)
    cache: dict[tuple, Entry] = {}
    expected_token = f"Bearer {token}".encode("ascii")

    @app.get("/healthz")
    async def health():
        return {
            "service_version": SERVICE_VERSION, "schema_version": 1,
            "model_version": model_version, "config_version": config_version, "demo": demo,
            "modules": {module: {"available": module in handlers} for module in MODULES},
        }

    def evict_expired(now):
        for key, entry in list(cache.items()):
            if entry.task is None and entry.expires <= now:
                del cache[key]

    async def execute(entry, data, handler, budget_end):
        module_start = monotonic()
        worker = asyncio.create_task(asyncio.to_thread(handler, data["payload"]))
        try:
            remaining = max(0, budget_end - monotonic())
            output = await asyncio.wait_for(asyncio.shield(worker), remaining)
            body = {
                **envelope(data), "status": "OK", "executor": "REMOTE",
                "elapsed_ms": elapsed(module_start), "output": output,
            }
            try:
                check_output(body, data, dimension)
            except ProtocolError as exc:
                raise RuntimeError("Invalid adapter result") from exc
            encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) > MAX_BODY:
                result = error(data, "PAYLOAD_TOO_LARGE", "Module output exceeds 4 MiB", elapsed(module_start))
            elif monotonic() >= budget_end:
                result = error(data, "DEADLINE_EXCEEDED", "Execution budget expired", elapsed(module_start))
            else:
                result = 200, body
        except TimeoutError:
            result = error(data, "DEADLINE_EXCEEDED", "Execution budget expired", elapsed(module_start))
        except ProtocolError as exc:
            # Adapter exceptions may expose model paths or transcript text.
            if exc.code in ("NO_SPEECH", "NO_TRANSCRIPT", "MODEL_UNAVAILABLE", "BUSY", "INVALID_PAYLOAD"):
                result = error(data, exc.code, "Module could not process input", elapsed(module_start))
            else:
                result = error(data, "INTERNAL_ERROR", "Module failed", elapsed(module_start))
        except Exception:
            result = error(data, "INTERNAL_ERROR", "Module failed", elapsed(module_start))

        if not worker.done():
            # The HTTP caller can leave on deadline. Keep the key in progress
            # and the worker slot occupied until the non-interruptible handler exits.
            try:
                await worker
            except Exception:
                pass
        entry.result = result
        entry.result_size = len(json.dumps(result[1], ensure_ascii=False).encode("utf-8"))
        entry.expires = monotonic() + cache_ttl
        entry.task = None

    @app.post("/api/v1/modules/{module_id}/execute")
    async def dispatch(module_id: str, request: Request):
        received = monotonic()
        data = {}
        try:
            auth = request.headers.get("authorization", "").encode("latin-1")
            if not hmac.compare_digest(auth, expected_token):
                raise ProtocolError("UNAUTHORIZED", "Invalid bearer credential")
            if module_id not in MODULES:
                raise ProtocolError("UNKNOWN_MODULE", "Unknown module")
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            require(content_type == "application/json", "Expected application/json")
            try:
                raw = await asyncio.wait_for(read_body(request), MAX_EXECUTION_MS / 1000)
            except TimeoutError:
                raise ProtocolError("DEADLINE_EXCEEDED", "Request body read timed out") from None
            parsed = parse_json(raw)
            require(isinstance(parsed, dict), "Expected a JSON object")
            data = parsed
            check_request(data, module_id, model_version, config_version, dimension)
            now = monotonic()
            evict_expired(now)
            key = tuple(data[k] for k in ("task_id", "attempt", "plan_version", "module_id"))
            digest = hashlib.sha256(json.dumps(
                data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
            ).encode("ascii")).digest()
            entry = cache.get(key)
            if entry is not None:
                if entry.digest != digest:
                    raise ProtocolError("REQUEST_CONFLICT", "Same key with different request")
                if entry.result is None:
                    raise ProtocolError("IN_PROGRESS", "Request already running")
                return reply(entry.result)

            budget_end = received + min(data["remaining_budget_ms"], MAX_EXECUTION_MS) / 1000
            if budget_end <= now:
                raise ProtocolError("DEADLINE_EXCEEDED", "Execution budget expired")
            if module_id not in handlers:
                raise ProtocolError("MODEL_UNAVAILABLE", "Module is not available")
            if (
                sum(entry.task is not None for entry in cache.values()) >= MAX_RUNNING
                or len(cache) >= MAX_CACHE_ENTRIES
                or sum(entry.result_size if entry.result is not None else MAX_BODY for entry in cache.values())
                    + MAX_BODY > MAX_CACHE_BYTES
            ):
                raise ProtocolError("BUSY", "Gateway capacity reached")
            entry = Entry(digest)
            cache[key] = entry
            entry.task = asyncio.create_task(execute(entry, data, handlers[module_id], budget_end))
            try:
                await asyncio.wait_for(asyncio.shield(entry.task), max(0, budget_end - monotonic()))
            except TimeoutError:
                raise ProtocolError("DEADLINE_EXCEEDED", "Execution budget expired") from None
            return reply(entry.result)
        except ProtocolError as exc:
            return reply(error(data, exc.code, str(exc), elapsed(received)))
        except (ValueError, UnicodeError, RecursionError, OverflowError):
            return reply(error(data, "INVALID_PAYLOAD", "Invalid UTF-8 JSON body", elapsed(received)))

    return app
