import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from server.app import create
from server.modules.integration import load_registry


class ModelRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = {'model_version': 'test-model', 'config_version': 'test-rules',
            'vosk_directory': 'weights/vosk', 'config': {'dimension': 384, 'max_length': 128,
            'pooling': 'mean', 'normalize': 'L2', 'vad_threshold': 0.5, 'match_threshold': 0.8},
            'artifacts': {}}
        for key, name in [('vad', 'vad.onnx'), ('semantic', 'semantic.onnx'),
                          ('tokenizer', 'tokenizer.model'), ('vosk_file_1', 'vosk/am/final.mdl')]:
            path = self.root / 'weights' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'registry-test-fixture')
            self.manifest['artifacts'][key] = {'path': path.relative_to(self.root).as_posix(),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.publish()
        for name in ('Vad', 'Asr', 'Semantic'):
            context = patch('server.modules.integration.' + name)
            self.addCleanup(context.stop)
            context.start().return_value = lambda payload: payload

    def publish(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest), 'utf-8')

    def test_independent_registration_and_hash_failure(self):
        _, handlers, errors = load_registry(self.root)
        self.assertEqual(set(handlers), {'M1', 'M2', 'M3', 'M4'})
        self.assertFalse(errors)
        (self.root / 'weights/semantic.onnx').write_bytes(b'tampered-fixture')
        _, handlers, errors = load_registry(self.root)
        self.assertEqual(set(handlers), {'M1', 'M2', 'M4'})
        self.assertEqual(set(errors), {'M3'})

    def test_deleted_and_unlisted_vosk_files_are_rejected(self):
        (self.root / 'weights/vosk/extra').write_bytes(b'not-in-manifest')
        _, handlers, errors = load_registry(self.root)
        self.assertNotIn('M2', handlers)
        self.assertEqual(set(errors), {'M2'})
        (self.root / 'weights/vosk/extra').unlink()
        (self.root / 'weights/vosk/am/final.mdl').unlink()
        _, handlers, errors = load_registry(self.root)
        self.assertNotIn('M2', handlers)
        self.assertEqual(set(errors), {'M2'})

    def test_outside_path_and_invalid_config(self):
        self.manifest['artifacts']['tokenizer']['path'] = '../outside.model'
        self.publish()
        _, handlers, errors = load_registry(self.root)
        self.assertEqual(set(errors), {'M3'})
        self.assertIn('M2', handlers)
        self.manifest['config']['vad_threshold'] = float('nan')
        self.publish()
        manifest, handlers, errors = load_registry(self.root)
        self.assertIsNone(manifest)
        self.assertFalse(handlers)
        self.assertEqual(len(errors), 4)


class MissingModelServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_factory_without_manifest_still_serves_health_and_503(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            'SA_GATEWAY_TOKEN': 'test-token', 'SA_DEMO': '0', 'SA_MODEL_ROOT': root,
            'SA_MODULE_FACTORY': 'server.modules.integration:create_handlers',
            'SA_MODEL_VERSION': 'unconfigured', 'SA_CONFIG_VERSION': 'unconfigured'}):
            app = create()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.get('/healthz')
                self.assertEqual(response.status_code, 200)
                self.assertTrue(all(not v['available'] for v in response.json()['modules'].values()))
                request = {'schema_version': 1, 'task_id': 'missing-model', 'attempt': 1,
                    'module_id': 'M1', 'plan_version': 'test-plan', 'model_version': 'unconfigured',
                    'config_version': 'unconfigured', 'remaining_budget_ms': 2000,
                    'payload': {'audio': {'sample_rate_hz': 16000, 'channels': 1, 'sample_format': 's16le',
                        'sample_count': 1, 'pcm_b64': base64.b64encode(b'\0\0').decode()}}}
                response = await client.post('/api/v1/modules/M1/execute', json=request,
                    headers={'Authorization': 'Bearer test-token'})
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.json()['error']['code'], 'MODEL_UNAVAILABLE')
