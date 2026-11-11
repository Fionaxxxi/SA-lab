"""Five process-cold and five model-warm desktop diagnostics, with real memory counters."""
import argparse
import csv
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone


def memory():
    if os.name != 'nt':
        raise RuntimeError('This measurement uses Windows PROCESS_MEMORY_COUNTERS')
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    current = ctypes.WinDLL('kernel32', use_last_error=True).GetCurrentProcess
    current.restype = wintypes.HANDLE
    get = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    get.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get.restype = wintypes.BOOL
    values = Counters()
    values.cb = ctypes.sizeof(values)
    if not get(current(), ctypes.byref(values), values.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'working_set_bytes': values.WorkingSetSize, 'peak_working_set_bytes': values.PeakWorkingSetSize,
            'commit_bytes': values.PagefileUsage, 'peak_commit_bytes': values.PeakPagefileUsage}


def worker(args):
    import numpy as np
    from server.modules.integration import create_handlers
    from server.modules.audio_io import read_wav
    golden = json.loads(args.golden.read_text('utf-8'))
    manifest = json.loads((args.models / 'manifest.json').read_text('utf-8'))
    assert manifest['model_version'] == golden['model_version']
    assert hashlib.sha256(args.wav.read_bytes()).hexdigest() == golden['audio']['sha256']
    canonical = json.dumps(golden['input'], ensure_ascii=False, separators=(',', ':')).encode()
    assert hashlib.sha256(canonical).hexdigest() == golden['input_sha256']
    os.environ['SA_MODEL_ROOT'] = str(args.models.resolve())
    before = memory()
    begin = time.perf_counter()
    handlers = create_handlers(strict=True)
    load_ms = (time.perf_counter() - begin) * 1000
    after_load = memory()
    initial = read_wav(args.wav)
    def inference():
        begin = time.perf_counter()
        payload = initial
        outputs, durations = {}, {}
        for module in ('M1', 'M2', 'M3', 'M4'):
            started = time.perf_counter()
            output = handlers[module](payload)
            durations[module] = (time.perf_counter() - started) * 1000
            outputs[module] = output
            payload = output | {'keypoints': golden['speech_keypoints']} if module == 'M2' else output
        elapsed_ms = (time.perf_counter() - begin) * 1000
        expected = golden['expected']
        intervals = [{k:v for k,v in row.items() if k != 'pcm_b64'} for row in outputs['M1']['segments']]
        assert intervals == expected['intervals']
        assert outputs['M2']['transcript'] == expected['transcript']
        max_score_diff = 0
        for actual, wanted in zip(outputs['M4']['matches'], expected['matches'], strict=True):
            max_score_diff = max(max_score_diff, abs(actual['score'] - wanted['score']))
            assert max_score_diff <= golden['tolerance']['score_abs']
            assert {k:v for k,v in actual.items() if k != 'score'} == {k:v for k,v in wanted.items() if k != 'score'}
        encoder = handlers['M3']
        vectors = [encoder.vector(text) for text in golden['input']['texts']]
        tokens = [encoder.tokens(text) for text in golden['input']['texts']]
        assert tokens == expected['token_ids']
        norms = np.linalg.norm(vectors, axis=1)
        prefix_error = float(np.max(np.abs(np.asarray(vectors)[:, :8] - expected['vectors_first8'])))
        cosine_error = float(np.max(np.abs(np.asarray(vectors) @ np.asarray(vectors).T - expected['cosine'])))
        assert prefix_error <= golden['tolerance']['vector_abs']
        assert cosine_error <= golden['tolerance']['vector_abs']
        assert max(abs(norms - 1)) <= golden['tolerance']['norm_abs']
        return elapsed_ms, durations, {'passed': True, 'tokens_equal': True,
            'vector_prefix_max_abs': prefix_error, 'cosine_max_abs': cosine_error, 'score_max_abs': max_score_diff}
    if args.kind == 'MODEL_WARM':
        inference()  # One unrecorded prewarm; never count it as a measured trial.
    rows = []
    for index in range(args.trials):
        elapsed, durations, comparison = inference()
        rows.append({'kind': args.kind, 'trial': index + 1, 'pid': os.getpid(), 'load_ms': load_ms,
            'inference_ms': elapsed, 'module_ms': durations, 'memory': memory(), 'comparison': comparison})
        print(f'{args.kind} {index+1}/{args.trials}: {elapsed:.1f} ms', flush=True)
    args.output.write_text(json.dumps({'before_load': before, 'after_load': after_load, 'rows': rows}, indent=2), 'utf-8')


