"""Declared read-only old conversations; never worker/model/Memory claims."""
from hashlib import sha256
import re

from cj_run.core import Binding
from cj_usage.authorization_budget import canonical
from runtime_adapter.contract import Unavailable

VERSION='LIO-readonly-history-anchor.1'


def targets(plan,scopes):
    old=plan.get('old_chats',{})
    if plan.get('first_setup')is True:
        if old:raise Unavailable('APP_SMOKE_SETUP_HAS_UNQUALIFIED_OLD_TARGETS')
        return []
    if type(old)is not dict or set(old)!={'zh','en'}:raise Unavailable('APP_SMOKE_HISTORY_TARGETS_REQUIRED')
    result=[];seen=set()
    for locale,selected in old.items():
        if type(selected)is not dict:raise Unavailable('APP_SMOKE_HISTORY_TARGET_INVALID')
        conversations=selected.get('conversations',[selected])
        chosen={k:v for k,v in selected.items()if k!='conversations'}
        if(type(conversations)is not list or not conversations or chosen not in conversations):
            raise Unavailable('APP_SMOKE_SELECTED_HISTORY_NOT_IN_CENSUS')
        for anchor in conversations:
            result.extend(_anchor(anchor,scopes[locale],seen))
    return result


def _anchor(anchor,scope,seen):
    result=[]
    if(type(anchor)is not dict or set(anchor)!={'version','conversation_id','generation','messages'}
            or anchor['version']!=VERSION or type(anchor['conversation_id'])is not str
            or re.fullmatch('lio-dialogue-[0-9a-f]{32}',anchor['conversation_id'])is None
            or type(anchor['generation'])is not str or not anchor['generation']
            or type(anchor['messages'])is not list or not 1<=len(anchor['messages'])<=2000):
        raise Unavailable('APP_SMOKE_HISTORY_TARGET_INVALID')
    previous=0
    for item in anchor['messages']:
        if(type(item)is not dict or set(item)!={'message_id','run_id','sequence','canonical_sha256'}
                or type(item['canonical_sha256'])is not str or re.fullmatch('[a-f0-9]{64}',item['canonical_sha256'])is None
                or type(item['sequence'])is not int or item['sequence']<=previous):
            raise Unavailable('APP_SMOKE_HISTORY_MESSAGE_INVALID')
        binding=Binding(scope,anchor['conversation_id'],anchor['generation'],
            item['message_id'],item['run_id'],item['sequence'])
        key=(binding.scope,binding.message_id)
        if key in seen:raise Unavailable('APP_SMOKE_HISTORY_MESSAGE_NOT_UNIQUE')
        seen.add(key);previous=item['sequence']
        result.append(dict(origin='readonly_history',binding=dict(scope=binding.scope,conversation_id=binding.conversation_id,
            generation=binding.generation,message_id=binding.message_id,run_id=binding.run_id,message_sequence=binding.message_sequence),
            canonical_sha256=item['canonical_sha256']))
    return result

def require_original(context,original,target):
    if original is None or original.raw is None:raise Unavailable('APP_SMOKE_HISTORY_ORIGINAL_UNAVAILABLE')
    r=original.receipt;b=target['binding']
    if((context.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)!=tuple(
            b[k]for k in('scope','conversation_id','generation','message_id','run_id','message_sequence'))
            or r.input_sha256!=target['canonical_sha256']or sha256(original.raw).hexdigest()!=target['canonical_sha256']):
        raise Unavailable('APP_SMOKE_HISTORY_ORIGINAL_CHANGED')
    return original


def require_census(selected,state):
    for cid in {x['binding']['conversation_id']for x in selected}:
        expected=[dict(message_id=t['binding']['message_id'],run_id=t['binding']['run_id'],conversation_id=cid,
            generation=t['binding']['generation'],sequence=t['binding']['message_sequence'],canonical_sha256=t['canonical_sha256'])
            for t in selected if t['binding']['conversation_id']==cid]
        actual=[row for row in state['native_messages']if row['conversation_id']==cid]
        if sorted(actual,key=lambda x:x['sequence'])!=expected:
            raise Unavailable('APP_SMOKE_HISTORY_CENSUS_CHANGED')


def anchors(selected):
    result=[]
    for cid in dict.fromkeys(x['binding']['conversation_id']for x in selected):
        rows=[x for x in selected if x['binding']['conversation_id']==cid]
        result.append(dict(version=VERSION,conversation_id=cid,generation=rows[0]['binding']['generation'],
            messages=[dict(message_id=x['binding']['message_id'],run_id=x['binding']['run_id'],
                sequence=x['binding']['message_sequence'],canonical_sha256=x['canonical_sha256'])for x in rows]))
    return result


