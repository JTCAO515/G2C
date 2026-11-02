"""Read-only erasure preparation, not an immutable cleanup descriptor or grant."""
from hashlib import sha256
import json

from cj_memory.domain import Unavailable
from cj_memory.typed import parse_stored
from cj_memory_management.postgres import Transaction as ManagementTransaction
from cj_memory_jobs.publication_store import PublicationTransaction
from cj_memory_jobs.postgres import encode


def capture(memory,item_id,*,max_sources,max_bytes):
    """Canonical scope-locked source graph, including M37 candidate confirmation.

    Returns comparison/provenance bytes only. It persists nothing, stops nothing,
    and cannot authorize physical erasure, B payload access or model processing.
    Origin producers are first producers, NOT all overlapping queued jobs.
    """
    if (type(max_sources) is not int or not 1<=max_sources<=1000
            or type(max_bytes) is not int or not 1<=max_bytes<=1_000_000):
        raise ValueError('explicit bounded source graph required')
    epoch=memory.lock_scope();item=memory.detail(item_id)
    if item is None:raise Unavailable('selected Memory unavailable')
    cur,scope=memory.cur,memory.scope
    management=ManagementTransaction(cur,scope,typed_context=memory.typed_context)
    publication=PublicationTransaction(memory)
    edges=[]
    cur.execute("SELECT action_id FROM cj_memory_management_action WHERE scope=%s AND item_id=%s AND operation='edit' ORDER BY version LIMIT %s",
                (scope,item_id,max_sources+1))
    actions=cur.fetchall()
    if len(actions)>max_sources:raise Unavailable('source graph exceeds explicit bound')
    for (aid,) in actions:
        _,receipt=management.action(aid)  # Existing persisted-data decoder/projection.
        cur.execute('SELECT previous_source_id,new_source_id FROM cj_memory_management_action WHERE scope=%s AND action_id=%s',(scope,aid))
        previous,current=cur.fetchone()
        edges.append((receipt.version,previous,current))
    cur.execute('SELECT action_id FROM cj_memory_history_candidate_action WHERE scope=%s AND candidate_id=%s ORDER BY action_id LIMIT %s',
                (scope,item_id,max_sources+1))
    decisions=cur.fetchall()
    if len(decisions)>max_sources:raise Unavailable('candidate source graph exceeds explicit bound')
    for (aid,) in decisions:
        raw,receipt=publication.decision(aid)
        action=json.loads(raw);result=json.loads(receipt)['receipt']
        cur.execute('SELECT previous_source_id,new_source_id FROM cj_memory_history_candidate_action WHERE scope=%s AND action_id=%s',(scope,aid))
        previous,current=cur.fetchone()
        if action['operation']=='confirm':
            if current!='candidate-confirm-v1:'+sha256(raw).hexdigest():
                raise Unavailable('candidate source transition differs from original action')
            edges.append((result['version'],previous,current))
        elif current is not None:
            raise Unavailable('rejected candidate cannot create a source')
    edges.sort()
    nodes=[edges[0][1]] if edges else [item.command.source_id]
    versions=set()
    for version,previous,current in edges:
        if version in versions or previous!=nodes[-1] or current in nodes:
            raise Unavailable('source graph is incomplete, forked or cyclic')
        versions.add(version);nodes.append(current)
    if nodes[-1]!=item.command.source_id or len(nodes)>max_sources:
        raise Unavailable('current source does not close the complete graph')
    # Existing approved commands are the source's exact item association. This
    # query also detects unlinked sources for the selected item; it never infers
    # an association from text, a model result or a manual permission flag.
    cur.execute('''SELECT source_id,version,approved_input FROM cj_memory_source
        WHERE scope=%s AND convert_from(approved_input,'UTF8')::jsonb->>'item_id'=%s
        ORDER BY source_id LIMIT %s''',(scope,item_id,max_sources+1))
    rows=cur.fetchall()
    if len(rows)>max_sources:raise Unavailable('source inventory exceeds explicit bound')
    sources=[]
    for sid,version,raw in rows:
        command=parse_stored(bytes(raw))
        if (command.item_id,command.source_id,command.source_version)!=(item_id,sid,version):
            raise Unavailable('stored source projection differs')
        if sid==item.command.source_id and bytes(raw)!=item.command.raw:
            raise Unavailable('current source bytes differ from canonical item')
        sources.append(dict(source_id=sid,source_version=version))
    if {s['source_id'] for s in sources}!=set(nodes):
        raise Unavailable('unlinked or missing selected-item source')
    cur.execute('''SELECT source_id,item_id FROM cj_memory_item WHERE scope=%s AND source_id=ANY(%s)
        UNION SELECT previous_source_id,item_id FROM cj_memory_management_action WHERE scope=%s AND previous_source_id=ANY(%s)
        UNION SELECT new_source_id,item_id FROM cj_memory_management_action WHERE scope=%s AND new_source_id=ANY(%s)
        UNION SELECT previous_source_id,candidate_id FROM cj_memory_history_candidate_action WHERE scope=%s AND previous_source_id=ANY(%s)
        UNION SELECT new_source_id,candidate_id FROM cj_memory_history_candidate_action WHERE scope=%s AND new_source_id=ANY(%s)''',
        (scope,nodes,scope,nodes,scope,nodes,scope,nodes,scope,nodes))
    if any(referred!=item_id for _,referred in cur.fetchall()):
        raise Unavailable('selected source has another item reference')
    cur.execute('SELECT source_id,item_id,job_id,attempt_id,origin_refs FROM cj_memory_history_origin '
                'WHERE scope=%s AND source_id=ANY(%s)',(scope,nodes))
    origins=cur.fetchall();refs={};producers=set()
    for sid,origin_item,jid,attempt,values in origins:
        if origin_item!=item_id or type(values) is not list:
            raise Unavailable('selected source origin differs')
        producers.add((jid,attempt))
        for ref in values:
            fields={'conversation_id','generation','sequence','message_id','input_sha256'}
            if (type(ref) is not dict or set(ref)!=fields or type(ref['sequence']) is not int
                    or not 1<=ref['sequence']<=2**63-1
                    or any(type(ref[k]) is not str or not ref[k].strip() or '\0' in ref[k]
                           for k in ('conversation_id','generation','message_id','input_sha256'))
                    or len(ref['input_sha256'])!=64 or any(ch not in '0123456789abcdef' for ch in ref['input_sha256'])):
                raise Unavailable('original message reference unavailable')
            refs[encode(ref)]=ref
    if any(sid.startswith(('history-v1:','candidate-confirm-v1:')) and not any(o[0]==sid for o in origins) for sid in nodes):
        raise Unavailable('provided history source origin missing')
    raw=encode(dict(version='MEMORY-ERASURE-GRAPH-DRAFT@1',item_id=item_id,item_version=item.version,
        current_source_id=item.command.source_id,current_source_version=item.command.source_version,scope_epoch=epoch,
        source_refs=sources,message_refs=[refs[key] for key in sorted(refs)],
        origin_producers=[dict(job_id=jid,attempt_id=attempt) for jid,attempt in sorted(producers)]))
    if len(raw)>max_bytes:raise Unavailable('source graph response exceeds explicit bound')
    return raw