def export_csv(result, path):
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        fields = ['condition', 'device_id', 'model_version', 'config_version', 'model_manifest_sha256', 'kind', 'trial', 'pid', 'load_ms', 'inference_ms', 'M1_ms', 'M2_ms', 'M3_ms', 'M4_ms',
                  'working_set_bytes', 'peak_working_set_bytes', 'commit_bytes', 'peak_commit_bytes', 'golden_passed']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in result['rows']:
            writer.writerow({k:result[k] for k in ['condition','device_id','model_version','config_version','model_manifest_sha256']} | {k:row[k] for k in ['kind','trial','pid','load_ms','inference_ms']} |
                {k+'_ms':v for k,v in row['module_ms'].items()} | row['memory'] | {'golden_passed': row['comparison']['passed']})


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    rows, children = [], []
    for kind, count in [('PROCESS_COLD', 1)] * 5 + [('MODEL_WARM', 5)]:
        child = args.output / f'worker-{len(children)+1}.json'
        command = [sys.executable, '-m', 'experiments.scripts.desktop_startup', '--worker', '--models', str(args.models),
            '--wav', str(args.wav), '--golden', str(args.golden), '--output', str(child), '--kind', kind, '--trials', str(count)]
        started = time.perf_counter()
        result = subprocess.run(command, check=True)
        observed = json.loads(child.read_text('utf-8'))
        children.append({'file': child.name, 'process_wall_ms': (time.perf_counter() - started) * 1000,
                         'before_load': observed['before_load'], 'after_load': observed['after_load']})
        rows += observed['rows']
    metadata = {'condition': 'REAL_MODELS_SYNTHETIC_TTS_DESKTOP_ONLY',
        'created_at': datetime.now(timezone.utc).isoformat(), 'device_id': platform.node(),
        'platform': platform.platform(), 'cpu': platform.processor(), 'python': platform.python_version(),
        'model_version': json.loads((args.models/'manifest.json').read_text('utf-8'))['model_version'],
        'config_version': json.loads((args.models/'manifest.json').read_text('utf-8'))['config_version'],
        'model_manifest_sha256': hashlib.sha256((args.models/'manifest.json').read_bytes()).hexdigest(),
        'golden_sha256': hashlib.sha256(args.golden.read_bytes()).hexdigest(),
        'cold_definition': 'Fresh child process and fresh model objects; OS filesystem cache NOT flushed.',
        'warm_definition': 'One process, shared model objects, one unmeasured full prewarm, five recorded inferences.',
        'memory_definition': 'Windows process working-set/commit counters; peak is process lifetime high-water, not incremental per trial.',
        'reference': 'https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters',
        'latency_definition': 'VAD+ASR+semantic+match only; excludes loading, WAV decode, token/vector regression checks and UI.',
        'formal_phone_or_human_evaluation': False, 'children': children, 'rows': rows}
    (args.output/'startup.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), 'utf-8')
    export_csv(metadata, args.output/'startup.csv')
    print(f'Completed {len(rows)} measured trials in {len(children)} separate processes.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, default=Path('models'))
    parser.add_argument('--wav', type=Path, required=True)
    parser.add_argument('--golden', type=Path, default=Path('contracts/examples/golden-desktop-v1.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--kind', choices=['PROCESS_COLD', 'MODEL_WARM'], default='PROCESS_COLD')
    parser.add_argument('--trials', type=int, default=1)
    args = parser.parse_args()
    worker(args) if args.worker else main(args)
