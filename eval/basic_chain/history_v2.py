"""Frozen read-only history targets, never MESSAGE claims or saved content."""
from .plan import is_sha,require


FIELDS={'version','conversation_id','generation','messages'}


def targets(plan,locale):
    if plan['first_setup']:return ()
    selected=plan['old_chats'][locale]
    require(type(selected)is dict and set(selected)in(FIELDS,FIELDS|{'conversations'}),
            'B actual selected old-chat metadata required for standard execution')
    selected_anchor={key:selected[key]for key in FIELDS}
    values=selected.get('conversations',[selected_anchor])
    require(type(values)is list and values,'complete original history target census required')
    cids=set();mids=set()
    for value in values:
        require(type(value)is dict and set(value)==FIELDS
                and value['version']=='LIO-readonly-history-anchor.1','exact read-only history anchor required')
        cid=value['conversation_id']
        require(type(cid)is str and cid and cid not in cids
                and type(value['generation'])is str and value['generation'],'unique original CID/generation required')
        cids.add(cid)
        messages=value['messages']
        require(type(messages)is list and messages,'original old-chat MESSAGE census required')
        for number,message in enumerate(messages,1):
            require(type(message)is dict and set(message)=={'message_id','run_id','sequence','canonical_sha256'},
                    'exact original MESSAGE target metadata required')
            require(type(message['message_id'])is str and message['message_id']and message['message_id']not in mids
                    and type(message['run_id'])is str and message['run_id']
                    and type(message['sequence'])is int and message['sequence']==number
                    and is_sha(message['canonical_sha256']),'complete distinct ordered MESSAGE targets required')
            mids.add(message['message_id'])
    require(selected_anchor in values,'selected original conversation is missing from history census')
    return tuple(values)


def check_native(targets,state):
    """Validate declared App-local targets against the complete owner census.

    Other server-only CIDs remain in the original state. The product has no
    server history-list API; their presence does not make them App-local rows.
    """
    for target in targets:
        rows=sorted((row for row in state['native_messages']if row['conversation_id']==target['conversation_id']),
                    key=lambda row:row['sequence'])
        require(all(row['generation']==target['generation']for row in rows),'old generation changed')
        require([{key:row[key]for key in('message_id','run_id','sequence','canonical_sha256')}for row in rows]==target['messages'],
                'current original old MESSAGE census differs from frozen targets')
