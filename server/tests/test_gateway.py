import asyncio
import copy
import hashlib
import json
import threading
import unittest
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

from server.gateway.fixtures import demo_handlers
from server.gateway.protocol import MAX_BODY, VALIDATORS
from server.gateway.service import create_app

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"
FIXTURE = json.loads((EXAMPLES / "ljx-http-cases.json").read_text("utf-8"))
REQUEST = FIXTURE["cases"][0]["request"]
HEADERS = {"Authorization": "Bearer fixture-token", "Content-Type": "application/json"}
URL = "/api/v1/modules/M4/execute"


def gateway(**kwargs):
    return create_app(
        token="fixture-token", model_version="modelset-demo", config_version="rules-demo",
        dimension=2, **kwargs,
    )


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture")


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_fixtures_and_plans(self):
        for validator in VALIDATORS.values():
            Draft202012Validator.check_schema(validator.schema)
        for plan in json.loads((EXAMPLES / "ljx-execution-plans.json").read_text("utf-8")):
            VALIDATORS["execution-plan"].validate(plan)
        VALIDATORS["module-request"].validate(REQUEST)
        encoded = json.dumps(REQUEST, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), FIXTURE["input_sha256"])
        first = None
        async with client(gateway(handlers=demo_handlers(), demo=True)) as http:
            for case in FIXTURE["cases"]:
                with self.subTest(case=case["id"]):
                    expected = case["expected"]
                    if "request" in case:
                        response = await http.post(URL, json=case["request"], headers=HEADERS)
                    else:
                        recipe = case["body_recipe"]
                        response = await http.post(URL, content=recipe["fill"].encode() * recipe["utf8_bytes"],
                                                   headers=HEADERS)
                    self.assertEqual(response.status_code, expected["http_status"], response.text)
                    body = response.json()
                    VALIDATORS["module-result"].validate(body)
                    if "code" in expected:
                        self.assertEqual(body["error"]["code"], expected["code"])
                    if "body" in expected:
                        first = body
                        self.assertEqual(body | {"elapsed_ms": 0}, expected["body"])
                    if expected.get("cached"):
                        self.assertEqual(body, first)

    async def test_health_missing_models_auth_path_and_malformed(self):
        async with client(gateway()) as http:
            health = (await http.get("/healthz")).json()
            self.assertFalse(health["demo"])
            self.assertTrue(all(not item["available"] for item in health["modules"].values()))
            for path, headers, request, status, code in [
                (URL, {}, REQUEST, 401, "UNAUTHORIZED"),
                ("/api/v1/modules/M0/execute", HEADERS, REQUEST, 404, "UNKNOWN_MODULE"),
                ("/api/v1/modules/M2/execute", HEADERS, REQUEST, 400, "INVALID_PAYLOAD"),
                (URL, HEADERS, REQUEST, 503, "MODEL_UNAVAILABLE"),
                (URL, HEADERS, REQUEST | {"model_version": "old"}, 409, "VERSION_MISMATCH"),
            ]:
                with self.subTest(code=code):
                    response = await http.post(path, headers=headers, json=request)
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.json()["error"]["code"], code)
            for body in (b"\xff", b"{", b'{"x":NaN}', b'{"x":1e999}', b'{"x":1,"x":2}'):
                self.assertEqual((await http.post(URL, headers=HEADERS, content=body)).status_code, 400)

    async def test_data_boundaries(self):
        async def oversized_stream():
            yield b" " * MAX_BODY
            yield b" "
        async with client(gateway(handlers=demo_handlers())) as http:
            self.assertEqual((await http.post(URL, headers=HEADERS, content=oversized_stream())).status_code, 413)
            bad_vector = copy.deepcopy(REQUEST["payload"])
            bad_vector["embeddings"]["answer_sentences"][0]["vector"] = [0, 0]
            for module, payload in [
                ("M1", {"audio": {"sample_rate_hz": 16000, "channels": 1, "sample_format": "s16le",
                                  "sample_count": 960001, "pcm_b64": "AQI="}}),
                ("M1", {"audio": {"sample_rate_hz": 16000, "channels": 1, "sample_format": "s16le",
                                  "sample_count": 2, "pcm_b64": "AQI="}}),
                ("M2", {"segments": [
                    {"segment_id": "s1", "start_sample": 0, "end_sample": 1, "pcm_b64": "AQI="},
                    {"segment_id": "s2", "start_sample": 0, "end_sample": 1, "pcm_b64": "AQI="}]}),
                ("M4", bad_vector),
            ]:
                request = REQUEST | {"module_id": module, "payload": payload}
                response = await http.post(f"/api/v1/modules/{module}/execute", headers=HEADERS, json=request)
                self.assertEqual(response.status_code, 400, response.text)

    async def test_in_progress_conflict_and_single_execution(self):
        started, release = threading.Event(), threading.Event()
        calls = 0

        def block(payload):
            nonlocal calls
            calls += 1
            started.set()
            release.wait(3)
            return demo_handlers()["M4"](payload)

        async with client(gateway(handlers={"M4": block})) as http:
            first = asyncio.create_task(http.post(URL, headers=HEADERS, json=REQUEST))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                retry = await http.post(URL, headers=HEADERS, json=REQUEST)
                conflict = await http.post(URL, headers=HEADERS, json=REQUEST | {"remaining_budget_ms": 1999})
                self.assertEqual(retry.json()["error"]["code"], "IN_PROGRESS")
                self.assertEqual(conflict.json()["error"]["code"], "REQUEST_CONFLICT")
            finally:
                release.set()
            self.assertEqual((await first).status_code, 200)
            self.assertEqual((await http.post(URL, headers=HEADERS, json=REQUEST)).status_code, 200)
            self.assertEqual(calls, 1)

    async def test_timeout_and_cache_expiry(self):
        started, release = threading.Event(), threading.Event()
        calls = 0

        def block(payload):
            nonlocal calls
            calls += 1
            started.set()
            release.wait(3)
            return demo_handlers()["M4"](payload)

        request = REQUEST | {"remaining_budget_ms": 150}
        async with client(gateway(handlers={"M4": block}, cache_ttl=0.1)) as http:
            first = asyncio.create_task(http.post(URL, headers=HEADERS, json=request))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                self.assertEqual((await first).status_code, 504)
                self.assertEqual((await http.post(URL, headers=HEADERS, json=request)).status_code, 409)
            finally:
                release.set()
            for _ in range(40):
                retry = await http.post(URL, headers=HEADERS, json=request)
                if retry.status_code != 409:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(retry.status_code, 504)
            self.assertEqual(calls, 1)
            await asyncio.sleep(0.11)
            self.assertEqual((await http.post(URL, headers=HEADERS, json=request)).status_code, 200)
            self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
