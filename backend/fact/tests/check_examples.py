"""Run fixed FACT consumer cases. No network, provider, identity or cost is involved."""
import json
from datetime import date, datetime
from pathlib import Path

from cj_fact import DateRange, Query, SourcePolicy, evaluate, extract_structured_evidence, parse_document


def main():
    path = Path(__file__).resolve().parents[3] / 'contracts' / 'fact' / 'synthetic-cases.json'
    bundle = json.loads(path.read_text())
    assert bundle['synthetic'] is True
    policy = SourcePolicy(('https://source.example.test',), 8192, 32, 0, 1.0, 8, 256)
    for case in bundle['cases']:
        query_data = case['query']
        query = Query(query_data['fact_key'], query_data['region'],
                      DateRange(date.fromisoformat(query_data['start']), date.fromisoformat(query_data['end'])),
                      tuple(query_data['conditions'].items()), datetime.fromisoformat(query_data['evaluated_at']))
        records = []
        for index, record in enumerate(case['sources']):
            doc = parse_document(source_url='https://source.example.test/fixture',
                                 retrieved_at=datetime.fromisoformat(case['retrieved_at']),
                                 content_type='application/json', body=json.dumps(record).encode(),
                                 policy=policy, synthetic=True)
            records.append(extract_structured_evidence(doc, evidence_id=f'fixture-{index}',
                                                       fact_key=query.fact_key, policy=policy))
        result = evaluate(query, tuple(records))
        assert result.status.value == case['expected_status'], case['id']
        assert result.original_value == case['expected_original_value'], case['id']
        assert all(item.evidence.document.synthetic for item in result.assessments)
        print(f"PASS {case['id']}: {result.status.value}")
    print(f"{len(bundle['cases'])} synthetic consumer cases PASS; real integration UNRUN")


if __name__ == '__main__':
    main()
