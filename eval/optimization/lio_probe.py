"""Public Lio mutation setup proof using C's signed local host and FakeProvider.

Local fixture only: fresh private PG and local admission configuration, never HK
bootstrap, a production role/profile change, or a B Part2 collection substitute.
"""
import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from cj_agent.provider import FakeProvider
from cj_api.lio_planning_grounding import PLAN_REQUEST, PlanningTurn, requests_save
from cj_api.local_lio_planning import COMPACT_DRAFT, explicit_plan
from cj_draft.lio_plan import COMPACT_INITIAL_PLAN, INITIAL_SYSTEM
from .score_v2 import dataset

VERSION = 'G2C-lio-setup-probe.1'
TASKS = ('dev-local-edit', 'val-undo')


def grounded_setup(task, language):
    text = task['variants'][language]['steps'][0]['text']
    assert PLAN_REQUEST.match(text) and requests_save(text), 'original planning/save declaration not admitted'
    details = explicit_plan((PlanningTurn(text, date(2026, 11, 11)),), (), explicit_save=True)
    assert details is not None and details.clarification is None, 'complete original planning authority required'
    fields = details.fields
    dates = re.findall(r'\d{4}-\d{2}-\d{2}', text)
    assert [fields[edge]['date']['value'] for edge in ('arrival', 'departure')] == dates
    assert fields['party_size'] == dict(state='known', value=2)
    fixed, = fields['fixed_items']
    assert fixed['locked'] == dict(state='known', value=True) and fixed['applies_to'] == ['party']
    assert fixed['description'] in text and fixed['start']['date'] == fields['arrival']['date']
    return details


class PlanFixture(FakeProvider):
    def __init__(self, details):
        super().__init__()
        self.day = details.fields['departure']['date']['value']
        self.inputs = []

    def stream(self, messages, system=None):
        # C must admit the public declarations without an intake-model invention.
        assert system.startswith(INITIAL_SYSTEM) and system.endswith(COMPACT_DRAFT)
        self.calls += 1
        self.inputs.append(messages)
        yield json.dumps(dict(version=COMPACT_INITIAL_PLAN, title='Public setup control',
            items=[dict(id='afternoon', text='Park walk', date=self.day,
                        start_time='13:00', end_time='14:00', timezone='Asia/Shanghai')],
            proposed_subjects={'afternoon': ['party']}))


