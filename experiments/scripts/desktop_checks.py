"""Run real HTTP/model boundary checks without a phone or fabricated human data."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import wave
import httpx
from server.modules.audio_io import read_wav
from server.gateway.protocol import MAX_BODY, ProtocolError


def serve(models, log, client):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.close()
    credential = secrets.token_hex(24)
    env = os.environ | {'SA_MODEL_ROOT': str(models.resolve()), 'SA_GATEWAY_TOKEN': credential,
        'SA_MODULE_FACTORY': 'server.modules.integration:create_handlers', 'SA_DEMO': '0',
        'SA_MODEL_VERSION': 'unconfigured', 'SA_CONFIG_VERSION': 'unconfigured', 'PYTHONIOENCODING': 'utf-8'}
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server.app:create', '--factory',
        '--host', '127.0.0.1', '--port', str(port), '--workers', '1', '--ws', 'none',
        '--no-access-log', '--log-level', 'warning'], env=env, stdout=log, stderr=log)
    base = f'http://127.0.0.1:{port}'
    deadline = time.monotonic() + 240
    try:
        while time.monotonic() < deadline and process.poll() is None:
            try:
                response = client.get(base + '/healthz', timeout=1)
                if response.status_code == 200:
                    return process, base, credential, response.json()
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise RuntimeError('Gateway failed to become ready; inspect the server diagnostic log')
    except BaseException:
        process.terminate()
        process.wait(timeout=20)
        raise


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    golden = json.loads(args.golden.read_text('utf-8'))
    initial = read_wav(args.wav)
    records = []
    with httpx.Client(trust_env=False, timeout=40) as client, (args.output/'server.log').open('wb') as log:
        process, base, token, health = serve(args.models, log, client)
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        sequence = 0
        def body(module, payload):
            nonlocal sequence
            sequence += 1
            return {'schema_version': 1, 'task_id': f'desktop-check-{sequence}', 'attempt': 1,
                'module_id': module, 'plan_version': 'desktop-check-v1', 'model_version': health['model_version'],
                'config_version': health['config_version'], 'remaining_budget_ms': 30000, 'payload': payload}
        def check(name, request, expected_status=200, expected_code=None, **options):
            sent = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode()
            started = time.perf_counter()
            response = client.post(base + '/api/v1/modules/' + request['module_id'] + '/execute',
                content=sent, headers=options.pop('headers', headers), **options)
            value = response.json()
            code = value.get('error', {}).get('code')
            passed = response.status_code == expected_status and code == expected_code
            records.append({'case_id': name, 'expected_http': expected_status, 'actual_http': response.status_code,
                'expected_code': expected_code, 'actual_code': code, 'passed': passed,
                'bytes_up': len(sent), 'bytes_down': len(response.content),
                'round_trip_ms': (time.perf_counter() - started) * 1000})
            with (args.output/"http-cases.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(records[-1], ensure_ascii=False) + "\n")
            assert passed, (name, response.status_code, value)
            return value
        try:
            assert not health['demo'] and all(x['available'] for x in health['modules'].values())
            payload, outputs = initial, {}
            for module in ('M1', 'M2', 'M3', 'M4'):
                request = body(module, payload)
                value = check(module + '-real', request)
                duplicate = check(module + '-same-key', request)
                assert duplicate == value
                conflict = request | {'remaining_budget_ms': 29999}
                check(module + '-conflicting-key', conflict, 409, 'REQUEST_CONFLICT')
                outputs[module] = value['output']
                payload = value['output'] | {'keypoints': golden['speech_keypoints']} if module == 'M2' else value['output']
            assert outputs['M2']['transcript'] == golden['expected']['transcript']
            score_error = max(abs(a['score'] - b['score']) for a,b in zip(
                outputs['M4']['matches'], golden['expected']['matches'], strict=True))
            assert score_error <= golden['tolerance']['score_abs']
            (args.output/'real-http-outputs.json').write_text(json.dumps(outputs, ensure_ascii=False, indent=2), 'utf-8')
            silent = {'audio': initial['audio'] | {'sample_count': 16000,
                'pcm_b64': base64.b64encode(bytes(32000)).decode()}}
            check('silence-vad', body('M1', silent), 422, 'NO_SPEECH')
            silence_segments = {'segments': [{'segment_id': 'silent', 'start_sample': 0, 'end_sample': 16000,
                'pcm_b64': silent['audio']['pcm_b64']}]}
            check('silence-asr', body('M2', silence_segments), 422, 'NO_TRANSCRIPT')
            for i in range(20):
                check(f'recognizer-recreate-{i+1:02d}', body('M2', silence_segments), 422, 'NO_TRANSCRIPT')
            invalid = copy.deepcopy(initial)
            invalid['audio']['pcm_b64'] = ''
            check('empty-pcm', body('M1', invalid), 400, 'INVALID_PAYLOAD')
            invalid['audio']['sample_count'] = 960001
            check('over-60s', body('M1', invalid), 400, 'INVALID_PAYLOAD')
            invalid = copy.deepcopy(initial)
            invalid['audio']['pcm_b64'] = '%%%'
            check('bad-base64', body('M1', invalid), 400, 'INVALID_PAYLOAD')
            request = body('M1', initial) | {'model_version': 'incorrect-model'}
            check('wrong-version', request, 409, 'VERSION_MISMATCH')
            check('unknown-module', body('M9', initial), 404, 'UNKNOWN_MODULE')
            check('wrong-token', body('M1', initial), 401, 'UNAUTHORIZED',
                headers=headers | {'Authorization': 'Bearer invalid-token'})
            invalid = copy.deepcopy(outputs['M3'])
            invalid['embeddings']['keypoints'][0]['vector'] = [0] * 384
            check('zero-vector', body('M4', invalid), 400, 'INVALID_PAYLOAD')
            invalid['embeddings']['dimension'] = 383
            check('wrong-dimension', body('M4', invalid), 400, 'INVALID_PAYLOAD')
            request = body('M1', initial) | {'remaining_budget_ms': 1}
            check('deadline', request, 504, 'DEADLINE_EXCEEDED')
            response = client.post(base+'/api/v1/modules/M1/execute', content=b'x' * (MAX_BODY+1), headers=headers)
            value = response.json()
            assert response.status_code == 413 and value['error']['code'] == 'PAYLOAD_TOO_LARGE'
            records.append({'case_id': 'body-over-4MiB', 'passed': True, 'actual_http': 413,
                            'actual_code': value['error']['code']})
        finally:
            stop(process)
        with tempfile.TemporaryDirectory() as empty:
            process, base, token, missing_health = serve(Path(empty), log, client)
            try:
                assert all(not x['available'] for x in missing_health['modules'].values())
                health = missing_health
                headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
                check('real-factory-missing-model', body('M1', initial), 503, 'MODEL_UNAVAILABLE')
            finally:
                stop(process)
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        cases = [('empty',16000,1,2,0), ('stereo',16000,2,2,10), ('wrong-rate',48000,1,2,10),
                 ('24-bit',16000,1,3,10), ('over-duration',16000,1,2,960001), ('truncated',16000,1,2,100)]
        for name, rate, channels, width, count in cases:
            path = folder/(name+'.wav')
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((channels,width,rate,0,'NONE','not compressed'))
                wav.writeframes(bytes(count*channels*width))
            if name == 'truncated':
                path.write_bytes(path.read_bytes()[:-2])
            try:
                read_wav(path)
            except ProtocolError as error:
                assert error.code == 'INVALID_PAYLOAD'
                records.append({'case_id': 'wav-'+name, 'passed': True, 'actual_code': error.code})
            else:
                raise AssertionError('Accepted bad WAV: '+name)
        path = folder/'bad-header.wav'
        path.write_bytes(b'not a RIFF WAV')
        try:
            read_wav(path)
        except ProtocolError as error:
            assert error.code == 'INVALID_PAYLOAD'
            records.append({'case_id': 'wav-bad-header', 'passed': True, 'actual_code': error.code})
        else:
            raise AssertionError('Accepted malformed WAV')
    result = {'condition': 'REAL_MODELS_SYNTHETIC_DESKTOP_HTTP_NOT_PHONE_EVALUATION',
        'model_version': golden['model_version'], 'golden_sha256': hashlib.sha256(args.golden.read_bytes()).hexdigest(),
        'audio_sha256': hashlib.sha256(args.wav.read_bytes()).hexdigest(),
        'score_max_abs': score_error, 'recognizer_recreations_with_valid_error': 20,
        'memory_leak_conclusion': 'No leak conclusion is drawn from 20 short requests; use startup process counters for measured memory.',
        'cases': records, 'passed': all(row['passed'] for row in records)}
    (args.output/'checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    print(f'Passed {len(records)} desktop cases; 20 fresh recognizer invocations included.')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--models', type=Path, default=Path('models'))
    cli.add_argument('--wav', type=Path, required=True)
    cli.add_argument('--golden', type=Path, default=Path('contracts/examples/golden-desktop-v1.json'))
    cli.add_argument('--output', type=Path, required=True)
    main(cli.parse_args())
