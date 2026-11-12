import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from experiments.scripts.quality_metrics import evaluate, strict_json
from experiments.scripts.quality_report import write_report


def fixture_reviews():
    def point(key,expected,actual,sentence=None,accepted=None):
        value = {'keypoint_id':key,'expected_covered':expected,'actual_covered':actual}
        if actual is True:
            value.update(actual_evidence_sentence_id=sentence,accepted_evidence_sentence_ids=accepted or [])
        return value
    values = [
        ('甲， 乙！','甲 乙',[point('k1',True,True,'s1',['s1']),point('k2',False,False),
                             point('k3',False,True,'s2',[]),point('k4',True,False)]),
        ('丙丁','丙戊',[point('k1',True,True,'s1',['s1'])]),
        ('己庚','',[point('k1',True,False)]),
        ('辛','辛壬癸',[]),
        ('','噪声',[]),
    ]
    rows = []
    for i,(reference,actual,points) in enumerate(values,1):
        rows.append({'sample_id':f'fixture-q{i}','run_id':'quality-fixture-run','device_id':'fixture-device',
            'task_id':f'fixture-task-{i}','topic_id':f'fixture-topic-{i}','split':'evaluation',
            'model_version':'fixture-model','config_version':'fixture-rules','mode':'LOCAL','input_source':'IMPORT',
            'effective_input':i!=5,'reference_text':reference,'actual_text':actual,'matches':points})
    return {'schema_version':1,'condition':'FIXTURE',
        'notes':'Constructed text/labels for arithmetic tests only. No human recording, annotator or reviewer claimed.',
        'records':rows}


