"""Executable synthetic consumer of the actual public NEEDS object contract."""
from dataclasses import asdict
import json
from pathlib import Path

from cj_needs.domain import Command, Revision, Snapshot, validate_fields
from cj_feasibility import evaluate


def synthetic_history(patches):
    fields, revisions = {}, []
    for version, patch in enumerate(patches, 1):
        raw = json.dumps(dict(action_id=f'synthetic-{version}', needs_id='synthetic-demo',
                              expected_version=version - 1,
                              source={'kind': 'manual', 'text': 'synthetic demo only / 仅合成示例'},
                              changes=patch), ensure_ascii=False).encode()
        command = Command(raw)
        fields.update(command.data['changes'])
        validate_fields(fields, complete=True)
        content = json.dumps(fields, ensure_ascii=False, separators=(',', ':')).encode()
        revisions.append(Revision('synthetic-demo', version, command.action_id, raw, content))
    return Snapshot('synthetic-demo', len(revisions), content), tuple(revisions)


def main():
    fixture = Path(__file__).resolve().parents[2] / 'contracts/feasibility/examples.json'
    for case in json.loads(fixture.read_text()):
        snapshot, revisions = synthetic_history(case['patches'])
        report = evaluate(snapshot, revisions)
        checks = [c for c in report.checks if c.code in case['expected_codes']]
        assert report.status == case['expected_status'], case['name']
        assert {c.code for c in checks} == set(case['expected_codes']), case['name']
        # Actual evidence stays in memory; output only synthetic diagnostic summaries.
        print(json.dumps({'synthetic': True, 'case': case['name'], 'status': report.status,
                          'checks': [{key: value for key, value in asdict(c).items() if key != 'evidence'}
                                     for c in checks]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
