"""Reviewed coverage agreement, corpus/per-observation CER and quality reports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from jsonschema import Draft202012Validator
from experiments.scripts.compute_metrics import edits, normalize, percentile

SCHEMA_PATH = Path(__file__).resolve().parents[1]/'samples/quality-review.schema.json'
SCHEMA = json.loads(SCHEMA_PATH.read_text('utf-8'))
GROUP_FIELDS = ('run_id','device_id','model_version','config_version','mode','input_source','split')

def ratio(a,b):
    return a/b if b else None

def strict_json(data):
    def unique(pairs):
        result = dict(pairs)
        if len(result)!=len(pairs):
            raise ValueError('Duplicate JSON field')
        return result
    def finite(value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('Non-finite number')
        return value
    def invalid(value):
        raise ValueError('Non-finite JSON constant: '+value)
    return json.loads(data,object_pairs_hook=unique,parse_float=finite,parse_constant=invalid)

def prepare(payload, condition=None):
    errors = list(Draft202012Validator(SCHEMA).iter_errors(payload))
    if errors:
        def leaves(error):
            return [leaf for child in error.context for leaf in leaves(child)] if error.context else [error]
        detail = max((leaf for error in errors for leaf in leaves(error)),key=lambda e:len(e.absolute_path))
        location = '.'.join(map(str,detail.absolute_path)) or '<root>'
        raise ValueError('Invalid review field at '+location+': '+detail.message[:200])
    legacy = isinstance(payload,list)
    declared = 'UNREVIEWED' if legacy else payload['condition']
    if condition is not None:
        if not legacy and condition!=declared:
            raise ValueError('Cannot relabel an existing review envelope condition')
        declared = condition
    if declared not in ('FIXTURE','UNREVIEWED','REVIEWED'):
        raise ValueError('Unknown condition')
    raw_rows = payload if legacy else payload['records']
    rows, identities, topics, sample_topics = [], {}, {}, {}
    duplicates = 0
    for index, raw in enumerate(raw_rows,1):
        row = dict(raw)
        if not legacy and not row.get('sample_id'):
            raise ValueError('Versioned records require sample_id')
        row['sample_id'] = row.get('sample_id',f'legacy-row-{index:04d}')
        keys = ('run_id','device_id','task_id')
        present = [key in row for key in keys]
        if any(present) and not all(present):
            raise ValueError('Supply run_id/device_id/task_id together')
        if all(present):
            identity = tuple(row[k] for k in keys)
        elif not legacy:
            identity = (row['sample_id'],)+tuple(row.get(k) for k in GROUP_FIELDS)
        else:
            identity = ('legacy-row',index)
        encoded = json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False)
        if identity in identities:
            if identities[identity]!=encoded:
                raise ValueError('Conflicting observations for the same task/sample identity')
            duplicates += 1
            continue
        identities[identity] = encoded
        topic, split = row.get('topic_id'), row.get('split')
        if topic and split and topics.setdefault(topic,split)!=split:
            raise ValueError('A topic occurs in both calibration and evaluation')
        if topic and sample_topics.setdefault(row['sample_id'],topic)!=topic:
            raise ValueError('A sample_id changes topic')
        if declared=='REVIEWED':
            required = keys+('topic_id','split','audio_sha256','model_version','config_version','mode','input_source','effective_input','annotator','reviewer','consent')
            if any(key not in row for key in required):
                raise ValueError('REVIEWED records need traceable audio, versions and human review')
            if (type(row['effective_input']) is not bool or row['consent'] is not True
                    or row['annotator'].strip()==row['reviewer'].strip()
                    or any(str(row[k]).upper().startswith('TODO') for k in required)):
                raise ValueError('Incomplete human review or input classification')
        matches = []
        for number, match in enumerate(row['matches'],1):
            match = dict(match)
            if declared=='REVIEWED' and not match.get('keypoint_id'):
                raise ValueError('REVIEWED matches require keypoint_id')
            match['keypoint_id'] = match.get('keypoint_id',f'legacy-keypoint-{number}')
            if match['expected_covered'] is False and match.get('accepted_evidence_sentence_ids'):
                raise ValueError('Uncovered reference cannot have accepted evidence')
            matches.append(match)
        if len({m['keypoint_id'] for m in matches})!=len(matches):
            raise ValueError('Duplicate keypoint_id in one observation')
        row['matches'] = matches
        row['_source_row'] = index
        rows.append(row)
    return rows, {'condition':declared,'legacy_input':legacy,'input_records':len(raw_rows),'duplicates_removed':duplicates}

def score_row(row):
    eligible = row.get('effective_input') is not False
    reference, actual = normalize(row['reference_text']), normalize(row['actual_text'])
    if eligible and not reference:
        raise ValueError('Empty normalized reference transcript: '+row['sample_id'])
    result = {key:row.get(key) for key in GROUP_FIELDS}
    result.update(sample_id=row['sample_id'],task_id=row.get('task_id'),audio_sha256=row.get('audio_sha256'),
        source_row=row['_source_row'],effective_input=row.get('effective_input'),eligible=eligible,
        exclusion_reason=None if eligible else 'PRECLASSIFIED_INVALID_INPUT',
        reference_characters=len(reference),actual_characters=len(actual),
        edit_errors=edits(reference,actual) if eligible else None,
        reference_text=row['reference_text'],actual_text=row['actual_text'])
    result['cer'] = ratio(result['edit_errors'],len(reference)) if eligible else None
    tp=tn=fp=fn=missing=evidence_correct=evidence_count=0
    points = []
    for match in row['matches']:
        expected, predicted = match['expected_covered'], match['actual_covered']
        correct = None if predicted is None else expected==predicted
        evidence = None
        if eligible:
            if predicted is None:
                missing += 1
            elif expected and predicted:
                tp += 1
            elif not expected and not predicted:
                tn += 1
            elif predicted:
                fp += 1
            else:
                fn += 1
            if predicted is True:
                evidence_count += 1
                evidence = match['actual_evidence_sentence_id'] is not None and match['actual_evidence_sentence_id'] in match['accepted_evidence_sentence_ids']
                evidence_correct += int(evidence)
        points.append({key:result.get(key) for key in ('sample_id','task_id')+GROUP_FIELDS} |
            {'source_row':row['_source_row'],'eligible':eligible,'keypoint_id':match['keypoint_id'],
             'expected_covered':expected,'actual_covered':predicted,'agreement':correct if eligible else None,
             'actual_evidence_sentence_id':match.get('actual_evidence_sentence_id'),
             'accepted_evidence_sentence_ids':json.dumps(match.get('accepted_evidence_sentence_ids'),ensure_ascii=False),
             'evidence_correct':evidence})
    known = tp+tn+fp+fn
    result.update(tp=tp,tn=tn,fp=fp,fn=fn,labeled_keypoints=len(row['matches']) if eligible else 0,
        compared_keypoints=known,missing_predictions=missing,
        coverage_accuracy=ratio(tp+tn,known),coverage_correct_rate_all=ratio(tp+tn,known+missing),
        evidence_correct=evidence_correct,evidence_count=evidence_count,
        evidence_accuracy=ratio(evidence_correct,evidence_count))
    return result,points

def summarize(records):
    eligible = [r for r in records if r['eligible']]
    total = lambda key:sum(r[key] for r in eligible)
    tp,tn,fp,fn = (total(k) for k in ('tp','tn','fp','fn'))
    chars,errors = total('reference_characters'),total('edit_errors')
    values = [r['cer'] for r in eligible]
    point_count,known = total('labeled_keypoints'),total('compared_keypoints')
    evidence_n,evidence_correct = total('evidence_count'),total('evidence_correct')
    accuracy_values = [r['coverage_accuracy'] for r in eligible if r['coverage_accuracy'] is not None]
    return {'observations':len(records),'recordings':len(eligible),'excluded_invalid_inputs':len(records)-len(eligible),
        'unique_sample_ids':len({r['sample_id'] for r in eligible}),
        'unique_known_audio_hashes':len({r['audio_sha256'] for r in eligible if r['audio_sha256']}),
        'missing_audio_hashes':sum(not r['audio_sha256'] for r in eligible),
        'unknown_effective_input':sum(r['effective_input'] is None for r in records),
        'reference_characters':chars,'edit_errors':errors,'cer':ratio(errors,chars),
        'macro_cer':mean(values) if values else None,
        'cer_p50':percentile(values,.5),'cer_p90':percentile(values,.9),'cer_p99':percentile(values,.99),
        'tp':tp,'tn':tn,'fp':fp,'fn':fn,'labeled_keypoints':point_count,'compared_keypoints':known,
        'missing_predictions':total('missing_predictions'),'missing_match_labels':sum(r['labeled_keypoints']==0 for r in eligible),
        'coverage_accuracy':ratio(tp+tn,known),'coverage_correct_rate_all':ratio(tp+tn,point_count),
        'prediction_availability':ratio(known,point_count),
        'macro_coverage_accuracy':mean(accuracy_values) if accuracy_values else None,
        'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),
        'evidence_count':evidence_n,'evidence_correct':evidence_correct,'evidence_accuracy':ratio(evidence_correct,evidence_n)}

def evaluate(payload, *, condition=None, split='all'):
    rows,metadata = prepare(payload,condition)
    if split not in ('all','calibration','evaluation'):
        raise ValueError('Unknown split filter')
    selected = [r for r in rows if split=='all' or r.get('split')==split]
    if not selected:
        raise ValueError('No observations match the split filter')
    scored = [score_row(row) for row in selected]
    for index,(sample,points) in enumerate(scored,1):
        sample['observation_index'] = index
        for point in points:
            point['observation_index'] = index
    samples = [value[0] for value in scored]
    matches = [point for value in scored for point in value[1]]
    groups = {}
    for sample in samples:
        groups.setdefault(tuple(sample.get(k) for k in GROUP_FIELDS),[]).append(sample)
    grouped = [dict(zip(GROUP_FIELDS,key)) | summarize(value) for key,value in groups.items()]
    summary = summarize(samples)
    notes = []
    if metadata['condition']=='FIXTURE':
        notes.append('测试夹具数据，只验证计算和报告流程，不代表真实录音或系统质量。')
    elif metadata['condition']=='UNREVIEWED':
        notes.append('输入尚未满足审核登记要求，统计不作为正式质量验收结论。')
    else:
        notes.append('审核信息由提交者提供，软件不代为完成审核或签收。')
    if summary['unique_known_audio_hashes']<30:
        notes.append('已知不同音频哈希不足 30 个，未据此宣称满足 S2 独立录音样本量。')
    if len(grouped)>1:
        notes.append('包含多组运行/设备/版本/来源/划分；整体只作汇总，各组指标单独列出。')
    if any(r.get('split')=='calibration' for r in selected):
        notes.append('包含校准集；独立评价请使用 --split evaluation，不用评价集调阈值。')
    if summary['unknown_effective_input']:
        notes.append('部分有效输入分类未知；其可计算的转写用于描述性统计，未补造有效输入标签。')
    if summary['missing_predictions'] or summary['missing_match_labels']:
        notes.append('存在未返回预测或缺少要点标注；同时报告覆盖分母、预测可用率及全标注要点正确率，不将缺测当作正确。')
    return {'schema_version':1,**metadata,'selected_split':split,'selected_observations':len(selected),
        'normalization':'Remove Unicode punctuation and whitespace only; preserve letters/case/numbers.',
        'cer_definition':'sum(character edit distance) / sum(normalized reference characters); no clipping above 1.',
        'coverage_definition':'(TP+TN)/(TP+TN+FP+FN); missing predictions excluded and disclosed separately.',
        'all_label_rate_definition':'(TP+TN)/all labeled keypoints; missing predictions receive no correctness credit.',
        'notes':notes,'summary':summary,'groups':grouped,'per_sample':samples,'per_keypoint':matches}

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('labels',type=Path)
    cli.add_argument('--output',type=Path,help='New output directory for JSON/CSV/figures/Markdown')
    cli.add_argument('--condition',choices=['FIXTURE','UNREVIEWED'],help='Only legacy arrays may be explicitly labeled')
    cli.add_argument('--split',choices=['all','calibration','evaluation'],default='all')
    cli.add_argument('--cer-target',type=float,default=.2)
    cli.add_argument('--coverage-target',type=float)
    cli.add_argument('--evidence-target',type=float)
    args = cli.parse_args()
    for value in (args.cer_target,args.coverage_target,args.evidence_target):
        if value is not None and (not math.isfinite(value) or value<0):
            cli.error('Targets must be finite and nonnegative')
    for value in (args.coverage_target,args.evidence_target):
        if value is not None and value>1:
            cli.error('Accuracy targets must be in [0,1]')
    raw = args.labels.read_bytes()
    report = evaluate(strict_json(raw),condition=args.condition,split=args.split)
    report['input_file'] = args.labels.name
    report['input_sha256'] = hashlib.sha256(raw).hexdigest()
    report['tool_sources_sha256'] = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in
        (Path(__file__),Path(__file__).with_name('quality_report.py'),Path(__file__).with_name('compute_metrics.py'),SCHEMA_PATH)}
    report['targets'] = {'cer_max':args.cer_target,'coverage_accuracy_min':args.coverage_target,
                         'evidence_accuracy_min':args.evidence_target}
    if args.output:
        from experiments.scripts.quality_report import write_report
        write_report(report,args.output,source_bytes=raw)
    # Preserve the old command's summary JSON output, with explicit new denominators.
    print(json.dumps({'condition':report['condition'],**report['summary']},ensure_ascii=False,indent=2,allow_nan=False))

if __name__=='__main__':
    main()