def capture(task, language, conninfo, root):
    # C's original script seams, read-only reused. No copies of its API/worker logic.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    import dev_auth
    import local_run_context
    import run_worker
    from fastapi.testclient import TestClient
    from cj_agent.draft import trip_scope_for
    from cj_api.local_app import ISSUER, LocalDatabase, create_local_app, load_confirmation_signer, scope_for
    from cj_api.local_run_context import load_run_context
    from cj_api.local_worker_context import checker_for
    from cj_trip.lio_history import revisions
    from cj_trip.postgres import Repository

    details = grounded_setup(task, language)
    actor = task['id'] + '-' + language
    auth = root / actor
    dev_auth.init(auth, [actor])
    now = int(time.time())
    meter_path = auth / 'meter.json'
    meter_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2', current=dict(
        meter=dict(unit='provider_call', budget=80, period_start=now-60, period_end=now+3600,
                   max_steps=8, max_tools=2, max_output=60000, max_seconds=600),
        output_limits=dict(model=4000, tool=2000, memory=1000)), history=[])))
    context = load_run_context(meter_path)
    local_run_context.provision_budget(conninfo, context, actor)
    from cj_message.travel import ABI
    dev_auth.activate_travel(conninfo, actor, context, ABI)
    database = LocalDatabase(conninfo, run_context=context, travel_context=True, needs_context=True)
    signer = load_confirmation_signer(auth)
    app = create_local_app(conninfo_path=None, auth_dir=auth, database=database, account_admission=True,
        confirmation_signer=signer, demo_dialogue_subjects=frozenset({actor}), lio_dialogue_subjects=frozenset({actor}))
    scope = scope_for(ISSUER, actor)
    provider = PlanFixture(details)
    worker = run_worker._worker_for_scope(database, provider, auth, scope, checker_for(auth),
        draft_profile='needs-structured.1', demo_planning=True, lio_confirmation=signer)
    headers = {'Authorization': 'Bearer ' + dev_auth.token(auth, actor, 5),
               'Content-Type': 'application/octet-stream'}
    repository = Repository(lambda: database.connect(scope), trip_scope_for(scope), structured=True)
    evidence = dict(task_id=task['id'], language=language, grounding=details.fields, messages=[], snapshots=[])
    conversation = None
    with TestClient(app) as api:
        for index, step in enumerate(task['variants'][language]['steps']):
            if step['kind'] == 'message':
                raw = dict(version='LIO-message.2', message_id=f'public-step-{index}', text=step['text'], locale=language)
                if conversation is None:
                    raw.update(new_conversation=True)
                else:
                    raw.update(conversation_id=conversation)
                original = json.dumps(raw, ensure_ascii=False).encode()
                response = api.post('/v2/lio/messages', content=original, headers=headers)
                assert response.status_code == 200, response.text
                conversation = response.json()['conversation_id']
                outcomes = worker.process()
                assert [outcome.status for outcome in outcomes] == ['completed'], outcomes
                evidence['messages'].append(dict(original=raw, input_sha256=sha256(original).hexdigest(), receipt=response.json()))
            else:
                before = api.get('/v2/lio/trip', params={'conversation_id': conversation}, headers=headers).json()
                raw = dict(version='LIO-trip-undo.2', action_id='public-undo',
                           conversation_id=conversation, target=before['undo_target'])
                response = api.post('/v2/lio/trip/undo', content=json.dumps(raw).encode(), headers=headers)
                assert response.status_code == 200 and response.json()['committed'] is True, response.text
                evidence['undo'] = dict(original=raw, receipt=response.json())
            response = api.get('/v2/lio/trip', params={'conversation_id': conversation}, headers=headers)
            assert response.status_code == 200, response.text
            card = response.json()['current']
            assert card is not None, response.text
            actual = revisions(repository, card['trip_id'])
            current = json.loads(actual[0].content)
            fixed = [item for item in current['items'] if item['fixed'] == dict(state='known', value=True)]
            declaration, = details.fields['fixed_items']
            assert len(fixed) == 1 and fixed[0]['id'] == declaration['item_id']
            assert fixed[0]['text'] == declaration['description']
            assert fixed[0]['schedule']['start']['time'] == declaration['start']['time']
            assert fixed[0]['schedule']['end']['time'] == declaration['end']['time']
            snapshot = dict(version=actual[0].version, trip_id=card['trip_id'], fixed=fixed,
                content=current, history={str(t.version): sha256(t.content).hexdigest() for t in actual})
            assert snapshot['version'] == index+1, snapshot
            evidence['snapshots'].append(snapshot)
        snapshots = evidence['snapshots']
        assert len({s['trip_id'] for s in snapshots}) == 1
        assert snapshots[0]['fixed'] == snapshots[1]['fixed']
        old, new = snapshots[0]['content'], snapshots[1]['content']
        replacement = '天坛' if language == 'zh' else 'Temple of Heaven'
        if task['id'] == 'val-undo':
            replacement = '颐和园' if language == 'zh' else 'the Summer Palace'
        # The admitted selector preserves the literal replacement label.
        assert new['items'] == [dict(item, text=replacement) if item['id']=='afternoon' else item for item in old['items']]
        assert all(s['history']['1'] == snapshots[0]['history']['1'] for s in snapshots)
        if task['id'] == 'val-undo':
            assert snapshots[2]['content'] == snapshots[0]['content']
            assert snapshots[2]['history']['2'] == snapshots[1]['history']['2']
        assert provider.calls == 1, 'edit/undo must not fabricate another model call'
        evidence.update(model_calls=provider.calls, provider_inputs=provider.inputs, result='PASS')
        return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runtime import private_database
    document, digest = dataset()
    report = dict(version=VERSION, commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  dataset_sha256=digest, environment='signed local API / private PG / FakeProvider',
                  source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), external_calls=0, controls=[])
    with private_database('lio-v2-setup') as conninfo, tempfile.TemporaryDirectory(prefix='g2c-lio-setup-') as folder:
        for task in document['tasks']:
            if task['id'] not in TASKS:
                continue
            for language in ('zh', 'en'):
                evidence = capture(task, language, conninfo, Path(folder))
                name = task['id'] + '-' + language
                (args.output / (name+'.json')).write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
                report['controls'].append(dict(task_id=task['id'], language=language, result='PASS',
                    versions=[s['version'] for s in evidence['snapshots']], fixed_items=1, model_calls=evidence['model_calls']))
                (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
                print(name, 'PASS', flush=True)


if __name__ == '__main__':
    main()
