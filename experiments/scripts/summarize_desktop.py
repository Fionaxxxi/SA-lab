"""Summarize measured desktop startup, latency and process-memory records."""
import argparse
import json
from pathlib import Path
import statistics
import os
import tempfile
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "interview-feedback-mpl"))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def summarize(folder, output):
    result = json.loads((folder/'startup.json').read_text('utf-8'))
    cold = [r for r in result['rows'] if r['kind'] == 'PROCESS_COLD']
    warm = [r for r in result['rows'] if r['kind'] == 'MODEL_WARM']
    assert len(cold) == len(warm) == 5
    summary = {'condition': result['condition'], 'device_id': result['device_id'],
        'cold_trials': 5, 'warm_trials': 5, 'os_filesystem_cache_flushed': False,
        'all_golden_passed': all(r['comparison']['passed'] for r in result['rows']),
        'cold_load_median_ms': statistics.median(r['load_ms'] for r in cold),
        'cold_first_inference_median_ms': statistics.median(r['inference_ms'] for r in cold),
        'warm_inference_median_ms': statistics.median(r['inference_ms'] for r in warm),
        'cold_first_inference_min_ms': min(r['inference_ms'] for r in cold),
        'cold_first_inference_max_ms': max(r['inference_ms'] for r in cold),
        'warm_inference_min_ms': min(r['inference_ms'] for r in warm),
        'warm_inference_max_ms': max(r['inference_ms'] for r in warm),
        'peak_working_set_max_bytes': max(r['memory']['peak_working_set_bytes'] for r in result['rows']),
        'peak_commit_max_bytes': max(r['memory']['peak_commit_bytes'] for r in result['rows']),
        'formal_phone_evaluation': False}
    output.mkdir(parents=True, exist_ok=True)
    (output/'summary.json').write_text(json.dumps(summary, indent=2), 'utf-8')
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), constrained_layout=True)
    axes[0].bar(range(1,6), [r['load_ms']/1000 for r in cold], color='#2e6d9c')
    axes[0].set(title='Fresh-process model loading', xlabel='Fresh process', ylabel='Seconds')
    axes[0].set_xticks(range(1,6))
    for x, rows, label, color in [(0,cold,'First inference','#2e6d9c'),(1,warm,'Model reuse','#e18c32')]:
        values = [r['inference_ms']/1000 for r in rows]
        axes[1].scatter([x + d for d in [-.08,-.04,0,.04,.08]], values, color=color, s=32)
        med = statistics.median(values)
        axes[1].plot([x-.17,x+.17],[med,med],color=color,lw=2)
    axes[1].set(title='Real-model inference (n=5 each)', ylabel='Seconds', xticks=[0,1], xticklabels=['First inference','Model reuse'])
    axes[1].set_ylim(bottom=0)
    peaks = [r['memory']['peak_working_set_bytes']/1e9 for r in cold]
    peaks += [max(r['memory']['peak_working_set_bytes'] for r in warm)/1e9]
    axes[2].bar(['C1','C2','C3','C4','C5','W'], peaks, color=['#2e6d9c']*5+['#e18c32'])
    axes[2].set(title='Lifetime peak working set', ylabel='GB (decimal)', xlabel='C: fresh process; W: shared warm process')
    for axis in axes:
        axis.spines[['top','right']].set_visible(False)
        axis.grid(axis='y', alpha=.2)
        axis.set_axisbelow(True)
    fig.suptitle('Desktop diagnostic | synthetic TTS, 8.455 s | OS file cache retained | no phone or human evaluation', fontsize=10)
    fig.savefig(output/'startup.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('folder', type=Path)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    summarize(args.folder, args.output)
