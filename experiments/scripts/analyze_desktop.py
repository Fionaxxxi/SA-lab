"""Analyze a WAV entirely on this computer and save readable feedback."""
import argparse
import json
import os
from pathlib import Path
import time
from server.modules.audio_io import read_wav
from server.modules.integration import create_handlers


def analyze(wav, keypoints, models, output):
    lines = [line.strip() for line in keypoints.read_text('utf-8-sig').splitlines() if line.strip()]
    if not 1 <= len(lines) <= 100:
        raise ValueError('Provide 1 to 100 reference keypoints, one per line')
    payload = read_wav(wav)
    manifest = json.loads((models / 'manifest.json').read_text('utf-8'))
    os.environ['SA_MODEL_ROOT'] = str(models.resolve())
    started = time.perf_counter()
    print("正在加载本地模型，请等待……", flush=True)
    handlers = create_handlers(strict=True)
    load_ms = (time.perf_counter() - started) * 1000
    points = [{'keypoint_id': f'k{i+1}', 'text': text} for i, text in enumerate(lines)]
    outputs, durations = {}, {}
    started = time.perf_counter()
    for module in ('M1', 'M2', 'M3', 'M4'):
        begin = time.perf_counter()
        result = handlers[module](payload)
        durations[module] = (time.perf_counter() - begin) * 1000
        outputs[module] = result
        payload = result | {'keypoints': points} if module == 'M2' else result
    result = {'condition': 'DESKTOP_LOCAL_INPUT_NOT_HUMAN_REVIEWED', 'formal_evaluation': False, 'model_version': manifest['model_version'],
              'config_version': manifest['config_version'], 'source_wav': wav.name, 'reference_keypoints': points,
              'model_load_ms': load_ms, 'inference_ms': (time.perf_counter() - started) * 1000,
              'module_ms': durations, 'transcript': outputs['M2']['transcript'], 'matches': outputs['M4']['matches']}
    output.parent.mkdir(parents=True, exist_ok=True)
    # The result intentionally contains the supplied transcript and evidence.
    # Gateway event logs remain free of these contents.
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    text = '# 电脑本地分析结果\n\n来源：' + wav.name + '\n\n本结果未经人工复核。\n\n' + result['transcript']['full_text'] + '\n\n'
    for point, match in zip(points, result['matches'], strict=True):
        label = '已覆盖' if match['covered'] else '可能遗漏'
        text += f'- {point["text"]}：{label}（{match["score"]:.3f}）\n  依据：{match["evidence_text"]}\n'
    text += '\n阈值来自当前配置，仍待人工校准。此文件为电脑分析结果。\n'
    output.with_suffix('.md').write_text(text, 'utf-8')
    print(f'JSON: {output}\nFeedback: {output.with_suffix(".md")}')
    return result


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('wav', type=Path)
    cli.add_argument('--keypoints', type=Path, required=True)
    cli.add_argument('--models', type=Path, default=Path('models'))
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    analyze(args.wav, args.keypoints, args.models, args.output)
