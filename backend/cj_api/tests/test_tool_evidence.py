from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_app import ISSUER, scope_for
from cj_api.real_services import RealServices, RealTools, canonical_tool, _lio_tool_result
from cj_api.tool_evidence import ToolEvidence
from cj_run.operation_usage import RegisteredOperation
from cj_run.usage_binding import UsageBinding
from cj_usage.authorization_budget import AuthorizationBudget, canonical
from cj_usage.core import Command
from cj_usage.metered_exit import BudgetUnknown


NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
SUBJECT = 'm4-synthetic-evidence'
KEY = 'synthetic-evidence-key-not-live'


class ToolEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'results'
        self.directory.mkdir(mode=0o700)
        self.manifest = self.root / 'window.json'
        self.data = dict(version='G2C-tool-evidence-window.1', directory=str(self.directory),
            messages=[dict(subject=SUBJECT, message_id='original')],
            expires_at=(NOW + timedelta(hours=1)).isoformat(), source_commit='a' * 40)
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_bytes(canonical(self.data))
        self.manifest.chmod(0o600)

    def load(self):
        return ToolEvidence.load(self.manifest, frozenset({SUBJECT}), clock=lambda: NOW.timestamp())

    def operation(self, raw, *, message='original'):
        binding = SimpleNamespace(scope=scope_for(ISSUER, SUBJECT), message_id=message, run_id='original-run')
        command = Command('original-attempt', 'original-operation', binding.run_id, 'tool',
                          sha256(raw).hexdigest(), 1, 48000)
        return RegisteredOperation(binding, 'tool.0.0', 'tool.weather', 'original-ledger', (1, 2),
                                   UsageBinding.from_command(command, raw))

    def test_capture_binds_exact_input_result_and_original_receipt(self):
        evidence = self.load()
        raw = canonical(dict(private_projection_field='retained synthetic original', status='ok'))
        operation = self.operation(b'original registered input')
        receipt = dict(response_sha256=sha256(raw).hexdigest(), result_status='ok')
        evidence.record(operation, 'weather', raw, receipt)
        path, = self.directory.iterdir()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        record = json.loads(path.read_bytes())
        self.assertEqual(record['attempt_id'], operation.command.attempt_id)
        self.assertEqual(record['run_id'], operation.binding.run_id)
        self.assertEqual(record['operation_key'], operation.operation_key)
        self.assertEqual(record['input_sha256'], sha256(record['input_utf8'].encode()).hexdigest())
        self.assertEqual(record['response_sha256'], sha256(record['result_utf8'].encode()).hexdigest())
        self.assertEqual(json.loads(record['result_utf8'])['private_projection_field'], 'retained synthetic original')
        self.assertEqual(record['receipt'], receipt)
        self.assertNotIn('Authorization', path.read_text())
        before = path.read_bytes()
        with self.assertRaises(BudgetUnknown):
            evidence.record(operation, 'weather', raw, receipt)
        self.assertEqual(path.read_bytes(), before)

    def test_unselected_message_and_owner_are_not_collected(self):
        evidence = self.load()
        operation = self.operation(b'input', message='other-message')
        evidence.record(operation, 'weather', b'{}', dict(response_sha256='b' * 64))
        operation.binding.message_id = 'original'
        operation.binding.scope = scope_for(ISSUER, 'm4-synthetic-other')
        evidence.record(operation, 'weather', b'{}', dict(response_sha256='b' * 64))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_expired_selected_capture_stops_without_a_replacement(self):
        evidence = replace(self.load(), clock=lambda: (NOW + timedelta(hours=2)).timestamp())
        with self.assertRaises(BudgetUnknown):
            evidence.record(self.operation(b'input'), 'weather', b'{}', dict(response_sha256='b' * 64))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_manifest_requires_current_invited_roster_and_unique_messages(self):
        for change in (
            dict(messages=[dict(subject='m4-synthetic-uninvited', message_id='original')]),
            dict(messages=self.data['messages'] * 2),
            dict(expires_at=NOW.isoformat()),
            dict(expires_at=(NOW + timedelta(days=2)).isoformat()),
            dict(expires_at='2026-11-11T00:30:00'),
            dict(expires_at=42),
            dict(source_commit='unfixed'),
        ):
            with self.subTest(change=change):
                original = self.data
                self.data = {**original, **change}
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.load()
                self.data = original

    def test_private_owned_paths_and_duplicate_json_are_required(self):
        self.manifest.chmod(0o644)
        with self.assertRaises(ValueError):
            self.load()
        self.write_manifest()
        self.directory.chmod(0o755)
        with self.assertRaises(ValueError):
            self.load()
        self.directory.chmod(0o700)
        self.manifest.write_text('{"version":1,"version":2}')
        with self.assertRaises(ValueError):
            self.load()
        self.write_manifest()
        link = self.root / 'link.json'
        link.symlink_to(self.manifest)
        with self.assertRaises(OSError):
            ToolEvidence.load(link, frozenset({SUBJECT}))
        with patch('cj_api.tool_evidence.os.getuid', return_value=os.getuid() + 1):
            with self.assertRaises(ValueError):
                self.load()

    def test_failed_durable_capture_is_unknown(self):
        evidence = self.load()
        with patch('cj_api.tool_evidence.os.fsync', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(BudgetUnknown):
                evidence.record(self.operation(b'input'), 'weather', b'{}', dict(response_sha256='b' * 64))

    def test_real_tool_producer_is_observed_once_before_lio_projection(self):
        budget = AuthorizationBudget(self.root / 'journal', clock=lambda: NOW)
        provider = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, KEY), budget)
        services = RealServices(provider, KEY, frozenset({SUBJECT}))
        tools = RealTools(services, tool_evidence=self.load())
        name, query = canonical_tool('weather', json.dumps(dict(start_date='2026-11-11', end_date='2026-11-11')))
        prepared = tools._tool_input(name, (query, 'original-reference'))
        operation = self.operation(prepared.original_bytes)
        result = dict(status='observed', forecasts=[], source_url='https://restapi.amap.com/v3/weather/weatherInfo',
                      retrieved_at=NOW.isoformat(), provider_reporttime='UNKNOWN',
                      opaque_original='synthetic field removed by Lio projection')
        with patch('cj_api.real_services.weather', return_value=result) as external:
            raw = ''.join(prepared.bind_operation(operation, lambda: True)())
        external.assert_called_once()
        self.assertEqual(json.loads(raw), result)
        path, = self.directory.iterdir()
        captured = json.loads(path.read_bytes())
        self.assertEqual(captured['result_utf8'], raw)
        self.assertEqual(captured['input_utf8'].encode(), prepared.original_bytes)
        receipt = budget.inspect()[0]['receipt']
        self.assertEqual(receipt['response_sha256'], sha256(raw.encode()).hexdigest())
        self.assertEqual(captured['response_sha256'], receipt['response_sha256'])
        projected = _lio_tool_result(name, result, dict(title='Weather', url=None, observed_at=NOW.isoformat()),
                                    False, query)
        self.assertNotIn('opaque_original', projected)
        self.assertEqual(budget.inspect()[0]['state'], 'RECEIVED')

    def load_intake(self):
        self.data=dict(self.data,version='G2C-synthetic-evidence-window.2',kinds=['lio_intake'])
        self.write_manifest()
        return self.load()

    def intake_operation(self,raw,*,message='original'):
        original=self.operation(raw,message=message)
        command=Command(original.command.attempt_id,original.command.operation_id,original.binding.run_id,
                        'model',sha256(raw).hexdigest(),1,12000)
        return RegisteredOperation(original.binding,'model.lio_intake.0','model.lio_intake.1',original.ledger_scope,
                                   original.period,UsageBinding.from_command(command,raw))

    def test_intake_is_a_separate_model_contract_with_original_bytes_and_receipt(self):
        evidence=self.load_intake();operation=self.intake_operation(b'private original input')
        raw='{"version":"LIO-planning-intake.1","opaque":"原始失败字段"}'.encode()
        receipt=dict(model_id=M4_MODEL,receipt_sha256='c'*64,usage=dict(prompt_tokens=12,completion_tokens=6,total_tokens=18))
        evidence.record_intake(operation,raw,receipt)
        path,=self.directory.iterdir();record=json.loads(path.read_bytes())
        self.assertEqual(record['version'],'G2C-lio-intake-evidence.1')
        self.assertEqual(record['capture_kind'],'model')
        self.assertEqual(record['registration_id'],'model.lio_intake.1')
        self.assertEqual(record['result_utf8'].encode(),raw)
        self.assertEqual(record['response_sha256'],sha256(raw).hexdigest())
        self.assertEqual(record['input_sha256'],operation.command.input_digest)
        self.assertNotIn('input_utf8',record)
        self.assertEqual(record['receipt'],receipt)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        with self.assertRaises(BudgetUnknown):evidence.record_intake(operation,raw,receipt)

    def test_intake_selection_expiry_and_kind_do_not_widen_tool_capture(self):
        evidence=self.load_intake();operation=self.intake_operation(b'input',message='not-selected')
        evidence.record_intake(operation,b'{}',{})
        self.assertEqual(list(self.directory.iterdir()),[])
        operation=self.intake_operation(b'input')
        with self.assertRaises(BudgetUnknown):replace(evidence,clock=lambda:(NOW+timedelta(hours=2)).timestamp()).record_intake(operation,b'{}',{})
        with self.assertRaises(BudgetUnknown):evidence.record_intake(self.operation(b'input'),b'{}',{})
        self.assertEqual(list(self.directory.iterdir()),[])

    def test_complete_original_model_is_captured_once_after_vendor_receipt(self):
        from test_m4_real_services import sse
        budget=AuthorizationBudget(self.root/'model-journal',clock=lambda:NOW)
        import httpx
        sent=[]
        def response(request):
            sent.append(request)
            return httpx.Response(200,stream=httpx.ByteStream(sse().encode()))
        provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,transport=httpx.MockTransport(response))
        subjects=frozenset({SUBJECT})
        services=RealServices(provider,KEY,subjects,demo_subjects=subjects,national_subjects=subjects)
        tools=RealTools(services,tool_evidence=self.load_intake())
        prepared=tools._lio_intake_input(([dict(role='user',content='Synthetic original')],'JSON intake',provider))
        operation=self.intake_operation(prepared.original_bytes)
        raw=''.join(prepared.bind_operation(operation,lambda:True)())
        self.assertEqual(len(sent),1)
        self.assertEqual(budget.inspect()[0]['state'],'RECEIVED')
        path,=self.directory.iterdir();record=json.loads(path.read_bytes())
        self.assertEqual(record['result_utf8'],raw)
        self.assertEqual(record['receipt'],budget.inspect()[0]['receipt'])
        self.assertNotIn(KEY,path.read_text())

    def test_after_receipt_revocation_withholds_capture_without_redispatch(self):
        from test_m4_real_services import sse
        import httpx
        budget=AuthorizationBudget(self.root/'revoked-journal',clock=lambda:NOW);sent=[]
        def response(request):
            sent.append(request);return httpx.Response(200,stream=httpx.ByteStream(sse().encode()))
        provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,transport=httpx.MockTransport(response))
        subjects=frozenset({SUBJECT})
        tools=RealTools(RealServices(provider,KEY,subjects,demo_subjects=subjects,national_subjects=subjects),tool_evidence=self.load_intake())
        prepared=tools._lio_intake_input(([dict(role='user',content='Synthetic original')],'JSON intake',provider))
        operation=self.intake_operation(prepared.original_bytes)
        def valid():return not any(row['state']=='RECEIVED' for row in budget.inspect())
        with self.assertRaises(BudgetUnknown):''.join(prepared.bind_operation(operation,valid)())
        self.assertEqual(len(sent),1)
        self.assertEqual(budget.inspect()[0]['state'],'RECEIVED')
        self.assertEqual(list(self.directory.iterdir()),[])

    def test_incomplete_model_never_has_a_complete_intake_artifact(self):
        from test_m4_real_services import sse
        from cj_agent.provider import ProviderUnknown
        import httpx
        budget=AuthorizationBudget(self.root/'short-journal',clock=lambda:NOW)
        provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,
            transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=httpx.ByteStream(sse(done=False).encode()))))
        subjects=frozenset({SUBJECT});tools=RealTools(RealServices(provider,KEY,subjects,demo_subjects=subjects,national_subjects=subjects),tool_evidence=self.load_intake())
        prepared=tools._lio_intake_input(([dict(role='user',content='Synthetic original')],'JSON intake',provider))
        with self.assertRaises(ProviderUnknown):''.join(prepared.bind_operation(self.intake_operation(prepared.original_bytes),lambda:True)())
        self.assertEqual(list(self.directory.iterdir()),[])


    def test_old_tool_manifest_does_not_enable_model_output_capture(self):
        evidence=self.load()
        self.assertFalse(evidence.intake_enabled)
        evidence.record_intake(self.intake_operation(b'input'),b'{}',{})
        self.assertEqual(list(self.directory.iterdir()),[])
        evidence=self.load_intake()
        self.assertFalse(evidence.tools_enabled)
        evidence.record(self.operation(b'input'),'weather',b'{}',dict(response_sha256='b'*64))
        self.assertEqual(list(self.directory.iterdir()),[])

    def test_model_collection_requires_explicit_unique_supported_kinds(self):
        original=dict(self.data)
        for kinds in (None,[],['model'],['lio_intake','lio_intake'],'lio_intake'):
            with self.subTest(kinds=kinds):
                self.data=dict(original,version='G2C-synthetic-evidence-window.2',kinds=kinds)
                self.write_manifest()
                with self.assertRaises(ValueError):self.load()
        self.data=dict(original,version='G2C-synthetic-evidence-window.2')
        self.write_manifest()
        with self.assertRaises(ValueError):self.load()

    def load_runtime(self):
        self.data=dict(self.data,version='G2C-runtime-evidence-window.3',kinds=['tool','model'])
        self.write_manifest()
        return self.load()

    def test_runtime_model_artifacts_cover_original_answer_draft_reflection_and_memory(self):
        evidence=self.load_runtime()
        for index,(registration,kind) in enumerate((('model.answer','model'),('model.draft','model'),
                ('model.lio_intake.8','model'),('model.runtime_reflection.1','model'),('memory.lio_extract.1','memory'))):
            raw=b'original serialized model input';original=self.intake_operation(raw)
            command=Command('original-attempt-'+str(index),'original-operation-'+str(index),original.binding.run_id,
                            kind,sha256(raw).hexdigest(),1,12000)
            operation=RegisteredOperation(original.binding,registration,registration,original.ledger_scope,
                original.period,UsageBinding.from_command(command,raw))
            evidence.record_model(operation,b'complete original output',{'original_receipt':'synthetic'})
        records=[json.loads(path.read_bytes()) for path in self.directory.iterdir()]
        self.assertEqual(len(records),5)
        self.assertEqual({record['registration_id'] for record in records},
            {'model.answer','model.draft','model.lio_intake.8','model.runtime_reflection.1','memory.lio_extract.1'})
        for record in records:
            self.assertEqual(record['version'],'G2C-model-evidence.1')
            self.assertEqual(record['input_sha256'],sha256(record['input_utf8'].encode()).hexdigest())
            self.assertEqual(record['response_sha256'],sha256(record['result_utf8'].encode()).hexdigest())
        with self.assertRaises(BudgetUnknown):evidence.record_model(operation,b'new output',{})
        self.assertEqual(len(list(self.directory.iterdir())),5)

    def test_runtime_capture_keeps_streaming_and_requires_complete_original_receipt(self):
        from test_m4_real_services import sse
        from cj_api.real_services import ModelInput,TOOL_SYSTEM
        from cj_agent.provider import M4_NATIVE_TURN_STREAM,ProviderUnknown
        import httpx
        for complete in (True,False):
            with self.subTest(complete=complete):
                directory=self.directory/str(complete);directory.mkdir(mode=0o700)
                evidence=replace(self.load_runtime(),directory=directory)
                budget=AuthorizationBudget(self.root/('stream-'+str(complete)),clock=lambda:NOW)
                events=sse(done=complete).splitlines(keepends=True)
                first=json.loads(events[0][6:]);first['choices'][0]['delta']['content']='Visible before final usage. '*40
                events[0]='data: '+json.dumps(first)+'\n'
                sent=[]
                def response(request):
                    sent.append(request)
                    return httpx.Response(200,stream=httpx.ByteStream(''.join(events).encode()))
                provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,
                                                  transport=httpx.MockTransport(response))
                tools=RealTools(RealServices(provider,KEY,frozenset({SUBJECT})),
                                streaming_subject=SUBJECT,tool_evidence=evidence)
                argument=ModelInput([dict(role='user',content='Synthetic original')],TOOL_SYSTEM,provider,{},
                                    turn_profile=M4_NATIVE_TURN_STREAM)
                prepared=tools._model_input(argument)
                operation=replace(self.intake_operation(prepared.original_bytes),registration_id='model.tool_turn')
                stream=prepared.bind_operation(operation,lambda:True)()
                first_chunk=next(stream)
                self.assertTrue(first_chunk)
                wire_path,=directory.iterdir();wire=json.loads(wire_path.read_bytes())
                self.assertEqual(wire['version'],'G2C-model-wire-input.1')
                self.assertEqual(wire['logical_input_sha256'],operation.command.input_digest)
                self.assertEqual(wire['wire_input_utf8'].encode(),sent[0].content)
                self.assertEqual(wire['wire_input_sha256'],budget.inspect()[0]['input_sha'])
                self.assertNotIn(KEY,wire_path.read_text())
                self.assertEqual(budget.inspect()[0]['state'],'INTENT')
                if complete:
                    result=first_chunk+''.join(stream)
                    records=[json.loads(path.read_bytes()) for path in directory.iterdir()]
                    record,=[r for r in records if r['version']=='G2C-model-evidence.1']
                    self.assertEqual(record['input_utf8'].encode(),prepared.original_bytes)
                    self.assertEqual(record['result_utf8'],result)
                    self.assertEqual(record['receipt'],budget.inspect()[0]['receipt'])
                    self.assertEqual(budget.inspect()[0]['state'],'RECEIVED')
                    self.assertEqual(len(records),2)
                else:
                    with self.assertRaises(ProviderUnknown):''.join(stream)
                    self.assertEqual(list(directory.iterdir()),[wire_path])
                    self.assertEqual(budget.inspect()[0]['state'],'INTENT')
                self.assertEqual(len(sent),1)

    def test_old_windows_never_enable_generic_model_capture(self):
        for evidence in (self.load(),self.load_intake()):
            self.assertFalse(evidence.model_enabled)
            evidence.record_model(self.intake_operation(b'input'),b'output',{})
        self.assertEqual(list(self.directory.iterdir()),[])

    def test_wire_capture_failure_keeps_original_hold_and_never_sends(self):
        import httpx
        from test_m4_real_services import sse
        budget=AuthorizationBudget(self.root/'wire-failure',clock=lambda:NOW);sent=[]
        def response(request):
            sent.append(request);return httpx.Response(200,stream=httpx.ByteStream(sse().encode()))
        provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,
                                          transport=httpx.MockTransport(response))
        tools=RealTools(RealServices(provider,KEY,frozenset({SUBJECT})),tool_evidence=self.load_runtime())
        prepared=tools._model_input(([dict(role='user',content='Synthetic')],'JSON only',provider))
        operation=self.intake_operation(prepared.original_bytes)
        with patch('cj_api.tool_evidence.os.fsync',side_effect=OSError('controlled fsync loss')):
            with self.assertRaises(BudgetUnknown):''.join(prepared.bind_operation(operation,lambda:True)())
        self.assertEqual(sent,[])
        self.assertEqual(provider.calls,0)
        self.assertEqual(budget.inspect()[0]['state'],'INTENT')

    def test_v4_requires_trusted_runtime_selection_and_keeps_old_windows_narrow(self):
        old=dict(self.data)
        selector=lambda binding:True
        with self.assertRaises(ValueError):
            ToolEvidence.load(self.manifest,frozenset({SUBJECT}),clock=lambda:NOW.timestamp(),runtime_selection=selector)
        self.data={key:value for key,value in old.items() if key!='messages'}
        self.data.update(version='G2C-runtime-evidence-window.4',subjects=[SUBJECT],kinds=['tool','model'],
            expires_at=(NOW+timedelta(days=7)).isoformat())
        self.write_manifest()
        with self.assertRaises(ValueError):self.load()
        seen=[]
        def admitted(binding):
            seen.append(binding)
            if binding.message_id=='revoked':raise BudgetUnknown('original runtime auth revoked')
            return binding.message_id=='claimed-runtime-original'
        evidence=ToolEvidence.load(self.manifest,frozenset({SUBJECT}),clock=lambda:NOW.timestamp(),runtime_selection=admitted)
        original=self.operation(b'input',message='claimed-runtime-original')
        self.assertTrue(evidence.selects(original.binding))
        self.assertFalse(evidence.selects(self.operation(b'input',message='ordinary-message').binding))
        foreign=self.operation(b'input');foreign.binding.scope=scope_for(ISSUER,'other-owner')
        before=len(seen);self.assertFalse(evidence.selects(foreign.binding));self.assertEqual(len(seen),before)
        with self.assertRaises(BudgetUnknown):evidence.selects(self.operation(b'input',message='revoked').binding)
        evidence.record(original,'weather',b'{}',{'response_sha256':sha256(b'{}').hexdigest()})
        self.assertEqual(len(list(self.directory.iterdir())),1)
        self.data['expires_at']=(NOW+timedelta(days=7,seconds=1)).isoformat();self.write_manifest()
        with self.assertRaises(ValueError):
            ToolEvidence.load(self.manifest,frozenset({SUBJECT}),clock=lambda:NOW.timestamp(),runtime_selection=admitted)
