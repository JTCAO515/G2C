"""Actual bounded OR-Tools + independent verifier; synthetic inputs only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event
import json

from cj_place import (ORIGIN, Config, Coordinate, Departure, Endpoint, FieldState,
                      Observed, Quantity, Response, RouteQuery, parse_response, prepare)
from cj_feasibility import Candidate
from cj_feasibility.routes import Window, assess_route
from cj_feasibility.solver import Limits, Problem, StartWindow, solve
from cj_feasibility.output_check import verify_output
from demo import synthetic_history
from route_demo import event, known


def examples():
    epoch=datetime(2026,10,22,tzinfo=timezone.utc)
    at=epoch+timedelta(hours=1)
    fields=[dict(item_id=key,kind='appointment',description='synthetic solver demo / 合成求解',
                 applies_to=['self'],locked=known(False),booking_status=known('intended'),
                 start=event(start),end=event(end))
            for key,start,end in [('a','08:00','09:00'),('b','09:15','10:00')]]
    before,revisions=synthetic_history([{'fixed_items':fields}])
    candidate=Candidate(before.needs_id,before.version,before.content)
    query=RouteQuery(Endpoint('SYNTH_A',Coordinate('116.1,39.1'),'exit'),
                     Endpoint('SYNTH_B',Coordinate('116.2,39.2'),'entrance'),
                     'walking',Departure('at_query_time',None))
    config=Config(ORIGIN,4096,16384,3,60)
    request=prepare(config,query,'synthetic-solver-demo',at)
    body=json.dumps(dict(status='1',info='OK',infocode='10000',count='1',
                         route=dict(origin=query.origin.coordinate.raw,destination=query.destination.coordinate.raw,
                                    paths=[dict(distance='1000',duration='3600')]))).encode()
    result=parse_response(config,request,Response(request.binding_digest,request.origin,request.path,200,body,at+timedelta(seconds=1)),
                          now=at+timedelta(seconds=2),evidence='synthetic')
    zero=Observed(FieldState.PRESENT,Quantity('0',Decimal('0'),'s'))
    scope,ids=frozenset({'fixed_items'}),frozenset({'b'})
    route=assess_route(before,revisions,candidate,Window('a','b',query,zero,zero),result,
                       route_index=0,request=request,config=config,as_of=at+timedelta(seconds=2),
                       selected_fields=scope,selected_item_ids=ids)
    problem=Problem(before,revisions,candidate,scope,ids,
                    (StartWindow('b',at+timedelta(minutes=15),at+timedelta(minutes=61)),),(route,))
    limits=Limits(epoch,86400,1000000,2**60-1,10,10,10,2.0,1.0,10000)
    accepted=solve(problem,limits,stop=Event())
    fixed=replace(problem,selected_fields=frozenset(),selected_item_ids=frozenset(),windows=())
    unsat=solve(fixed,limits,stop=Event())
    exhausted=solve(problem,replace(limits,max_solve_seconds=1e-12),stop=Event())
    limited=solve(problem,replace(limits,max_deterministic_seconds=1e-100),stop=Event())
    tampered=verify_output(problem,candidate,limits)
    assert accepted.status=='CONDITIONAL_SOLUTION' and accepted.verification.accepted
    assert unsat.status=='CONDITIONAL_UNSAT' and unsat.native_status=='INFEASIBLE'
    assert exhausted.status=='TIMEOUT' and not tampered.accepted
    return accepted,unsat,exhausted,limited,tampered


def main():
    values=examples()
    for value in values[:4]:
        print(json.dumps(dict(synthetic=True,status=value.status,reason=value.reason,native_status=value.native_status,
                              overall=value.overall,zh=value.zh,en=value.en,
                              independently_accepted=value.verification.accepted if value.verification else None),ensure_ascii=False))
    print(json.dumps(dict(synthetic=True,tampered_output_accepted=values[4].accepted,codes=values[4].codes),ensure_ascii=False))


if __name__=='__main__':
    main()
