"""Run the converted sample catalog through the real desktop M1–M4 pipeline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from server.modules.audio_io import read_wav
from server.modules.integration import create_handlers

ROOT = Path(__file__).resolve().parents[2]

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--inventory', type=Path, default=ROOT/'experiments/samples/local/capture-inventory.json')
    cli.add_argument('--topics', type=Path, default=ROOT/'experiments/samples/topic-keypoints.json')
    cli.add_argument('--models', type=Path, default=ROOT/'models')
    cli.add_argument('--split', choices=['calibration', 'evaluation'], required=True)
    cli.add_argument('--include-evaluation', action='store_true',
                     help='Explicitly consume the held-out evaluation split after freezing rules.')
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    if args.split == 'evaluation' and not args.include_evaluation:
        cli.error('Evaluation split is held out; freeze rules and pass --include-evaluation when ready.')
    inventory_bytes = args.inventory.read_bytes()
    inventory = json.loads(inventory_bytes)
    if inventory['status'] != 'AUDIO_CONVERTED_UNREVIEWED':
        raise ValueError('Unexpected capture inventory status')
    topic_bytes = args.topics.read_bytes()
    topics = json.loads(topic_bytes)
    rows = [row for row in inventory['records'] if row['split'] == args.split]
    if len(rows) != 15:
        raise ValueError('Expected 15 recordings in each topic-disjoint split')
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['SA_MODEL_ROOT'] = str(args.models.resolve())
    load_start = time.perf_counter()
    handlers = create_handlers(strict=True)
    load_ms = (time.perf_counter() - load_start) * 1000
    manifest_bytes = (args.models/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    summary = {'condition': 'REAL_RECORDINGS_UNREVIEWED_EXPLORATORY',
               'formal_quality_ready': False, 'split': args.split,
               'model_version': manifest['model_version'], 'config_version': manifest['config_version'],
               'model_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
               'capture_inventory_sha256': hashlib.sha256(inventory_bytes).hexdigest(),
               'topic_keypoints_sha256': hashlib.sha256(topic_bytes).hexdigest(),
               'model_load_ms': load_ms, 'results': []}
    for row in rows:
        sample_id = row['sample_id']
        wav = ROOT / row['wav_path']
        if hashlib.sha256(wav.read_bytes()).hexdigest() != row['wav_sha256']:
            raise ValueError(f'{sample_id} WAV hash mismatch')
        points = [{'keypoint_id': f'k{i+1}', 'text': text}
                  for i, text in enumerate(topics[row['topic_id']])]
        result = {'sample_id': sample_id, 'topic_id': row['topic_id'], 'split': row['split'],
                  'audio_sha256': row['wav_sha256'], 'duration_s': row['duration_s'],
                  'reference_keypoints': points, 'module_ms': {}}
        try:
            payload = read_wav(wav)
            outputs = {}
            for module in ('M1', 'M2', 'M3', 'M4'):
                started = time.perf_counter()
                outputs[module] = handlers[module](payload)
                result['module_ms'][module] = (time.perf_counter() - started) * 1000
                payload = outputs[module] | {'keypoints': points} if module == 'M2' else outputs[module]
            result['status'] = 'SUCCESS'
            result['intervals'] = [{k:v for k,v in segment.items() if k != 'pcm_b64'}
                                   for segment in outputs['M1']['segments']]
            result['transcript'] = outputs['M2']['transcript']
            result['semantic'] = outputs['M3']
            result['matches'] = outputs['M4']['matches']
        except Exception as error:
            result['status'] = 'ERROR'
            result['error_type'] = type(error).__name__
            result['error_message'] = str(error)
        (args.output/f'{sample_id}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'utf-8')
        summary['results'].append({'sample_id': sample_id, 'status': result['status'],
                                   'module_ms': result['module_ms'],
                                   'covered': [m['covered'] for m in result.get('matches', [])]})
        print(f'{sample_id}: {result["status"]}', flush=True)
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(f'Completed {len(rows)} {args.split} recordings; output: {args.output}')

if __name__ == '__main__':
    main()
