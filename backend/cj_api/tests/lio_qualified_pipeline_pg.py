"""Actual qualified native4 consumers on the same original private PG account.

B's accepted operator entry upgrades only the existing empty fixture ledger.
No production account, token, quota, table writer or supplier is used here.
The actual L model/place/route adapters still traverse their signed origins,
registered exit, financial receipt and Memory holds; HTTP remains a fixture.
"""
from dataclasses import asdict
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
from cj_api.local_app import ISSUER,scope_for
from cj_api.local_worker_context import LocalBudgetRouter
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode_stored,decode_v2
from cj_usage.core import NATIVE4_PROFILE,model_attempts,provider_attempts
from cj_usage.registered_exit import Native4RegisteredExit
from deploy.hk import checkpoint,demo_accounts
import lio_exploration_flow_pg as native
import lio_pipeline_models_pg
import lio_route_sources_pg


def main(*,natural_direct=False,production=False):
    original_manage=demo_accounts.manage
    original_router=LocalBudgetRouter.for_run
    original_run_once=native.run_worker.run_once
    qualified=[];checked=[];selected=[]
    def manage(runtime,mode,subject,control,operation,new=None):
        result=original_manage(runtime,mode,subject,control,operation,new)
        if mode!='insert'or subject!=native.SUBJECT:return result
        scope=scope_for(ISSUER,subject);account=ledger_scope_for(scope,runtime.context.current.meter)
        # The accepted base fixture performs the official qualification after
        # manage(insert) returns. Observe the prior ledger here; never apply a
        # second qualification or replace the platform setup with a monkey.
        with checkpoint.operator()as (connection,_):
            row=connection.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
            before=decode_stored(*row)
            assert row[0]==1 and not before.attempts
        qualified.append((runtime,scope,account,asdict(before.config),checkpoint.operator))
        return result
    def router(host,binding,state):
        result=original_router(host,binding,state)
        assert isinstance(result,Native4RegisteredExit)
        assert result.output_limits['tool']==8192
        selected.append(binding.run_id)
        return result
    def run_once(*args,**kwargs):
        outcomes=original_run_once(*args,**kwargs)
        runtime,scope,account,config,operator=qualified[-1]
        with operator()as (connection,_):
            row=connection.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
            ledger=decode_v2(row[1])
            assert row[0]==2 and asdict(ledger.config)==config
            assert all(profile==NATIVE4_PROFILE for profile in ledger.run_profiles.values())
            assert all(model_attempts(ledger,rid)<=6 and provider_attempts(ledger,rid,'amap')<=45
                       for rid in ledger.runs)
            checked.append((len(ledger.runs),len(ledger.attempts)))
        return outcomes
    with patch.object(demo_accounts,'manage',manage),patch.object(LocalBudgetRouter,'for_run',router), \
            patch.object(native.run_worker,'run_once',run_once):
        lio_pipeline_models_pg.main(natural_direct=natural_direct)
        if production:
            lio_pipeline_models_pg.main(natural_direct=natural_direct,production=True)
            from lio_wording_connection_pg import check_wording_connections
            check_wording_connections(lio_pipeline_models_pg.main, production=True, cases=(0,),
                duration_days=4, natural_direct=True)
            lio_pipeline_models_pg.main(production=True,cases=(0,),duration_days=5,travel_pace='moderate')
            lio_pipeline_models_pg.main(production=True,cases=(0,),provider_available=False)
        lio_route_sources_pg.main()
    assert len(qualified)==(10 if production else 2)and selected and checked
    print('PASS '+str(len(qualified))+' fresh same-account native4 qualifications via accepted B operator; original budget/config unchanged; actual registered plan-model and place/route consumers selected Native4RegisteredExit; every observed RUN <=6 model including Memory and <=45 amap; fixture HTTP/0 real; '+('full generation exercised'if production else'component generation only')+'; real G6 UNRUN',flush=True)


if __name__=='__main__':main()
