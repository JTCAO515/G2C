"""Offline HK composition checks: synthetic keys only; no actual journal/network."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('CJ_ENV','local')
import hk
import real
from cj_api.real_services import RealServices
from cj_usage.authorization_budget import HK_PRODUCER


class HKChecks(unittest.TestCase):
    def setUp(self):hk.source_manifest.cache_clear()
    def tearDown(self):hk.source_manifest.cache_clear()

    def test_source_pin_requires_external_digest_and_actual_base_and_C_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'eval').mkdir();(root/'eval/hk.py').write_text('synthetic source')
            value=dict(version=1,commit='a'*40,backend_commit='b'*40,hashes={'eval/hk.py':sha256(b'synthetic source').hexdigest()})
            raw=json.dumps(value).encode();(root/hk.MANIFEST).write_bytes(raw)
            with patch.object(hk,'ROOT',root),patch.dict(os.environ,{'CJ_DEPLOY_TARGET':'hk-beta'},clear=True):
                with self.assertRaisesRegex(ValueError,'independently_pinned'):hk.source_candidate()
                os.environ['CJ_C_EVAL_SOURCE_SHA256']=sha256(raw).hexdigest()
                self.assertEqual(hk.source_candidate(),'a'*40)
                hk.source_manifest.cache_clear();(root/'eval/hk.py').write_text('changed')
                with self.assertRaisesRegex(ValueError,'source_bytes'):hk.source_candidate()

    def test_manifest_path_escape_rejected_even_if_digest_is_pinned(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            raw=json.dumps(dict(version=1,commit='a'*40,backend_commit='b'*40,hashes={'eval/../../outside.py':'a'*64})).encode()
            (root/hk.MANIFEST).write_bytes(raw)
            with patch.object(hk,'ROOT',root),patch.dict(os.environ,{
                    'CJ_DEPLOY_TARGET':'hk-beta','CJ_C_EVAL_SOURCE_SHA256':sha256(raw).hexdigest()},clear=True):
                with self.assertRaisesRegex(ValueError,'bounded_C_source_paths'):hk.source_candidate()

    def test_HK_output_must_be_on_persistent_evidence_volume(self):
        with patch.dict(os.environ,{'CJ_DEPLOY_TARGET':'hk-beta'},clear=True):
            hk.require_output(Path('/evidence/new-stage'))
            with self.assertRaisesRegex(ValueError,'persistent_C_evidence'):hk.require_output(Path('/tmp/new-stage'))

    def test_sealed_Mac_never_reads_keys_or_constructs_a_budget(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real,'STATE',Path(folder)), \
                patch.object(real,'hk_active',return_value=False), \
                patch.object(real,'keychain',side_effect=AssertionError('no keys')), \
                patch.object(real,'AuthorizationBudget',side_effect=AssertionError('no journal')):
            (Path(folder)/'transfer.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'sealed_Mac'):real.create_real_services(frozenset())

    def test_minimal_subset_reuses_B_factory_and_keys_do_not_reach_child(self):
        class OfflineBudget:
            def __init__(self,root,*,authorization_guard):self.guard=authorization_guard
            def begin(self,*args):raise AssertionError('no real outflow')
        with tempfile.TemporaryDirectory() as folder:
            secret=Path(folder)/'c-eval.env';secret.write_text('CJ_MODEL_API_KEY=synthetic-model-key\nCJ_AMAP_WEB_KEY=synthetic-amap-key-0000\n');secret.chmod(0o600)
            env={'CJ_ENV':'local','CJ_DEPLOY_TARGET':'hk-beta','CJ_M4_SYNTHETIC_ONLY':'1','CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}
            with patch.dict(os.environ,env,clear=True),patch.object(hk,'SECRET',secret), \
                    patch('deploy.hk.configuration.authorization') as guard, \
                    patch('cj_api.real_services.AuthorizationBudget',OfflineBudget):
                services=hk.services(frozenset(('m4-synthetic-c-unit',)))
                self.assertIs(type(services),RealServices)
                self.assertEqual(services.subjects,frozenset(('m4-synthetic-c-unit',)))
                self.assertIs(services.model.authorization.guard,guard)
                self.assertFalse(hk.KEYS.intersection(os.environ))
                code='import os; print(int(any(k in os.environ for k in ("CJ_MODEL_API_KEY","CJ_AMAP_WEB_KEY"))))'
                self.assertEqual(subprocess.check_output([sys.executable,'-c',code],text=True).strip(),'0')

    def test_privileged_or_ambient_credentials_are_refused_before_secret_read(self):
        base={'CJ_ENV':'local','CJ_DEPLOY_TARGET':'hk-beta','CJ_M4_SYNTHETIC_ONLY':'1','CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}
        for name in ('CJ_SUPABASE_RUNTIME_URI','CJ_SUPABASE_CLEANUP_URI','CJ_BETA_SIGNING_PRIVATE_B64',
                     'OSS_ACCESS_KEY_ID','CJ_MODEL_API_KEY','CJ_AMAP_WEB_KEY_FILE'):
            with self.subTest(name=name),patch.dict(os.environ,dict(base,**{name:'synthetic'}),clear=True), \
                    patch('deploy.hk.configuration.authorization'), \
                    patch.object(hk.os,'open',side_effect=AssertionError('must not read secret')):
                with self.assertRaisesRegex(ValueError,'minimal_C_service_identity'):hk.services(frozenset())

    def test_secret_permissions_extra_fields_and_factory_failure_fail_closed(self):
        env={'CJ_ENV':'local','CJ_DEPLOY_TARGET':'hk-beta','CJ_M4_SYNTHETIC_ONLY':'1','CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}
        with tempfile.TemporaryDirectory() as folder:
            secret=Path(folder)/'c.env'
            normal='CJ_MODEL_API_KEY=synthetic\nCJ_AMAP_WEB_KEY=synthetic-amap-key-0000\n'
            for mode,contents,reason in ((0o644,normal,'owned_0600'),
                    (0o600,normal+'OSS_ACCESS_KEY_ID=synthetic\n','exact_two'),
                    (0o600,normal+'CJ_MODEL_API_KEY=duplicate\n','exact_two')):
                with self.subTest(reason=reason),patch.dict(os.environ,env,clear=True), \
                        patch.object(hk,'SECRET',secret),patch('deploy.hk.configuration.authorization'):
                    secret.write_text(contents);secret.chmod(mode)
                    with self.assertRaisesRegex(ValueError,reason):hk.services(frozenset())
                    self.assertFalse(hk.KEYS.intersection(os.environ))
            secret.write_text(normal);secret.chmod(0o600)
            with patch.dict(os.environ,env,clear=True),patch.object(hk,'SECRET',secret), \
                    patch('deploy.hk.configuration.authorization'), \
                    patch.object(RealServices,'from_environment',side_effect=ValueError('synthetic configuration failure')):
                with self.assertRaisesRegex(ValueError,'synthetic configuration'):hk.services(frozenset())
                self.assertFalse(hk.KEYS.intersection(os.environ))

    def test_packaged_source_excludes_worktree_secrets_and_binds_B_and_C_commits(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir();output=Path(folder)/'overlay'
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
            git('init');git('config','user.name','C synthetic test');git('config','user.email','synthetic@example.invalid')
            files={'.gitignore':'.local/\n','pyproject.toml':'[project]\n','uv.lock':'synthetic lock',
                   'backend/code.py':'synthetic B source','eval/hk.py':'synthetic C source',
                   'eval/hk.Dockerfile':'FROM synthetic','eval/scenarios.json':'[]',
                   'eval/tests/test_private.py':'excluded test','eval/reports/original.json':'excluded report',
                   'evaluation/cj028/evaluate.py':'synthetic shared report code'}
            for name,contents in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents)
            git('add','.');git('commit','--no-gpg-sign','-m','synthetic source');commit=git('rev-parse','HEAD')
            secret=root/'.local/private.env';secret.parent.mkdir();secret.write_text('SYNTHETIC_CANARY_NOT_A_KEY')
            with patch.object(hk,'ROOT',root):
                actual,digest=hk.package(output,commit)
                self.assertEqual(actual,commit)
                raw=(output/hk.MANIFEST).read_bytes();value=json.loads(raw)
                self.assertEqual(sha256(raw).hexdigest(),digest)
                self.assertEqual(value['backend_commit'],commit)
                self.assertIn('backend/code.py',value['hashes'])
                self.assertFalse((output/'backend').exists())
                self.assertFalse((output/'eval/tests').exists())
                self.assertFalse((output/'eval/reports').exists())
                self.assertTrue((output/'evaluation/cj028/evaluate.py').is_file())
                self.assertFalse(any('SYNTHETIC_CANARY' in p.read_text() for p in output.rglob('*') if p.is_file()))
                with self.assertRaisesRegex(ValueError,'new_source_context'):hk.package(output,commit)
                (root/hk.MANIFEST).write_bytes(raw)
                with patch.dict(os.environ,{'CJ_DEPLOY_TARGET':'hk-beta','CJ_C_EVAL_SOURCE_SHA256':digest},clear=True):
                    self.assertEqual(hk.source_candidate(),commit)

    def test_dirty_or_different_backend_source_never_produces_a_context(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir();output=Path(folder)/'overlay'
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
            git('init');git('config','user.name','C synthetic test');git('config','user.email','synthetic@example.invalid')
            path=root/'backend/code.py';path.parent.mkdir();path.write_text('original')
            git('add','.');git('commit','--no-gpg-sign','-m','original');original=git('rev-parse','HEAD')
            path.write_text('different')
            with patch.object(hk,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'clean_committed'):hk.package(output,original)
                git('add','.');git('commit','--no-gpg-sign','-m','different')
                with self.assertRaisesRegex(ValueError,'exact_reviewed_B_source'):hk.package(output,original)
                self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
