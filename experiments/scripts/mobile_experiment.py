"""Prepare a mobile run config or validate exported config/sample/event linkage."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile
from jsonschema import Draft202012Validator
from experiments.scripts.compute_metrics import aggregate

ROOT = Path(__file__).resolve().parents[2]
RUN_SCHEMA = json.loads((ROOT/'experiments/configs/run-config.schema.json').read_text('utf-8'))
PLAN_SCHEMA = json.loads((ROOT/'contracts/execution-plan.schema.json').read_text('utf-8'))
HASH = re.compile(r'[0-9a-f]{64}')
NODES = ['M1','M2','M3','M4']

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def catalog_index(samples, formal=False):
    if not isinstance(samples,list) or not samples:
        raise ValueError('Empty sample catalog')
    index, topics = {}, {}
    for row in samples:
        if row['sample_id'] in index or not isinstance(row['sample_id'],str) or not row['sample_id'].strip():
            raise ValueError('Invalid or duplicate sample identities')
        if type(row['effective_input']) is not bool or not HASH.fullmatch(row['sha256']):
            raise ValueError('Missing explicit input classification or audio hash')
        if row['split'] not in ('calibration','evaluation') or topics.setdefault(row['topic_id'],row['split']) != row['split']:
            raise ValueError('Topic crosses calibration/evaluation split')
        points = row['keypoints']
        if not points or len({p['keypoint_id'] for p in points}) != len(points) or any(not p['text'].strip() for p in points):
            raise ValueError('Invalid keypoints')
        if formal and not (row.get('consent') is True and row.get('reference_text','').strip() and
            row.get('annotator','').strip() and row.get('reviewer','').strip() and
            row['annotator'].strip()!=row['reviewer'].strip() and all(type(p.get('expected_covered')) is bool for p in points)):
            raise ValueError('Formal samples need human annotation and review')
        index[row['sample_id']] = row
    if formal and (len(index)<30 or set(topics.values())!={'calibration','evaluation'}):
        raise ValueError('Formal run needs >=30 reviewed, topic-disjoint samples')
    return index

def build_run(device_info, manifest_bytes, samples_bytes, *, run_id, mode='LOCAL', source='IMPORT',
              condition='FIXTURE', warmup='COLD', duration_s=0, remote_modules=None, keypoint_count=None):
    manifest, samples = json.loads(manifest_bytes), json.loads(samples_bytes)
    device, observed = device_info['device'], device_info['runtime']
    if observed['model_manifest_sha256'] != sha256(manifest_bytes) or any(
            observed[key] != manifest[key] for key in ('model_version','config_version')):
        raise ValueError('Device model manifest or versions differ')
    catalog_index(samples,formal=condition=='FORMAL')
    counts = {len(row['keypoints']) for row in samples}
    if keypoint_count is None:
        if len(counts)!=1:
            raise ValueError('Use --keypoint-count to select a load when the catalog contains different counts')
        keypoint_count = next(iter(counts))
    if keypoint_count not in counts:
        raise ValueError('No registered sample has the configured keypoint count')
    remote = remote_modules if remote_modules is not None else (
        NODES if mode == 'REMOTE' else ['M2','M3'] if mode == 'MANUAL_MIXED' else [])
    run = {'schema_version':1,'measurement_version':'measurement-v1','run_id':run_id,'condition':condition,
        'device':device, 'network':{'mode':'OFFLINE' if mode=='LOCAL' else 'WIFI',
            'actual_bandwidth_mbps':None,'actual_rtt_ms':None,'profile_id':None},
        'input':{'source':source,'duration_s':duration_s,'keypoint_count':keypoint_count,
                 'sample_manifest_sha256':sha256(samples_bytes),'topic_set':None},
        'runtime':{key:observed[key] for key in ('apk_commit','apk_version','model_version','config_version','model_manifest_sha256')} |
            {'service_commit':None,'plan_version':'exp-'+mode+'-'+sha256(run_id.encode())[:12],
             'mode':mode,'remote_modules':remote,'warmup':warmup,'cache_policy':'FIXED'}}
    Draft202012Validator(RUN_SCHEMA).validate(run)
    if duration_s > 60:
        raise ValueError('Audio duration exceeds 60 seconds')
    return run

def validate_export(path):
    with ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) != len(set(item.filename for item in entries)) or sum(i.file_size for i in entries) > 128*1024*1024:
            raise ValueError('Duplicate files or export larger than 128 MiB')
        files = {}
        for item in entries:
            if item.filename != 'events.jsonl' and not re.fullmatch(r'experiments/(configs|samples|runs)/[0-9a-f]{64}\.json', item.filename):
                raise ValueError('Unexpected export path')
            files[item.filename] = archive.read(item)
    configs, catalogs, snapshots = {}, {}, {}
    for name, data in files.items():
        if '/configs/' in name or '/samples/' in name:
            digest = Path(name).stem
            if sha256(data) != digest:
                raise ValueError('Imported file hash mismatch')
            decoded = json.loads(data)
            if '/configs/' in name:
                Draft202012Validator(RUN_SCHEMA).validate(decoded)
                configs[digest] = decoded
            else:
                catalogs[digest] = catalog_index(decoded)
        elif '/runs/' in name:
            value = json.loads(data)
            if Path(name).stem != sha256(value['run_id'].encode()):
                raise ValueError('Run snapshot identity mismatch')
            snapshots[value['run_id']] = value
    for cfg in configs.values():
        catalog_index(list(catalogs[cfg['input']['sample_manifest_sha256']].values()),formal=cfg['condition']=='FORMAL')
    for run_id, snap in snapshots.items():
        cfg = configs[snap['run_config_sha256']]
        if cfg['run_id'] != run_id or cfg['input']['sample_manifest_sha256'] != snap['sample_manifest_sha256']:
            raise ValueError('Run snapshot changed configuration')
        Draft202012Validator(PLAN_SCHEMA).validate(snap['plan'])
    rows = [json.loads(line) for line in files.get('events.jsonl',b'').decode('utf-8-sig').splitlines() if line.strip()]
    linked, unregistered = [], 0
    for event in rows:
        link = event.get('experiment')
        if link is None:
            unregistered += 1
            continue
        cfg = configs[link['run_config_sha256']]
        samples = catalogs[link['sample_manifest_sha256']]
        sample = samples[event['sample_id']]
        snap = snapshots[event['run_id']]
        runtime, plan = cfg['runtime'], snap['plan']
        if not (event['run_id']==cfg['run_id']==snap['run_id'] and
                snap['run_config_sha256']==link['run_config_sha256'] and
                snap['sample_manifest_sha256']==link['sample_manifest_sha256']==cfg['input']['sample_manifest_sha256'] and
                event['device_id']==cfg['device']['device_id']==plan['device_id'] and
                event['input_source']==cfg['input']['source'] and event['mode']==runtime['mode']==plan['mode'] and
                all(event[k]==runtime[k]==plan[k] for k in ('plan_version','model_version','config_version')) and
                type(sample['effective_input']) is bool and type(event['effective_input']) is bool and
                event['effective_input']==sample['effective_input'] and
                link['condition']==cfg['condition'] and link['sample_sha256']==sample['sha256'] and
                link['topic_id']==sample['topic_id'] and link['split']==sample['split'] and
                len(sample['keypoints'])==cfg['input']['keypoint_count']):
            raise ValueError('Task/run/sample metadata mismatch')
        remote = set(runtime.get('remote_modules',NODES if event['mode']=='REMOTE' else []))
        for node in ['M0']+NODES+['M5']:
            if plan['assignments'][node] != ('REMOTE' if node in remote else 'LOCAL'):
                raise ValueError('Frozen execution ownership mismatch')
        if event['input_source']=='IMPORT' and link['actual_wav_sha256']!=sample['sha256']:
            raise ValueError('Imported WAV does not match registered sample')
        if event.get('module_id') is not None and event['executor']!=plan['assignments'][event['module_id']]:
            raise ValueError('Actual executor differs from frozen plan')
        linked.append(event)
    if not linked:
        raise ValueError('No registered experiment events')
    return {'registered_event_count':len(linked),'unregistered_event_count':unregistered,
            'run_count':len({x['run_id'] for x in linked}), 'passed':True,
            'audio_files_included':False,'metrics':aggregate(linked)}

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest='command', required=True)
    prepare = actions.add_parser('prepare')
    prepare.add_argument('--device-info',type=Path,required=True)
    prepare.add_argument('--models',type=Path,default=Path('models'))
    prepare.add_argument('--samples',type=Path,required=True)
    prepare.add_argument('--run-id',required=True)
    prepare.add_argument('--mode',choices=['LOCAL','REMOTE','MANUAL_MIXED'],default='LOCAL')
    prepare.add_argument('--source',choices=['IMPORT','RECORDING'],default='IMPORT')
    prepare.add_argument('--condition',choices=['FIXTURE','FORMAL'],default='FIXTURE')
    prepare.add_argument('--warmup',choices=['COLD','WARM'],default='COLD')
    prepare.add_argument('--duration-s',type=float,default=0)
    prepare.add_argument('--keypoint-count',type=int)
    prepare.add_argument('--output',type=Path,required=True)
    check = actions.add_parser('validate')
    check.add_argument('archive',type=Path)
    check.add_argument('--output',type=Path)
    args = cli.parse_args()
    if args.command=='prepare':
        if args.condition=='FORMAL':
            subprocess.run([sys.executable,'-m','experiments.scripts.check_samples',str(args.samples)],check=True)
        value = build_run(json.loads(args.device_info.read_bytes()),(args.models/'manifest.json').read_bytes(),
            args.samples.read_bytes(),run_id=args.run_id,mode=args.mode,source=args.source,condition=args.condition,
            warmup=args.warmup,duration_s=args.duration_s,keypoint_count=args.keypoint_count)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        print(str(args.output))
    else:
        value = validate_export(args.archive)
        text = json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(text+'\n','utf-8')
        print(text)

if __name__=='__main__':
    main()
