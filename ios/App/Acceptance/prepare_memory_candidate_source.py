"""Prepare a genuine #460 candidate with signed API, automatic C intake and Meter.

This is source preparation for native acceptance, not an App/native PASS. The
App must discover the producer itself through V5; no job/attempt/candidate ID is
an environment input. All data and credentials are fresh task-private local data.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid


def build_source_host(connection, auth, context, subjects, token):
    from cj_agent.provider import FakeProvider
    from cj_api.local_background import LocalBackgroundHost
    from cj_memory.manual import ManualPolicy
    from cj_memory_jobs.collection_app import create_collection_app
    from cj_memory_jobs.extraction import CollectionPolicy
    from cj_memory_jobs.producer import IncrementalProducer, ProducerHost
    from cj_memory_jobs.worker_adapter import MemoryCollectionAdapterV2
    from cj_run.background import BackgroundJobsV2
    from cj_run.background_store import JobRequest

    extraction = CollectionPolicy(frozenset({'self'}), frozenset({'pace'}), 1, 4096,
                                  lambda entry: True, lambda entry, rows: False)
    memory = ManualPolicy(extraction.subjects, extraction.slots, frozenset({'long_term'}),
                          frozenset(), datetime.now(timezone.utc) + timedelta(hours=1),
                          lambda command, raw: True, lambda command, raw: True)
    app = create_collection_app(conninfo_path=connection, auth_dir=auth, run_context=context,
                                resolve_collection=lambda principal: (extraction, memory, lambda entry: (None, None)))
    host = app.state.memory_history
    jobs = BackgroundJobsV2(database=host.database, boundary=host.boundary,
                            collection=MemoryCollectionAdapterV2(host.service), max_payload_bytes=262144)
    originals = []

    def submit(bearer, job, attempt, query, prepared):
        result = jobs.prepare(bearer, JobRequest(job, attempt, query, None, prepared))
        originals.append(result)
        return result

    producer = IncrementalProducer(host.service, submit, max_payload_bytes=262144, max_conversations=10)
    background = ProducerHost(producer, lambda: [token(subject) for subject in subjects], LocalBackgroundHost(jobs, auth))

    class SourceFake(FakeProvider):
        def __init__(self):
            super().__init__(chunks_per_reply=1)
            self.extractions = []

        def stream(self, messages, system=None):
            if system is None:
                yield from super().stream(messages, system)
                return
            self.calls += 1
            data = json.loads(messages[0]['content'])
            assert data['version'] == 'MEMORY-EXTRACT-DATA@2' and data['purpose'] == 'incremental'
            assert len(data['messages']) == 1
            self.extractions.append(data)
            original = data['messages'][0]
            yield json.dumps(dict(version='MEMORY-EXTRACT@2', entries=[dict(
                subject='self', slot='pace', kind='inference', text=original['text'],
                extent='long_term', occurred_at='时间不详',
                evidence=[dict(ref=original['ref'], quote=original['text'])])]), ensure_ascii=False)

    return app, host, jobs, background, SourceFake(), originals


def prepare_source(app, host, jobs, background, model, originals, auth, token, other_token):
    from fastapi.testclient import TestClient
    from run_worker import run_once

    conversation = 'candidate+中文-' + uuid.uuid4().hex
    text = '我可能更喜欢轻松的行程节奏'
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/octet-stream'}

    def expect(response):
        # Error output intentionally excludes response bodies and request headers.
        assert response.status_code == 200, ('signed local API status', response.status_code)
        return response.json()

    with TestClient(app) as client:
        head = expect(client.put('/v1/conversations', params={'conversation_id': conversation}, headers=headers))
        message = dict(version='MESSAGE-send.1', conversation_id=conversation, message_id=str(uuid.uuid4()),
                       text=text, trip_id=None, creation_intent='none', expected_generation=head['generation'], expected_sequence=0)
        expect(client.post('/v1/messages', content=json.dumps(message).encode(), headers=headers))
        normal = run_once(host.database, model, auth)
        assert len(normal) == 1 and normal[0].status == 'completed' and model.calls == 1
        consent = dict(version='MEMORY-HISTORY@1', action_id=str(uuid.uuid4()), operation='enable',
                       conversation_id=conversation, expected_generation=head['generation'], expected_epoch=0, expected_source_version=0)
        expect(client.post('/v3/memory-history-actions', content=json.dumps(consent).encode(), headers=headers))
        produced = run_once(host.database, model, auth, background_jobs=background)
        assert len(produced) == 1 and produced[0].status == 'completed'
        assert model.calls == 2 and len(model.extractions) == 1 and len(originals) == 1
        assert run_once(host.database, model, auth, background_jobs=background) == [] and model.calls == 2
        page = expect(client.get('/v5/memory-candidate-jobs', params={'conversation_id': conversation, 'after_job_id': ''}, headers=headers))['result']
        assert page['conversation_id'] == conversation and page['next_after_job_id'] is None and len(page['jobs']) == 1
        reference = page['jobs'][0]
        original = originals[0]
        assert reference == {key: original[key] for key in ('job_id', 'attempt_id')}
        observed = jobs.query_original(token, reference['job_id'], reference['attempt_id'])
        assert observed['state'] == 'completed' and observed['meter_attempt_id'] == original['meter_attempt_id']
        current = expect(client.get('/v3/memory-candidates', params=reference, headers=headers))['result']
        assert len(current['candidates']) == 1
        candidate = current['candidates'][0]
        assert candidate['status'] == 'candidate' and candidate['kind'] == 'inference' and candidate['text'] == text
        foreign = client.get('/v5/memory-candidate-jobs', params={'conversation_id': conversation, 'after_job_id': ''},
                             headers={'Authorization': 'Bearer ' + other_token})
        assert foreign.status_code in (403, 503), ('foreign protected discovery', foreign.status_code)
        return dict(conversation=conversation, message_id=message['message_id'], producer=reference,
                    candidate_id=candidate['candidate_id'], candidate_sha256=hashlib.sha256(candidate['text'].encode()).hexdigest(),
                    provider_calls=model.calls, meter_attempt_id=observed['meter_attempt_id'],
                    status='candidate', foreign_discovery_status=foreign.status_code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-source', required=True, type=Path)
    parser.add_argument('--backend-head', required=True)
    parser.add_argument('--run-context', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    backend, output = args.backend_source.resolve(), args.output.resolve()
    root = Path(__file__).resolve().parents[3]
    if output.is_relative_to(root) or output.is_relative_to(backend):
        raise ValueError('External evidence directory required')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=backend):
        raise ValueError('Backend pin must be clean')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=backend, text=True).strip() != args.backend_head:
        raise ValueError('Backend pin mismatch')
    for name in tuple(os.environ):
        if name.startswith(('PG', 'LIBPQ', 'CJ_LOCAL_')) or name in ('DATABASE_URL', 'CJ_DATABASE_URL'):
            os.environ.pop(name)
    os.environ['CJ_ENV'] = 'local'
    sys.path.insert(0, str(backend / 'scripts'))
    # Explicit supplied source paths precede an editable distribution's old tree.
    sys.path[:0] = [str(backend / 'backend'), *[str(p) for p in (backend / 'backend').iterdir() if p.is_dir()]]
    import psycopg
    import dev_auth
    import local_run_context
    import migrate
    from pg_suites import cluster
    import cj_memory_jobs.collection_app as collection_module
    from cj_api.local_app import ISSUER, scope_for
    from cj_api.local_run_context import load_run_context
    if not Path(collection_module.__file__).resolve().is_relative_to(backend):
        raise ValueError('Wrong imported source')
    context = load_run_context(args.run_context)
    assert context.current.meter.budget == 2
    output.mkdir(parents=True)
    report = dict(status='RUNNING', backend_head=args.backend_head, native='UNRUN', app='UNRUN',
                  run_context=json.loads(args.run_context.read_text()), pg_stopped=False)
    report_path = output / 'report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        with tempfile.TemporaryDirectory(prefix='cj460-', dir='/tmp') as temp:
            folder = Path(temp)
            with cluster('candidate', port=55760, role='cj460_initializer', root=folder / 'pg') as config:
                with psycopg.connect(**config, autocommit=True) as connection:
                    chain = migrate.load(); migrate.up(connection, chain, chain[-1]['version'])
                connection_path = folder / 'connection.json'; connection_path.write_text(json.dumps(config)); connection_path.chmod(0o600)
                subjects = ['cj460-' + uuid.uuid4().hex for _ in range(2)]
                auth = folder / 'auth'; dev_auth.init(auth, subjects)
                for subject in subjects: local_run_context.provision_budget(connection_path, context, subject)
                tokens = {subject: dev_auth.token(auth, subject, 30) for subject in subjects}
                app, host, jobs, background, model, originals = build_source_host(connection_path, auth, context, subjects, tokens.__getitem__)
                proof = prepare_source(app, host, jobs, background, model, originals, auth, tokens[subjects[0]], tokens[subjects[1]])
                with host.database.connect(scope_for(ISSUER, subjects[0])) as connection:
                    assert connection.execute('SELECT current_user').fetchone() == ('cj_m1_runtime',)
                    assert connection.execute("SELECT count(*) FROM cj_memory_item WHERE status='candidate'").fetchone() == (1,)
                    assert connection.execute('SELECT count(*) FROM cj_memory_candidate_action').fetchone() == (0,)
                report.update(source=proof, runtime_role='cj_m1_runtime', status='PASS')
            report['pg_stopped'] = True
        # Fresh signer files and credentials were confined to the removed temp tree.
        report['task_credentials_destroyed'] = True
    except BaseException as error:
        report.update(status='FAIL', error_type=type(error).__name__)
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
