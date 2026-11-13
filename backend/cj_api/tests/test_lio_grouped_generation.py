"""Original registered draft identity, declared format and supplier wire agree."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import httpx

from cj_agent.provider import DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL, ProviderUnknown
from cj_agent.worker import RunWorker
from cj_api.local_app import ISSUER, scope_for
from cj_api.real_services import RealServices, RealTools
from cj_draft.grouped_plan import (GENERATION_PROFILES, LioGroupedCalendarPublisher, LioGroupedPlanPublisher,
    grouped_input, response_format, response_format_sha256, system_for)
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.local_provider_exit import BudgetUnknown


class GroupedGeneration(unittest.TestCase):
    def packet(self, provider, *, ordinal=False, retained=False):
        cls=LioGroupedCalendarPublisher if ordinal else LioGroupedPlanPublisher
        host=cls.__new__(cls);host.source=SimpleNamespace(contexts={'original':object() if retained else None})
        host.system=system_for(retained=retained,ordinal=ordinal)
        return grouped_input(host,SimpleNamespace(binding='original'),[dict(role='user',content='Plan three days')],provider)

    def setup_model(self, folder, *, reject=False):
        journal=AuthorizationBudget(Path(folder)/'journal',clock=lambda:datetime(2026,11,9,tzinfo=timezone.utc))
        sent=[]
        def respond(request):
            body=json.loads(request.content);sent.append(body)
            if reject:return httpx.Response(400,json=dict(error=dict(code='invalid_response_format')))
            profile=body['response_format']['json_schema']['schema']['properties']['version']['const']
            ordinal=profile in GENERATION_PROFILES[2:];retained=profile in (GENERATION_PROFILES[1],GENERATION_PROFILES[3])
            value=dict(version=profile,days=[[1 if ordinal else'2026-12-01', [['a','Museum','14:00','15:00',['self']]]]])
            if not retained:value['title']='Trip'
            common=dict(id='fixture-grouped',model=M4_MODEL)
            events=[dict(**common,choices=[dict(index=0,delta=dict(content=json.dumps(value)),finish_reason=None)]),
                dict(**common,choices=[dict(index=0,delta={},finish_reason='stop')]),
                dict(**common,choices=[],usage=dict(prompt_tokens=40,completion_tokens=10,total_tokens=50))]
            raw=''.join('data: '+json.dumps(event)+'\n\n'for event in events)+'data: [DONE]\n\n'
            return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
        provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'offline-only',max_output_tokens=1536),
            journal,transport=httpx.MockTransport(respond))
        subjects=frozenset({'m4-synthetic-one','m4-synthetic-two'})
        tools=RealTools(RealServices(provider,'offline-grouped-key-only',subjects,demo_subjects=subjects,
            national_subjects=frozenset({'m4-synthetic-one'})))
        return provider,tools,journal,sent

    def test_canonical_schema_matches_actual_wire_and_old_registration_stays_unchanged(self):
        for ordinal in (False,True):
            for retained in (False,True):
                with self.subTest(ordinal=ordinal,retained=retained),tempfile.TemporaryDirectory() as folder:
                    provider,tools,journal,sent=self.setup_model(folder)
                    packet=self.packet(provider,ordinal=ordinal,retained=retained)
                    prepared=tools.registrations['model.draft'].prepare_input(packet)
                    declared=json.loads(prepared.original_bytes)
                    self.assertEqual(declared['draft_profile'],packet.profile)
                    self.assertEqual(declared['response_format_sha256'],response_format_sha256(packet.profile))
                    operation=SimpleNamespace(binding=SimpleNamespace(scope=scope_for(ISSUER,'m4-synthetic-one')),command=SimpleNamespace(attempt_id='one-original'))
                    result=''.join(prepared.bind_operation(operation,lambda:True)())
                    self.assertEqual(json.loads(result)['version'],packet.profile)
                    self.assertEqual(sent[0]['response_format'],response_format(packet.profile))
                    self.assertEqual(sent[0]['max_tokens'],1024)
                    self.assertEqual(len(sent),1)
                    self.assertEqual(journal.inspect()[0]['state'],'RECEIVED')
                    legacy=tools.registrations['model.draft'].prepare_input((packet.messages,packet.system,provider))
                    old=json.loads(legacy.original_bytes)
                    self.assertNotIn('draft_profile',old);self.assertNotIn('response_format_sha256',old)

    def test_nonnational_scope_cannot_dispatch_a_typed_grouped_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            provider,tools,journal,sent=self.setup_model(folder)
            prepared=tools.registrations['model.draft'].prepare_input(self.packet(provider))
            operation=SimpleNamespace(binding=SimpleNamespace(scope=scope_for(ISSUER,'m4-synthetic-two')),command=SimpleNamespace(attempt_id='denied'))
            with self.assertRaises(BudgetUnknown):prepared.bind_operation(operation,lambda:True)
            self.assertEqual(sent,[]);self.assertEqual(journal.inspect(),[])

    def test_supplier_rejection_does_not_fallback_or_redispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            provider,tools,journal,sent=self.setup_model(folder,reject=True)
            packet=self.packet(provider)
            prepared=tools.registrations['model.draft'].prepare_input(packet)
            operation=SimpleNamespace(binding=SimpleNamespace(scope=scope_for(ISSUER,'m4-synthetic-one')),command=SimpleNamespace(attempt_id='one-rejected-original'))
            with self.assertRaises(ProviderUnknown):list(prepared.bind_operation(operation,lambda:True)())
            self.assertEqual(len(sent),1);self.assertEqual(sent[0]['response_format'],response_format(packet.profile))
            self.assertEqual(sent[0]['max_tokens'],1024)
            self.assertEqual(len(journal.inspect()),1)
            self.assertEqual(journal.inspect()[0]['state'],'INTENT')

    def test_worker_preserves_original_draft_key_registration_and_stage(self):
        calls=[];provider=object();packet=self.packet(provider)
        class Exit:
            def prepare_operation(self,runs,binding,key,registration,argument,*,stage):
                calls.append((key,registration,argument,stage));return 'prepared'
            def stream(self,prepared):
                self.prepared=prepared;yield 'result'
        class Worker:
            budget_exit=Exit();runs=object()
            def _model_history(self,binding,messages,system):calls.append((messages,system))
            def _stream_source(self,binding,source,*,draft):
                self.draft=draft;yield from source()
        worker=Worker();worker.provider=provider
        self.assertEqual(''.join(RunWorker._stream(worker,'binding',[],system='later mutable system',grouped_input=packet)),'result')
        self.assertEqual(calls[0],(packet.messages,packet.system))
        self.assertEqual(calls[1],('model.draft','model.draft',packet,'draft'))
        self.assertTrue(worker.draft)


if __name__=='__main__':unittest.main()
