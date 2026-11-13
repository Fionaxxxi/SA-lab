"""Create a clearly unreviewed manifest skeleton from the converted audio inventory."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--inventory', type=Path, default=ROOT/'experiments/samples/local/capture-inventory.json')
    cli.add_argument('--topics', type=Path, default=ROOT/'experiments/samples/topic-keypoints.json')
    cli.add_argument('--output', type=Path, default=ROOT/'experiments/samples/manifest.annotation-draft.json')
    args = cli.parse_args()
    inventory = json.loads(args.inventory.read_text('utf-8'))
    topics = json.loads(args.topics.read_text('utf-8'))
    if len(inventory['records']) != 30:
        raise ValueError('Expected 30 converted recordings')
    rows = []
    for item in inventory['records']:
        wav = ROOT / item['wav_path']
        rows.append({'sample_id': item['sample_id'], 'topic_id': item['topic_id'],
                     'speaker_id': '', 'split': item['split'],
                     'wav_path': str(wav.relative_to(args.output.parent)).replace('\\', '/'),
                     'sha256': item['wav_sha256'], 'effective_input': None,
                     'reference_text': '', 'annotator': '', 'reviewer': '', 'consent': None,
                     'keypoints': [{'keypoint_id': f'k{i+1}', 'text': text,
                                    'expected_covered': None, 'accepted_evidence_sentence_ids': []}
                                   for i, text in enumerate(topics[item['topic_id']])]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    print(f'Created unreviewed annotation draft for {len(rows)} recordings: {args.output}')

if __name__ == '__main__':
    main()
