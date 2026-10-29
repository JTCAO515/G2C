"""Real formal local draft-outcome read and non-destructive rollback acceptance."""
import json
import uuid
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_agent.worker import RunWorker, original_context_valid
from cj_agent.draft import DraftPublisher
from cj_agent.provider import ProviderFailed, ProviderUnknown
from cj_message.domain import Service as MessageService
from cj_run.core import Service as RunService, Binding, Event, Conflict
from cj_run.display_snapshot import DisplaySnapshotReader
import local_history_pg as harness


class Provider:
    def __init__(self, failure): self.failure = failure
    def stream(self, messages, system=None):
        if system is None:
            yield 'answer remains complete'
        elif self.failure == 'validation_failed':
            yield '{"invalid":"draft"}'
        elif self.failure == 'provider_failed': raise ProviderFailed()
        elif self.failure == 'provider_unknown': raise ProviderUnknown()
        else: yield '{"title":"Beijing","items":["pending visit"]}'


def exercise(auth, conninfo):
    harness.dev_auth.init(auth, ['alice', 'bob'])
    headers = {s: {'Authorization': 'Bearer ' + harness.dev_auth.token(auth, s, 30)} for s in ('alice', 'bob')}
    with patch.dict('os.environ', {'CJ_LOCAL_AUTH_DIR': str(auth), 'CJ_LOCAL_CONNINFO': str(conninfo)}):
        database = LocalDatabase(conninfo)
        scope = scope_for(ISSUER, 'alice')
        with TestClient(app_from_environment()) as client:
            for expected in ('validation_failed', 'provider_failed', 'provider_unknown', 'published', 'not_requested', 'not_recorded'):
                cid, mid = 'chat-' + uuid.uuid4().hex, 'message-' + uuid.uuid4().hex
                opened = harness.expect(client.put('/v1/conversations', params={'conversation_id':cid}, headers=headers['alice']))
                raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id=cid, message_id=mid,
                    text='Beijing', trip_id=None, creation_intent='none' if expected=='not_requested' else 'consider_trip',
                    expected_generation=opened['generation'], expected_sequence=0)).encode()
                receipt = harness.expect(client.post('/v1/messages', content=raw,
                    headers={**headers['alice'], 'Content-Type':'application/octet-stream'}))['receipt']
                messages = MessageService(database.message_repository(scope), lambda: None)
                runs = RunService(database.run_repository(scope), lambda b: original_context_valid(b, messages, lambda: True))
                worker = RunWorker(scope=scope, messages=messages, runs=runs, provider=Provider(expected),
                    drafts=DraftPublisher(database.trip_repository(scope)))
                if expected == 'not_recorded':
                    binding = Binding(scope, cid, opened['generation'], mid, receipt['run_id'], receipt['sequence'])
                    runs.accept(binding)
                    runs.apply(Event(binding, 1, 'legacy-start', 'started'))
                    runs.apply(Event(binding, 2, 'legacy-completed', 'completed'))
                else:
                    result = worker.process()[0]
                    assert result.status == 'completed' 
                with TestClient(app_from_environment()) as rebuilt:
                    response = harness.expect(rebuilt.get('/v1/run-draft-status', params={'message_id':mid}, headers=headers['alice']))
                    assert (response['draft_outcome'], response['run_status'], response['version']) == (expected,'completed','RUN-draft-status.1'), response
                    assert response['message_id']==mid and response['run_id']==receipt['run_id']
                    harness.expect(rebuilt.get('/v1/run-draft-status', params={'message_id':mid}, headers=headers['bob']),503)
                    display = harness.expect(rebuilt.get('/v1/run-display', params={'message_id':mid}, headers=headers['alice']))
                    # Generated envelope has the original nine-field snapshot only.
                    snapshot = display['snapshot']
                    assert snapshot['text']==('' if expected=='not_recorded' else 'answer remains complete') and snapshot['text_state']=='complete'
                    assert 'draft_outcome' not in snapshot and len(snapshot)==9
                if expected.endswith('failed') or expected=='provider_unknown':
                    with database.connect(scope) as connection:
                        assert connection.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0]==0
                        assert connection.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND kind='effect_committed'",(receipt['run_id'],)).fetchone()[0]==0
            # The publication guard must run BEFORE the real TRIP callback.
            guarded_id = 'guard-' + uuid.uuid4().hex
            opened = harness.expect(client.put('/v1/conversations', params={'conversation_id':guarded_id}, headers=headers['alice']))
            raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id=guarded_id, message_id=guarded_id,
                text='guard',trip_id=None,creation_intent='consider_trip',expected_generation=opened['generation'],expected_sequence=0)).encode()
            guarded = harness.expect(client.post('/v1/messages', content=raw,
                headers={**headers['alice'],'Content-Type':'application/octet-stream'}))['receipt']
            binding = Binding(scope, guarded_id, opened['generation'], guarded_id, guarded['run_id'], guarded['sequence'])
            runs.accept(binding)
            runs.apply(Event(binding,1,'guard-start','started'))
            runs.apply(Event(binding,2,'guard-outcome','draft_outcome','provider_unknown'))
            invoked = []
            def publish():
                invoked.append(True)
                return DraftPublisher(database.trip_repository(scope)).publish(guarded['run_id'], '{"title":"forbidden","items":["x"]}')
            try: worker._step(binding,publish,lambda draft:'trip_proposal:'+draft.proposal_id,draft=True)
            except Conflict: pass
            else: raise AssertionError('publication must be fenced')
            assert invoked == []
            with database.connect(scope) as connection:
                assert connection.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',('p-'+guarded['run_id'],)).fetchone()[0]==0

            # Withdraw invitation after encoding, before the original final guards.
            original_read = DisplaySnapshotReader._read_materialized
            def revoke_after_encoding(reader, token, message_id, encode):
                def encoded_then_revoke(state, original):
                    body = encode(state, original)
                    (auth / 'invited.json').write_text('["bob"]')
                    return body
                return original_read(reader, token, message_id, encoded_then_revoke)
            try:
                with patch.object(DisplaySnapshotReader, '_read_materialized', revoke_after_encoding):
                    response = client.get('/v1/run-draft-status', params={'message_id':mid}, headers=headers['alice'])
                    assert response.status_code != 200 and 'draft_outcome' not in response.json()
            finally:
                (auth / 'invited.json').write_text('["alice","bob"]')

            # An initialization identity verifies refusal, never deletes event rows.
            with psycopg.connect(**json.loads(conninfo.read_text()), autocommit=True) as connection:
                before = connection.execute('SELECT count(*) FROM cj_run_event').fetchone()[0]
                for value in ('', 'published', 'arbitrary'):
                    try:
                        connection.execute("INSERT INTO cj_run_event(scope,run_id,sequence,event_id,kind,value) VALUES (%s,%s,99,'invalid','draft_outcome',%s)", (scope, receipt['run_id'], value))
                    except psycopg.errors.CheckViolation: pass
                    else: raise AssertionError('SQL must reject invalid draft outcome')
                try: harness.migrate.down(connection, harness.migrate.load(), 12)
                except psycopg.errors.RaiseException: pass
                else: raise AssertionError('rollback must refuse recorded draft outcomes')
                assert 13 in harness.migrate.applied(connection)
                assert connection.execute('SELECT count(*) FROM cj_run_event').fetchone()[0]==before
            print('PASS persisted outcomes, formal protected reads, original answer, cross-account rejection, rollback refusal')


if __name__ == '__main__':
    harness.exercise = exercise
    harness.main()
