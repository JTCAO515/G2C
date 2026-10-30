"""Accepted MESSAGE → actual FACT source/parser/Meter → original RUN, synthetic L1."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import psycopg
from cj_api.local_fact_tools import LocalFactTools, SyntheticFactModel
from cj_api.local_worker_context import LocalBudgetRouter
from cj_api.local_app import ISSUER,scope_for
from cj_fact.contract_v1 import decode_result,dump
from cj_usage.core import Meter
import local_history_pg as harness
sys.path.insert(0,str(harness.ROOT/'scripts'))
from registered_host_support import RegisteredHost

AT=datetime(2026,10,30,10,tzinfo=timezone.utc)
PROMPT='合成城市天气 / synthetic-city weather 2026-10-30 Asia/Shanghai '


def tools():
    value=LocalFactTools()
    value.fact.clock=lambda:AT
    return value


def exercise(auth,conninfo):
    subjects=['alice','bob','expired','conflict','unknown','missing','injection','rate','malformed',
              'oversize','redirect','timeout','steps','tools','output','revoke','deadline','cancel','cli','invalid','future','clarify']
    limits={s:(1 if s=='steps' else 8,1 if s=='tools' else 2,16 if s=='output' else 50000) for s in subjects}
    host=RegisteredHost(auth,conninfo,limits)
    with host.api('alice') as client:
        receipt=host.send(client,'alice','positive',PROMPT)
        producer=tools();model=SyntheticFactModel();worker=host.worker('alice',model,producer)
        assert worker.process()[0].status=='completed'
        assert model.calls==2 and producer.fact.invocations==producer.fact.transport_calls==1
        snapshot=host.display(client,'alice','positive')
        frames=[json.loads(line) for line in snapshot['text'].splitlines()]
        assert [v['version'] for v in frames]==['FACT-output.1','FACT-answer.1']
        value=decode_result(dump(frames[0]['result']))
        assert frames[0]['data_origin']==value['data_origin']=='synthetic'
        assert value['status']=='supported' and 'NOT a real forecast' in value['original_value']
        assert value['sources'][0]['declarations']['conditions']=={'calendar_timezone':'Asia/Shanghai'}
        assert '合成资料' in frames[1]['text_zh'] and 'Synthetic' in frames[1]['text_en']
        harness.expect(client.get('/v1/run-display',params={'message_id':'positive'},headers=host.headers['bob']),503)
        original=host.ledger('alice')
        assert worker.process()==[] and model.calls==2 and producer.fact.invocations==1
        assert host.ledger('alice')==original and Meter.exposure(original)==3
    for subject,status,outcome in [('expired','expired','ok'),('conflict','conflicting','ok'),
        ('unknown','unknown','ok'),('missing','unknown','no_results'),('injection','supported','ok'),
        ('rate','unknown','rate_limited'),('malformed','unknown','invalid_response'),
        ('oversize','unknown','invalid_response'),('redirect','unknown','invalid_response')]:
        with host.api(subject) as client:
            host.send(client,subject,subject,PROMPT+'SYNTH_'+subject.upper())
            producer=tools();model=SyntheticFactModel()
            assert host.worker(subject,model,producer).process()[0].status=='completed'
            assert producer.fact.invocations==1 and model.calls==2
            snapshot=host.display(client,subject,subject)
            frames=[json.loads(line) for line in snapshot['text'].splitlines()]
            value=decode_result(dump(frames[0]['result']))
            assert (value['status'],value['outcome'])==(status,outcome)
            if status!='supported':assert value['original_value'] is None
            assert frames[1]['text_zh'] and frames[1]['text_en']
            assert 'SYNTHETIC_PRIVATE_FACT_SENTINEL' not in snapshot['text']
    with host.api('future') as client:
        host.send(client,'future','future',PROMPT.replace('2026-10-30','2026-11-10'))
        producer=tools();model=SyntheticFactModel()
        assert host.worker('future',model,producer).process()[0].status=='completed'
        value=json.loads(host.display(client,'future','future')['text'].splitlines()[0])['result']
        assert value['status']=='unsupported_or_out_of_range' and value['original_value'] is None
        assert model.calls==2 and producer.fact.invocations==1
    with host.api('clarify') as client:
        host.send(client,'clarify','clarify','synthetic-city weather')
        producer=tools();model=SyntheticFactModel()
        assert host.worker('clarify',model,producer).process()[0].status=='completed'
        frames=[json.loads(l) for l in host.display(client,'clarify','clarify')['text'].splitlines()]
        assert [f['version'] for f in frames]==['FACT-answer.1']
        assert 'Specify' in frames[0]['text_en'] and producer.fact.invocations==0 and model.calls==1
    for subject in ('steps','output'):
        with host.api(subject) as client:
            host.send(client,subject,subject,PROMPT)
            producer=tools();model=SyntheticFactModel()
            assert host.worker(subject,model,producer).process()[0].status=='failed'
            assert model.calls==1 and producer.fact.invocations==(0 if subject=='steps' else 1)
            assert host.status(client,subject,subject)['budget_exhausted_stage']=='answer'
    class DoubleModel(SyntheticFactModel):
        def stream(self,messages,system=None):
            for chunk in super().stream(messages,system=system):
                value=json.loads(chunk)
                if value.get('kind')=='tool':value['calls']*=2
                yield json.dumps(value,ensure_ascii=False)
    with host.api('tools') as client:
        host.send(client,'tools','tools',PROMPT)
        producer=tools();model=DoubleModel()
        assert host.worker('tools',model,producer).process()[0].status=='failed'
        assert model.calls==1 and producer.fact.invocations==1
    with host.api('revoke') as client:
        host.send(client,'revoke','revoke',PROMPT)
        producer=tools();model=SyntheticFactModel();prepare=producer.fact.prepare_call
        def revoke(query,ref):
            invoke=prepare(query,ref)
            (auth/'invited.json').write_text(json.dumps([s for s in subjects if s!='revoke']))
            return invoke
        producer.fact.prepare_call=revoke
        try:assert host.worker('revoke',model,producer).process()[0].status=='context_invalid'
        finally:(auth/'invited.json').write_text(json.dumps(subjects))
        assert producer.fact.invocations==0 and model.calls==1 and Meter.exposure(host.ledger('revoke'))==2
    with host.api('deadline') as client:
        host.send(client,'deadline','deadline',PROMPT)
        offset=[0];resolve=LocalBudgetRouter._resolve_original
        def timed(router,binding,state):
            value=resolve(router,binding,state);value.clock=lambda:time.time()+offset[0];return value
        producer=tools();model=SyntheticFactModel();prepare=producer.fact.prepare_call
        def late(query,ref):
            invoke=prepare(query,ref);offset[0]=601;return invoke
        producer.fact.prepare_call=late
        with patch.object(LocalBudgetRouter,'_resolve_original',timed):
            assert host.worker('deadline',model,producer).process()[0].status=='failed'
        assert producer.fact.invocations==0 and model.calls==1 and Meter.exposure(host.ledger('deadline'))==2
    with host.api('cancel') as client:
        host.send(client,'cancel','cancel',PROMPT)
        class CancellingModel(SyntheticFactModel):
            def stream(self,messages,system=None):
                if messages[-1]['role']!='tool':
                    yield from super().stream(messages,system=system);return
                self.calls+=1
                yield '{'
                value=harness.expect(client.post('/v1/run-cancellations',json={'version':'RUN-cancel.1','message_id':'cancel'},headers=host.headers['cancel']))
                assert value['status']=='cancelled'
                yield 'SYNTHETIC_LATE_FACT_ANSWER'
        producer=tools();model=CancellingModel()
        assert host.worker('cancel',model,producer).process()[0].status=='cancelled'
        snapshot=host.display(client,'cancel','cancel')
        assert [json.loads(l)['version'] for l in snapshot['text'].splitlines()]==['FACT-output.1']
        assert 'SYNTHETIC_LATE_FACT_ANSWER' not in snapshot['text']
        assert Meter.exposure(host.ledger('cancel'))==3
    with host.api('timeout') as client:
        host.send(client,'timeout','timeout',PROMPT+'SYNTH_TIMEOUT')
        producer=tools();model=SyntheticFactModel();worker=host.worker('timeout',model,producer)
        assert worker.process()[0].status=='unknown' and producer.fact.invocations==producer.fact.transport_calls==1
        assert model.calls==1 and Meter.exposure(host.ledger('timeout'))==2
        ledger=host.ledger('timeout')
        assert host.worker('timeout',model,tools()).process()==[] and host.ledger('timeout')==ledger
    class InvalidModel(SyntheticFactModel):
        def stream(self,messages,system=None):
            for chunk in super().stream(messages,system=system):
                value=json.loads(chunk)
                if value.get('kind')=='tool':value['calls'][0]['arguments']['owner']='foreign'
                yield json.dumps(value,ensure_ascii=False)
    with host.api('invalid') as client:
        host.send(client,'invalid','invalid',PROMPT)
        producer=tools();model=InvalidModel()
        assert host.worker('invalid',model,producer).process()[0].status=='unknown'
        assert model.calls==1 and producer.fact.invocations==0 and Meter.exposure(host.ledger('invalid'))==1
    # Actual CLI profile is mandatory in the default group, never replaced with a callback.
    with host.api('cli') as client:
        today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        host.send(client,'cli','cli','synthetic-city weather '+today+' Asia/Shanghai')
        completed=subprocess.run([sys.executable,'-B',str(harness.ROOT/'scripts/run_worker.py'),
            '--conninfo-json',str(conninfo),'--auth-dir',str(auth),'--run-context',str(host.profiles['cli'][0]),
            '--tools-profile','synthetic-fact-v1','--once'],env=dict(os.environ),capture_output=True,text=True,timeout=30)
        assert completed.returncode==0,(completed.stdout,completed.stderr)
        assert 'local_provider_calls=2' in completed.stdout
        snapshot=host.display(client,'cli','cli')
        assert snapshot['status']=='completed'
        assert json.loads(snapshot['text'].splitlines()[0])['name']=='fact'
        assert 'SYNTHETIC_PRIVATE_FACT_SENTINEL' not in completed.stdout+completed.stderr
    with psycopg.connect(**json.loads(conninfo.read_text())) as observer:
        rows=observer.execute('SELECT kind,registration_id,operation_key FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s ORDER BY operation_key',
            (scope_for(ISSUER,'alice'),receipt['run_id'])).fetchall()
        assert rows==[('model','model.tool_turn','model.tool_turn.0'),('model','model.tool_turn','model.tool_turn.1'),('tool','tool.fact','tool.0.0')],rows
    print('PASS actual signed MESSAGE/model-FACT-model/one Meter/source readback/CLI; step/tool/output/time, revocation, cancellation, original UNKNOWN/exposure; synthetic data only')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
