import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave
from jsonschema import Draft202012Validator, ValidationError
from experiments.scripts.mobile_experiment import build_run, validate_export, RUN_SCHEMA


def write_fixture_assets(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    samples = []
    for name, effective, pcm in [('valid',True,b'\x01\x00'*1600),('silence',False,bytes(3200))]:
        path = directory/(name+'.wav')
        with wave.open(str(path),'wb') as audio:
            audio.setparams((1,2,16000,0,'NONE','not compressed'))
            audio.writeframes(pcm)
        samples.append({'sample_id':'fixture-'+name,'topic_id':'fixture-topic-'+name,'split':'calibration',
            'wav_path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'effective_input':effective,
            'reference_text':'','annotator':'','reviewer':'','consent':False,
            'keypoints':[{'keypoint_id':'k1','text':'固定协议测试要点','expected_covered':None}]})
    samples_bytes = json.dumps(samples,ensure_ascii=False,indent=2).encode()
    (directory/'samples.json').write_bytes(samples_bytes)
    manifest = {'model_version':'model-fixture','config_version':'rules-fixture'}
    manifest_bytes = json.dumps(manifest).encode()
    (directory/'manifest.json').write_bytes(manifest_bytes)
    info = {'device_info_schema_version':1,'device':{'device_id':'jvm-fixture','model':'JVM fixture',
        'android_version':None,'abi':None,'power_mode':None,'charging':None,'battery_percent':None,'temperature_c':None},
        'runtime':{'apk_commit':'a'*40,'apk_version':'0.2.0','model_version':'model-fixture','config_version':'rules-fixture',
            'model_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()}}
    (directory/'device-info.json').write_text(json.dumps(info,ensure_ascii=False),'utf-8')
    for mode in ['LOCAL','REMOTE','MANUAL_MIXED']:
        run = build_run(info,manifest_bytes,samples_bytes,run_id='fixture-'+mode,mode=mode,duration_s=.1)
        (directory/(mode+'.json')).write_text(json.dumps(run,ensure_ascii=False,indent=2),'utf-8')
    return info,manifest_bytes,samples_bytes


class MobileExperimentTests(unittest.TestCase):
    def test_generated_three_modes_validate_and_bind_exact_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            info,model,samples = write_fixture_assets(folder)
            for mode in ['LOCAL','REMOTE','MANUAL_MIXED']:
                row = json.loads((Path(folder)/(mode+'.json')).read_text('utf-8'))
                Draft202012Validator(RUN_SCHEMA).validate(row)
                self.assertEqual(row['input']['sample_manifest_sha256'],hashlib.sha256(samples).hexdigest())
                self.assertEqual(row['runtime']['mode'],mode)
                self.assertEqual(row['condition'],'FIXTURE')

    def test_rejects_mode_ownership_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            write_fixture_assets(folder)
            row = json.loads((Path(folder)/'LOCAL.json').read_text('utf-8'))
            row['runtime']['remote_modules']=['M2']
            with self.assertRaises(ValidationError):
                Draft202012Validator(RUN_SCHEMA).validate(row)

    def test_model_manifest_must_match_exported_device(self):
        with tempfile.TemporaryDirectory() as folder:
            info,model,samples = write_fixture_assets(folder)
            info['runtime']['model_manifest_sha256']='0'*64
            with self.assertRaises(ValueError):
                build_run(info,model,samples,run_id='wrong-model')

    def test_formal_cannot_relabel_two_unreviewed_fixtures(self):
        with tempfile.TemporaryDirectory() as folder:
            info,model,samples = write_fixture_assets(folder)
            with self.assertRaises(ValueError):
                build_run(info,model,samples,run_id='not-formal',condition='FORMAL')

    def test_multiple_keypoint_counts_can_share_one_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            info,model,samples = write_fixture_assets(folder)
            values = json.loads(samples)
            values[1]['keypoints'].append({'keypoint_id':'k2','text':'第二个测试要点'})
            data = json.dumps(values).encode()
            row = build_run(info,model,data,run_id='two-points',keypoint_count=2)
            self.assertEqual(row['input']['keypoint_count'],2)
            self.assertEqual(row['input']['sample_manifest_sha256'],hashlib.sha256(data).hexdigest())
