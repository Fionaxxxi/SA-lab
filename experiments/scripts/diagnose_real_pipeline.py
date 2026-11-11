"""Diagnostic with real models and a synthetic WAV; never a human evaluation run."""
import argparse
import asyncio
import base64
import json
import math
import os
from pathlib import Path
import secrets
import socket
import threading
import time
import wave
import httpx
import uvicorn
from server.modules.integration import create_handlers
from server.gateway.service import create_app


def equivalent(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=0, abs_tol=1e-5)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    return a == b


async def diagnose(args):
    os.environ['SA_MODEL_ROOT'] = str(args.models.resolve())
    manifest = json.loads((args.models / 'manifest.json').read_text('utf-8'))
    started = time.perf_counter()
    handlers = create_handlers()
    load_ms = (time.perf_counter() - started) * 1000
    with wave.open(str(args.wav), 'rb') as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        count = wav.getnframes()
        raw = wav.readframes(count)
    initial = {'audio': {'sample_rate_hz': 16000, 'channels': 1, 'sample_format': 's16le',
                         'sample_count': count, 'pcm_b64': base64.b64encode(raw).decode()}}
    points = [{'keypoint_id': f'k{i+1}', 'text': text} for i, text in enumerate(
        ['调查居民需求', '组织分层反诈宣传', '回访评估宣传效果'])]
    payload = initial
    outputs, direct_times = {}, {}
    for module in ('M1', 'M2', 'M3', 'M4'):
        started = time.perf_counter()
        output = handlers[module](payload)
        outputs[module] = output
        direct_times[module] = (time.perf_counter() - started) * 1000
        payload = output | {'keypoints': points} if module == 'M2' else output
    credential = secrets.token_hex(24)
    app = create_app(token=credential, model_version=manifest['model_version'],
                     config_version=manifest['config_version'], dimension=384, handlers=handlers)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False, ws='none'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    remote_outputs, requests = {}, []
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Loopback server failed to start')
            await asyncio.sleep(0.05)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', timeout=35,
                                     headers={'Authorization': f'Bearer {credential}'}, trust_env=False) as client:
            health = (await client.get('/healthz')).json()
            assert not health['demo'] and all(x['available'] for x in health['modules'].values())
            payload = initial
            for module in ('M1', 'M2', 'M3', 'M4'):
                body = {'schema_version': 1, 'task_id': 'synthetic-real-loopback-v1', 'attempt': 1,
                        'module_id': module, 'plan_version': 'diagnostic-remote',
                        'model_version': manifest['model_version'], 'config_version': manifest['config_version'],
                        'remaining_budget_ms': 30000, 'payload': payload}
                encoded = json.dumps(body, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                response = await client.post(f'/api/v1/modules/{module}/execute', content=encoded,
                                             headers={'Content-Type': 'application/json'})
                result = response.json()
                assert response.status_code == 200, result
                assert result['status'] == 'OK', result
                assert equivalent(outputs[module], result['output']), f'{module} mismatch'
                duplicate = await client.post(f'/api/v1/modules/{module}/execute', content=encoded,
                                              headers={'Content-Type': 'application/json'})
                assert duplicate.status_code == 200 and duplicate.json() == result
                requests.append({'module': module, 'http_status': response.status_code,
                                 'bytes_up': len(encoded), 'bytes_down': len(response.content),
                                 'gateway_elapsed_ms': result['elapsed_ms'], 'dedup_response_equal': True})
                remote_outputs[module] = result['output']
                payload = result['output'] | {'keypoints': points} if module == 'M2' else result['output']
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
    result = {'condition': 'REAL_MODELS_SYNTHETIC_TTS_DESKTOP_LOOPBACK_NOT_PHONE_EVALUATION',
              'audio_path': args.wav.name, 'audio_samples': count, 'model_version': manifest['model_version'],
              'model_load_ms': load_ms, 'direct_module_ms': direct_times, 'health': health,
              'http_requests': requests, 'comparison_abs_tolerance': 1e-5,
              'direct_remote_equivalent': True, 'outputs': outputs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), 'utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'outputs'}, ensure_ascii=False, indent=2))
    print(json.dumps(outputs['M2'], ensure_ascii=False))
    print(json.dumps(outputs['M4'], ensure_ascii=False))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('wav', type=Path)
    cli.add_argument('--models', type=Path, default=Path('models'))
    cli.add_argument('--output', type=Path, required=True)
    asyncio.run(diagnose(cli.parse_args()))