def export_anchor(boundary,database,token,conversation_id):
    """B prepares declared metadata from real current same-owner M originals."""
    if type(conversation_id)is not str or re.fullmatch('lio-dialogue-[0-9a-f]{32}',conversation_id)is None:
        raise Unavailable('APP_SMOKE_HISTORY_CONVERSATION_INVALID')
    def read(context):
        with database.connect(context.scope)as db:
            db.execute('SET TRANSACTION READ ONLY')
            rows=db.execute('SELECT message_id,run_id,generation,sequence,input_sha256 FROM cj_message_receipt '
                'WHERE scope=%s AND conversation_id=%s ORDER BY sequence',(context.scope,conversation_id)).fetchall()
        if not rows:raise Unavailable('APP_SMOKE_HISTORY_CONVERSATION_UNAVAILABLE')
        result=[]
        for mid,run,generation,sequence,digest in rows:
            target=dict(binding=dict(scope=context.scope,conversation_id=conversation_id,generation=generation,
                message_id=mid,run_id=run,message_sequence=sequence),canonical_sha256=digest)
            require_original(context,context.query_lio_message(mid),target)
            result.append(target)
        if len({x['binding']['generation']for x in result})!=1:
            raise Unavailable('APP_SMOKE_HISTORY_GENERATION_CHANGED')
        return anchors(result)[0]
    return boundary.with_history_context(token,read)


def default_anchor(boundary,database,token,allowed_scopes):
    from cj_message.demo_dialogue import lio_conversation
    def read(context):
        if context.scope not in allowed_scopes:raise Unavailable('APP_SMOKE_DEFAULT_OWNER_CHANGED')
        cid=lio_conversation(context.scope)
        page=context.lio_timeline(None,None,multiple=False)
        with database.connect(context.scope)as db:
            db.execute('SET TRANSACTION READ ONLY')
            rows=db.execute('SELECT message_id,run_id,generation,sequence,input_sha256 FROM cj_message_receipt '
                'WHERE scope=%s AND conversation_id=%s ORDER BY sequence',(context.scope,cid)).fetchall()
        messages=[]
        for mid,run,generation,sequence,digest in rows:
            target=dict(binding=dict(scope=context.scope,conversation_id=cid,generation=generation,
                message_id=mid,run_id=run,message_sequence=sequence),canonical_sha256=digest)
            require_original(context,context.query_lio_message(mid),target)
            if generation!=page.generation:raise Unavailable('APP_SMOKE_DEFAULT_GENERATION_CHANGED')
            messages.append(dict(message_id=mid,run_id=run,sequence=sequence,canonical_sha256=digest))
        if context.lio_timeline(None,None,multiple=False)!=page:
            raise Unavailable('APP_SMOKE_DEFAULT_PAGE_CHANGED')
        return dict(version=VERSION,conversation_id=cid,generation=page.generation,messages=messages)
    return boundary.with_history_context(token,read)


def with_default_response(originals,token,selector,response,consumer):
    return originals.boundary.with_history_context(token,
        lambda context:default_response_in_context(originals,context,selector,response,consumer))


def default_response_in_context(originals,context,selector,response,consumer):
    """Actual default GET under its existing AUTH/M context, even no-M page."""
    import json
    payload=json.loads(response)
    cursor=selector.get('before')
    page=context.lio_timeline(None,cursor,multiple=False)
    if(payload.get('version')!='LIO-timeline.1'or payload.get('conversation_id')!=page.conversation_id
            or payload.get('next_before')!=page.next_before
            or [row['message_id']for row in payload.get('messages',[])]!=[row.message_id for row in page.messages]
            or [row['text']for row in payload.get('messages',[])]!=[row.text for row in page.messages]):
        raise Unavailable('APP_SMOKE_ACTUAL_DEFAULT_PAGE_CHANGED')
    bindings=[Binding(context.scope,page.conversation_id,page.generation,item.message_id,item.run_id,item.sequence)
              for item in page.messages]
    def publish():
        value=consumer(context.scope,page,bindings[-1]if bindings else None)
        if context.lio_timeline(None,cursor,multiple=False)!=page:
            raise Unavailable('APP_SMOKE_DEFAULT_PAGE_CHANGED')
        return value
    if bindings:
        snapshots=originals.database.run_repository(context.scope).lio_timeline(bindings)
        if any(state is not None and state.status=='completed'for state,_ in snapshots):
            return context.with_lio_timeline_projection(publish)
    return publish()
