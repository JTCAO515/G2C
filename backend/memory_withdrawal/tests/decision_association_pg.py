"""C #26 preparation observes the real V3 workflow before account erasure."""
import json,os,sys,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import psycopg

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend/memory_jobs/tests')]
import migrate,pg_suites
from cj_memory_jobs.decision_service import DecisionCollectionService
from cj_memory_withdrawal.source_graph import capture
from cj_memory_withdrawal.association import prepare


def exercise():
    from decision_jobs_pg import DecisionInputChecks
    actual=DecisionCollectionService.apply_candidate;observations=[]
    def apply(service,token,raw,**kwargs):
        result=actual(service,token,raw,**kwargs);action=json.loads(raw)
        def project(context):
            repository,_,guard=service._binding(context,token)
            with repository.transaction() as memory:
                graph=json.loads(capture(memory,action['candidate_id'],max_sources=1000,max_bytes=1_000_000))
                association=prepare(memory,action['candidate_id'],expected_version=graph['item_version'],
                    expected_scope_epoch=graph['scope_epoch'],max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
                guard('decision_erasure_association');return association
        value=json.loads(service.boundary.with_history_context(token,project))
        assert len(value['decision_source_sha256s'])==1
        assert len(value['source_refs'])==2 and len(value['message_refs'])==2
        assert {r['job_id']:r['state'] for r in value['job_refs']}=={
            'decision-job':'completed','copy-job':'completed','decision-ending':'completed','tail-job':'inflight'}
        # Tail's publication rolled back; its separate message never entered the
        # canonical origin. Only the exact decision digest finds that old job.
        assert all(r['conversation_id']!='decision-tail' for r in value['message_refs'])
        observations.append(value)
        return result
    suite=unittest.TestSuite([DecisionInputChecks('test_real_modified_trip_and_committed_discussion_feed_bounded_data')])
    with patch.object(DecisionCollectionService,'apply_candidate',apply):result=unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful() and len(observations)==1
    print('PASS real V3 confirmation source graph preserves decision digest/all actual anchors; exact digest also captures rolled-back inflight tail outside first origin; readonly comparison only, immutable erasure intent still unprovided')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-decision-erasure-') as folder:
        root=Path(folder)
        with pg_suites.cluster('decision_association',port=55812,role='cj_c_decision_association',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
            path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            with patch.dict(os.environ,{'CJ_E2E_CONNINFO':str(path)}):
                exercise()
