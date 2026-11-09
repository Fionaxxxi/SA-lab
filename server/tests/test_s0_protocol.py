import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from server.app import create

ROOT = Path(__file__).resolve().parents[2] / "contracts"
FIXTURE = json.loads((ROOT / "examples/ljx-s0-protocol.json").read_text("utf-8"))
URL = "/api/v1/modules/M4/execute"
HEADERS = {"Authorization": "Bearer s0-test"}


class S0ProtocolTests(unittest.TestCase):
    def setUp(self):
        with patch.dict("os.environ", {"SA_GATEWAY_TOKEN": "s0-test"}):
            self.client = TestClient(create())

    def test_schemas_and_fixture_hash(self):
        for name in ("module-request", "module-result", "execution-plan"):
            schema = json.loads((ROOT / f"{name}.schema.json").read_text("utf-8"))
            Draft202012Validator.check_schema(schema)
        request = FIXTURE["cases"][0]["request"]
        raw = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FIXTURE["input_sha256"])

    def test_fixed_success_and_error_envelopes(self):
        schema = json.loads((ROOT / "module-result.schema.json").read_text("utf-8"))
        for case in FIXTURE["cases"]:
            with self.subTest(case=case["id"]):
                response = self.client.post(URL, headers=HEADERS, json=case["request"])
                expected = case["expected"]
                self.assertEqual(response.status_code, expected["http_status"])
                body = response.json()
                Draft202012Validator(schema).validate(body)
                if "body" in expected:
                    self.assertEqual(body, expected["body"])
                else:
                    self.assertEqual(body["error"]["code"], expected["code"])

    def test_health_availability_and_access_boundaries(self):
        health = self.client.get("/healthz").json()
        self.assertEqual(health["mode"], "FIXED_PROTOCOL_FIXTURE")
        self.assertTrue(all(not module["available"] for module in health["modules"].values()))
        self.assertEqual([name for name, value in health["modules"].items() if value["fixture_available"]], ["M4"])
        request = FIXTURE["cases"][0]["request"]
        self.assertEqual(self.client.post(URL, json=request).status_code, 401)
        self.assertEqual(self.client.post(URL.replace("M4", "M0"), json=request, headers=HEADERS).status_code, 404)
        payload = request["payload"] | {"embeddings": request["payload"]["embeddings"] | {
            "keypoints": [{"keypoint_id": "other", "vector": [1, 0]}],
        }}
        response = self.client.post(URL, json=request | {"payload": payload}, headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "MODEL_UNAVAILABLE")
