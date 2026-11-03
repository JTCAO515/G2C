"""A genuinely new process compares original manual derivation for erasure."""
import json,sys
from pathlib import Path
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_withdrawal.association import prepare
from cj_memory_withdrawal.source_graph import capture

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth

if __name__=='__main__':
    path,auth,subject,item=sys.argv[1:]
    service=create_collection_app(conninfo_path=Path(path),auth_dir=Path(auth),resolve_collection=lambda principal:None).state.memory_history.service
    token=dev_auth.token(Path(auth),subject,30)
    def read(context):
        repo,_,guard=service._binding(context,token)
        with repo.transaction() as memory:
            graph=json.loads(capture(memory,item,max_sources=1000,max_bytes=1_000_000))
            raw=prepare(memory,item,expected_version=graph['item_version'],expected_scope_epoch=graph['scope_epoch'],
                max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
            guard('new_process_manual_original');return raw
    value=json.loads(service.boundary.with_history_context(token,read))
    assert len(value['source_refs'])==len(value['operation_refs'])==1
    print('PASS new process original manual source/operation derivation, no rewritten user bytes or source identity')
