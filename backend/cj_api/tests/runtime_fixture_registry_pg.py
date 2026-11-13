"""Private signed AUTH + real MESSAGE row-lock controls; no paid/source qualification."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import psycopg

from cj_api.local_app import LocalDatabase,app_from_environment,ISSUER,scope_for
from cj_api.local_worker_context import checker_for
from cj_api.runtime_fixture_registry import FixtureUseRegistry,VERSION
from cj_api.runtime_fixture_originals import FixtureOriginalReferences
from cj_api.runtime_collector import RuntimeCollector
from cj_auth.interfaces import AdmissionStatus
from cj_message.auth_boundary import Boundary,AccessBlocked
from runtime_adapter import Binding,Unavailable
from runtime_adapter.contract import encode,decode
import local_history_pg as harness
import dev_auth


def exercise(auth,conninfo):
    subjects=['fixture-C','fixture-E','fixture-foreign']
    dev_auth.init(auth,subjects)
    tokens={s:dev_auth.token(auth,s,30)for s in subjects}
    database=LocalDatabase(conninfo);checker=checker_for(auth)
    with patch.dict(os.environ,{'CJ_LOCAL_AUTH_DIR':str(auth),'CJ_LOCAL_CONNINFO':str(conninfo)}):
        with TestClient(app_from_environment())as api:
            for subject in subjects:
                response=api.put('/v1/conversations',params={'conversation_id':'fixture-controls'},
                    headers={'Authorization':'Bearer '+tokens[subject]})
                assert response.status_code==200,response.text
    scope=scope_for(ISSUER,'fixture-E')
    producer=Binding(scope_for(ISSUER,'fixture-C'),sha256(tokens['fixture-C'].encode()).hexdigest(),
        'local-ledger-fixture','local-producer-fixture')
    consumer=Binding(scope,sha256(tokens['fixture-E'].encode()).hexdigest(),
        'local-ledger-fixture','local-producer-fixture')
    pins=SimpleNamespace(key='a'*64)
    # This source reference is deliberately synthetic: the test proves native
    # AUTH and admission serialization, not Trip source/cost/isolation validity.
    definition={'ref':'original-'+'b'*64,'sha256':'c'*64}
    root=auth.parent/'fixture-registry';root.mkdir(mode=0o700)
    directory=root/'reservations';directory.mkdir(mode=0o700)
    references=root/'metadata-originals';references.mkdir(mode=0o700)
    policy=root/'policy.json';policy.touch(mode=0o600)
    policy.write_bytes(encode(dict(version=VERSION,registry_id='local-registry',fixture_id='local-fixture',
        fixture_revision=1,producer_binding_sha256=producer.key,consumer_binding_sha256=consumer.key,
        baseline=dict(trip_id_sha256='d'*64,trip_version=1,content_sha256='e'*64),
        consumer_pins_sha256=pins.key,consumer_registration_ref=definition,experiment_ref=definition,
        public_release_ref=definition,batch_ids=['local-batch'],candidate_ids=['C0'],languages=['zh','en'],
        valid_from='2020-01-01T00:00:00Z',valid_until='2100-01-01T00:00:00Z',maximum_uses=3)))
    boundary=Boundary(checker,lambda p:database.message_repository(scope_for(p.issuer,p.subject)),lambda:'unused')
    selected={'token':tokens['fixture-E']}
    entered=Event()

    @contextmanager
    def admission():
        service=boundary._service(selected['token'])
        with service.repository.transaction()as tx:
            if tx.scope!=scope:raise Unavailable('ORIGINAL_MESSAGE_OWNER_CHANGED')
            entered.set()
            tx.lock_scope()
            yield

    def guard(*,read_only):
        decision=checker.check(selected['token'])
        if decision.status is not AdmissionStatus.ALLOWED:raise Unavailable('LOCAL_CONSUMER_WITHHELD')
        if scope_for(decision.principal.issuer,decision.principal.subject)!=scope:
            raise Unavailable('LOCAL_CONSUMER_OWNER_CHANGED')
        if checker.check(tokens['fixture-C']).status is not AdmissionStatus.ALLOWED:
            raise Unavailable('LOCAL_SOURCE_WITHHELD')

    def build():
        return FixtureUseRegistry(directory,policy,producer,producer,consumer,pins,guard=guard,
            source_guard=lambda:definition,admission_lock=admission,
            clock=lambda:datetime.now(timezone.utc))

    def request(attempt):
        return encode(dict(binding_sha256=consumer.key,pins_sha256=pins.key,batch_id='local-batch',
            candidate_id='C0',task_id='val-owner',language='en',attempt_id=attempt,step_id='local-step',
            request_sha256='f'*64))

    # A second native MESSAGE transaction holds the actual row; confirm the
    # waiter in PostgreSQL, rather than inferring blocking from elapsed time.
    config=json.loads(conninfo.read_bytes())
    def wait_for_row_lock(observer):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            rows=observer.execute("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' "
                "AND query LIKE 'SELECT scope FROM cj_message_scope%'").fetchone()[0]
            if rows:return
            time.sleep(.01)
        raise AssertionError('native MESSAGE waiter did not reach its row lock')

    with ThreadPoolExecutor(max_workers=2)as pool,psycopg.connect(**config,autocommit=True)as observer:
        with database.message_repository(scope).transaction()as held:
            held.lock_scope();pending=pool.submit(build().reserve,request('first'))
            assert entered.wait(10)
            wait_for_row_lock(observer)
            assert not pending.done()and not list(directory.iterdir())
        assert pending.result(timeout=10)['ordinal']==1
        results=list(pool.map(lambda _:build().reserve(request('second')),range(2)))
        assert results[0]==results[1]and results[0]['ordinal']==2
        assert len(list(directory.iterdir()))==2
        originals=FixtureOriginalReferences(references,build(),request('first'))
        policy_ref=originals.issue(tokens['fixture-E'],'registry')
        reservation_ref=originals.issue(tokens['fixture-E'],'reservation')
        assert originals.resolve(tokens['fixture-E'],policy_ref['ref'])==policy.read_bytes()
        assert decode(originals.resolve(tokens['fixture-E'],reservation_ref['ref']))==build().read(request('first'))
        second=FixtureOriginalReferences(references,build(),request('second'))
        assert second.issue(tokens['fixture-E'],'registry')==policy_ref
        assert second.issue(tokens['fixture-E'],'reservation')!=reservation_ref
        assert len(list(directory.iterdir()))==2
        legacy=root/'legacy-refs';legacy.mkdir(mode=0o700)
        collector=RuntimeCollector(None,SimpleNamespace(binding=consumer),None,lambda:tokens['fixture-E'],
            pins,legacy,guard=build().guard,state_reader=None,model_reader=None,
            fixture_originals=FixtureOriginalReferences(references,build()))
        assert decode(collector.original(reservation_ref['ref'],deadline=time.monotonic()+30))==build().read(request('first'))
        try:originals.resolve(tokens['fixture-foreign'],reservation_ref['ref'])
        except Unavailable:pass
        else:raise AssertionError('foreign session resolved an original metadata source')
        selected['token']=tokens['fixture-foreign']
        try:build().read(request('first'))
        except Unavailable:pass
        else:raise AssertionError('foreign owner read original reservation')
        selected['token']=tokens['fixture-E']
        entered.clear()
        with database.message_repository(scope).transaction()as held:
            held.lock_scope();pending=pool.submit(build().reserve,request('third'))
            assert entered.wait(10)
            wait_for_row_lock(observer)
            (auth/'invited.json').write_text(json.dumps(['fixture-C','fixture-foreign']))
        try:pending.result(timeout=10)
        except (Unavailable,AccessBlocked):pass
        else:raise AssertionError('revoked waiter reserved a new use')
        assert len(list(directory.iterdir()))==2
        try:build().read(request('first'))
        except Unavailable:pass
        else:raise AssertionError('revoked consumer read an original reservation')
        try:originals.resolve(tokens['fixture-E'],reservation_ref['ref'])
        except Unavailable:pass
        else:raise AssertionError('revoked consumer resolved a saved reference')
        (auth/'invited.json').write_text(json.dumps(['fixture-E','fixture-foreign']))
        try:build().read(request('first'))
        except Unavailable:pass
        else:raise AssertionError('withdrawn source returned an original reservation')
        try:originals.resolve(tokens['fixture-E'],policy_ref['ref'])
        except Unavailable:pass
        else:raise AssertionError('withdrawn producer returned cached policy metadata')
        try:collector.original(policy_ref['ref'],deadline=time.monotonic()+30)
        except Unavailable:pass
        else:raise AssertionError('collector exposed withdrawn producer metadata')
    print('PASS private PG signed owner/foreign/revoked AUTH, native MESSAGE row waiter, '
        'idempotent concurrent reservation, actual registry/reservation originals and withdrawn refs withheld; '
        'full source/cost/isolation/paid execution UNRUN')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
