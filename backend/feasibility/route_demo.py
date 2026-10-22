"""Synthetic-only executable PLACE consumer; never performs network calls."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from cj_place import (ORIGIN, Config, Coordinate, Departure, Endpoint, FieldState,
                      Observed, Quantity, Response, RouteQuery, parse_response, prepare)
from cj_feasibility import Candidate
from cj_feasibility.routes import Window, assess_route
from demo import synthetic_history


def known(value):
    return {'state': 'known', 'value': value}


def event(wall):
    return dict(date=known('2026-10-22'), time=known(wall), timezone=known('Asia/Shanghai'),
                place={'state': 'unknown'})


def main():
    at = datetime(2026, 10, 22, 1, tzinfo=timezone.utc)
    items = [dict(item_id=key, kind='appointment', description='synthetic appointment / 合成预约',
                  applies_to=['self'], locked=known(False), booking_status=known('intended'),
                  start=event(start), end=event(end))
             for key, start, end in [('a', '08:00', '09:00'), ('b', '09:15', '10:00')]]
    snapshot, revisions = synthetic_history([{'fixed_items': items}])
    candidate = Candidate(snapshot.needs_id, snapshot.version, snapshot.content)
    query = RouteQuery(Endpoint('SYNTH_A', Coordinate('116.1,39.1'), 'exit'),
                       Endpoint('SYNTH_B', Coordinate('116.2,39.2'), 'entrance'),
                       'walking', Departure('at_query_time', None))
    config = Config(ORIGIN, 4096, 16384, 3, 60)  # explicit synthetic policy, no defaults
    request = prepare(config, query, 'synthetic-feasibility-demo', at)
    body = json.dumps(dict(status='1', info='OK', infocode='10000', count='1',
                           route=dict(origin=query.origin.coordinate.raw, destination=query.destination.coordinate.raw,
                                      paths=[dict(distance='1000', duration='3600')]))).encode()
    response = Response(request.binding_digest, request.origin, request.path, 200, body, at + timedelta(seconds=1))
    result = parse_response(config, request, response, now=at + timedelta(seconds=2), evidence='synthetic')
    zero = Observed(FieldState.PRESENT, Quantity('0', Decimal('0'), 's'))
    report = assess_route(snapshot, revisions, candidate, Window('a', 'b', query, zero, zero), result,
                          route_index=0, request=request, config=config, as_of=at + timedelta(seconds=2),
                          selected_fields=frozenset(), selected_item_ids=frozenset())
    assert report.conditional_relation == 'required_exceeds_gap' and report.status == 'UNKNOWN'
    print(json.dumps(dict(synthetic=True, status=report.status, conditional_relation=report.conditional_relation,
                         checks=[dict(code=c.code, status=c.status, missing=c.missing,
                                      details=dict(c.details), zh=c.zh, en=c.en) for c in report.checks
                                 if c.code.startswith('ROUTE_')]), ensure_ascii=False))


if __name__ == '__main__':
    main()
