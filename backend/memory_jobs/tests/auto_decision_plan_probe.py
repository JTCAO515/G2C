"""Read a pending automatic plan from a genuinely new Python process."""
from datetime import datetime,timedelta,timezone
import json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth
from cj_api.local_run_context import load_run_context
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_automatic_decision_collection_app
from cj_memory_jobs.decision_producer import DecisionConversationProducer


if __name__=='__main__':
    path,auth=sys.argv[1:];auth=Path(auth)
    run=load_run_context(auth/'manual-source-context.json')
    slots=frozenset({'diet.spicy','planning.choice','note'})
    extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda e:True,lambda e,rows:e.kind=='preference')
    memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),
        datetime.now(timezone.utc)+timedelta(hours=1),lambda c,r:True,lambda c,r:True)
    service=create_automatic_decision_collection_app(conninfo_path=Path(path),auth_dir=auth,run_context=run,
        resolve_collection=lambda p:(extraction,memory,lambda e:(None,None))).state.memory_history.service
    def no_submit(*args):raise AssertionError('readonly pending-plan observation dispatched work')
    producer=DecisionConversationProducer(service,no_submit,no_submit,max_payload_bytes=262144,max_conversations=100)
    token=dev_auth.token(auth,'alice',5)
    print(json.dumps(producer.ending._plan(token)))
