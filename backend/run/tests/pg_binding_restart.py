"""Read same original row after explicit clean restart; never dispatch."""
from dataclasses import replace
from pg_binding_checks import connect, repository, UsageFixture, Config, Meter, Command, SyntheticFirstStep, ReconcileOriginal
from cj_run.core import Binding, Service, Event, Conflict
scope='__main__.BindingPgTests.test_claim_unknown_blocks_replacement_after_reconstruction'
binding=Binding(scope,'chat','g','m','r',1)
with connect() as c:
    assert c.execute('SHOW listen_addresses').fetchone()[0]==''
run=Service(repository(scope),lambda _:True)
state=run.snapshot(binding)
assert state.status=='queued'
assert state.usage.input_bytes==b'{ "fixture_outbound" : true }\n'
original=Command(**state.usage.values())
assert (original.attempt_id,original.operation_id,original.run_id)==('a','original-operation','r')
usage=UsageFixture()
meter=Meter(usage,Config('synthetic-unit',100,0,1000,10,10,100,100),lambda:10)
calls=[]
for command in (original,replace(original,attempt_id='replacement')):
    adapter=SyntheticFirstStep(run,meter,original_binding=binding,original_command=command,
                               original_input_bytes=state.usage.input_bytes,synthetic_executor=lambda c:calls.append(c))
    try:
        adapter.create_fixture()
    except Conflict:
        pass
    else:
        raise AssertionError('existing row granted a new invocation')
    try:
        adapter.execute_fixture(binding,command,Event(binding,1,'start','started'))
    except (Conflict,ReconcileOriginal):
        pass
    else:
        raise AssertionError('recovered instance executed')
assert calls==[] and usage.ledger.attempts=={}
print('PASS: real PG clean restart + fresh Python process preserves command/input bytes; original/replacement attempts cannot re-arm; zero reserve/claim/executor')
print('UNRUN: real USAGE persistence, crash/power-loss recovery, AUTH and shared cross-domain exit fence')