class QualityMetricTests(unittest.TestCase):
    def test_micro_cer_coverage_tn_and_evidence_denominators(self):
        result = evaluate(fixture_reviews())
        summary = result['summary']
        self.assertEqual(summary['reference_characters'],7)
        self.assertEqual(summary['edit_errors'],5)
        self.assertAlmostEqual(summary['cer'],5/7)
        self.assertAlmostEqual(summary['macro_cer'],.875)
        self.assertEqual((summary['tp'],summary['tn'],summary['fp'],summary['fn']),(2,1,1,2))
        self.assertAlmostEqual(summary['coverage_accuracy'],.5)
        self.assertAlmostEqual(summary['precision'],2/3)
        self.assertAlmostEqual(summary['recall'],.5)
        self.assertAlmostEqual(summary['f1'],4/7)
        self.assertAlmostEqual(summary['evidence_accuracy'],2/3)
        self.assertEqual((summary['observations'],summary['recordings'],summary['excluded_invalid_inputs']),(5,4,1))
        self.assertEqual([row['cer'] for row in result['per_sample']],[0,.5,1,2,None])

    def test_blank_transcript_is_not_dropped_or_clipped(self):
        data = fixture_reviews()
        data['records'] = [data['records'][2],data['records'][3]]
        result = evaluate(data)
        self.assertEqual(result['summary']['recordings'],2)
        self.assertEqual(result['per_sample'][0]['cer'],1)
        self.assertEqual(result['per_sample'][1]['cer'],2)
        self.assertAlmostEqual(result['summary']['cer'],4/3)

    def test_zero_denominators_are_null_and_missing_predictions_disclosed(self):
        data = fixture_reviews()
        row = data['records'][0]
        row['matches'] = [{'keypoint_id':'k1','expected_covered':False,'actual_covered':False}]
        data['records'] = [row]
        summary = evaluate(data)['summary']
        self.assertEqual(summary['coverage_accuracy'],1)
        self.assertIsNone(summary['precision'])
        self.assertIsNone(summary['recall'])
        self.assertIsNone(summary['f1'])
        self.assertIsNone(summary['evidence_accuracy'])
        row['matches'] = [{'keypoint_id':'k1','expected_covered':True,'actual_covered':None}]
        summary = evaluate(data)['summary']
        self.assertIsNone(summary['coverage_accuracy'])
        self.assertEqual(summary['coverage_correct_rate_all'],0)
        self.assertEqual(summary['prediction_availability'],0)
        self.assertEqual(summary['missing_predictions'],1)

    def test_exact_duplicate_removed_conflicting_task_rejected(self):
        data = fixture_reviews()
        data['records'].append(copy.deepcopy(data['records'][0]))
        result = evaluate(data)
        self.assertEqual(result['duplicates_removed'],1)
        self.assertEqual(result['summary']['observations'],5)
        data['records'][-1]['actual_text']='changed'
        with self.assertRaises(ValueError):
            evaluate(data)

    def test_split_leakage_checked_before_filter_and_versions_grouped(self):
        data = fixture_reviews()
        data['records'][0]['split']='calibration'
        data['records'][1]['topic_id']=data['records'][0]['topic_id']
        with self.assertRaises(ValueError):
            evaluate(data,split='evaluation')
        data = fixture_reviews()
        data['records'][0]['split']='calibration'
        data['records'][1]['model_version']='second-model'
        result = evaluate(data,split='evaluation')
        self.assertEqual(result['summary']['observations'],4)
        self.assertEqual(len(result['groups']),2)
        self.assertNotIn('calibration',{group['split'] for group in result['groups']})

    def test_bad_labels_missing_evidence_and_empty_reference_rejected(self):
        for change in ('string-bool','missing-evidence','duplicate-keypoint','empty-reference','contradictory-evidence'):
            data = fixture_reviews()
            row = data['records'][0]
            if change=='string-bool': row['matches'][0]['expected_covered']='false'
            elif change=='missing-evidence': del row['matches'][0]['accepted_evidence_sentence_ids']
            elif change=='duplicate-keypoint': row['matches'][1]['keypoint_id']='k1'
            elif change=='empty-reference': row['reference_text']=' ，！ '
            else: row['matches'][0]['expected_covered']=False
            with self.subTest(change=change),self.assertRaises(ValueError):
                evaluate(data)

    def test_reviewed_requires_real_review_metadata_and_cannot_relabel_fixture(self):
        data = fixture_reviews()
        with self.assertRaises(ValueError):
            evaluate(data,condition='UNREVIEWED')
        data['condition']='REVIEWED'
        with self.assertRaises(ValueError):
            evaluate(data)

    def test_legacy_array_compatible_and_strict_json(self):
        data = [{'reference_text':'甲乙','actual_text':'甲乙','matches':[]}]
        result = evaluate(data)
        self.assertTrue(result['legacy_input'])
        self.assertEqual(result['condition'],'UNREVIEWED')
        self.assertEqual(result['summary']['cer'],0)
        self.assertEqual(result['summary']['unknown_effective_input'],1)
        for value in [b'{"x":NaN}',b'{"x":1e999}',b'{"x":1,"x":2}']:
            with self.assertRaises(ValueError): strict_json(value)

    def test_invalid_only_has_no_fake_perfect_metrics(self):
        data = fixture_reviews()
        data['records']=[data['records'][-1]]
        summary = evaluate(data)['summary']
        self.assertEqual(summary['recordings'],0)
        self.assertIsNone(summary['cer'])
        self.assertIsNone(summary['coverage_accuracy'])
        self.assertIsNone(summary['evidence_accuracy'])

    def test_report_artifacts_trace_back_to_input_and_do_not_overwrite(self):
        data = fixture_reviews()
        raw = json.dumps(data,ensure_ascii=False,indent=2).encode()
        report = evaluate(data)
        report.update(input_file='fixture.json',input_sha256=hashlib.sha256(raw).hexdigest(),
                      targets={'cer_max':.2,'coverage_accuracy_min':None,'evidence_accuracy_min':None})
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'quality'
            mismatch = dict(report,input_sha256='0'*64)
            with self.assertRaises(ValueError): write_report(mismatch,output,source_bytes=raw)
            self.assertFalse(output.exists())
            write_report(report,output,source_bytes=raw)
            names = {'quality_summary.json','review_input.json','per_sample.csv','per_keypoint.csv','group_metrics.csv',
                     'cer_distribution.png','coverage_confusion.png','quality_report.md','artifact_sha256.json'}
            self.assertEqual({p.name for p in output.iterdir()},names)
            self.assertEqual((output/'review_input.json').read_bytes(),raw)
            with (output/'per_sample.csv').open(encoding='utf-8-sig') as stream:
                per_sample = list(csv.DictReader(stream))
            self.assertEqual(len(per_sample),5)
            self.assertEqual(float(per_sample[3]['cer']),2)
            self.assertEqual(per_sample[4]['cer'],'')
            text = (output/'quality_report.md').read_text('utf-8')
            self.assertIn('测试夹具数据',text)
            self.assertIn('数值未达到目标',text)
            hashes = json.loads((output/'artifact_sha256.json').read_text('utf-8'))
            for name,digest in hashes.items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),digest)
            for name in ('cer_distribution.png','coverage_confusion.png'):
                self.assertTrue((output/name).read_bytes().startswith(bytes([137,80,78,71,13,10,26,10])))
            with self.assertRaises(FileExistsError): write_report(report,output,source_bytes=raw)

    def test_reviewed_structure_does_not_imply_formal_sample_acceptance(self):
        # Pure schema/metadata fixture: no actual person or review is represented.
        data = fixture_reviews()
        data['condition']='REVIEWED'
        data['records']=data['records'][:1]
        data['records'][0].update(audio_sha256='a'*64,annotator='fixture-annotator',
            reviewer='fixture-reviewer',consent=True)
        result = evaluate(data)
        self.assertEqual(result['condition'],'REVIEWED')
        self.assertTrue(any('不足 30' in note for note in result['notes']))
        self.assertTrue(any('不代为' in note for note in result['notes']))

    def test_no_point_data_still_writes_explicit_empty_csv_and_na_report(self):
        data = fixture_reviews()
        data['records']=[data['records'][-1]]
        raw = json.dumps(data).encode()
        result = evaluate(data)
        result.update(input_file='invalid-fixture.json',input_sha256=hashlib.sha256(raw).hexdigest(),
                      targets={'cer_max':.2,'coverage_accuracy_min':None,'evidence_accuracy_min':None})
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'report'
            write_report(result,output,source_bytes=raw)
            with (output/'per_keypoint.csv').open(encoding='utf-8-sig') as stream:
                reader = csv.DictReader(stream)
                self.assertIn('expected_covered',reader.fieldnames)
                self.assertEqual(list(reader),[])
            self.assertIn('N/A',(output/'quality_report.md').read_text('utf-8'))
