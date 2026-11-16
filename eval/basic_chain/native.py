"""Parse B's actual protected host facts; no semantic or qualification labels.

Only the qualified transport invokes this parser in a real run. An imported
JSON file is not a transport, authority, UI witness or dispatch permission.
"""
from dataclasses import dataclass
from hashlib import sha256

from .plan import decode,digest,is_sha,packed,require
from .history_v2 import targets,check_native,default_target


def _state(value,scope):
    require(value['version']=='G2C-App-smoke-state.1'and value['scope_sha256']==scope,
            'actual scoped native state required')
    require(value['runtime_role']=='cj_m1_runtime'and len(value['role_flags'])==7
            and all(flag is False for flag in value['role_flags']),'original minimum runtime role required')
    messages=value['native_messages']
    rows=[[m[k]for k in('message_id','run_id','conversation_id','generation','sequence','canonical_sha256')]
          for m in messages]
    require(value['message_ids']==[r[0]for r in rows]and len({r[0]for r in rows})==len(rows),
            'complete distinct native MESSAGE census required')
    require(sha256(packed(rows)).hexdigest()==value['messages_sha256'],'native MESSAGE census digest differs')
    require(is_sha(value['trip_sha256'])and is_sha(value['memory_sha256']),'actual Trip/Saved Memory digests required')
    require(value['saved_memory_definition']=='all non-candidate current items; no extraction-job inference',
            'Saved Memory must not be confused with candidates or extraction jobs')
    return value


def _envelope(value,expected):
    require(value['version']=='G2C-App-smoke-host-read.1'
            and value['qualification_sha256']==expected['qualification_sha256'],'actual B host response required')
    roles=value['actual_roles'];require(set(roles)=={'api','worker'},'both actual native roles required')
    for role in roles.values():
        require((role['source'],role['image'],role['running'])==
                (expected['source'],expected['image'],True),'actual native source/image drift')
    require(roles['api']['health']=='healthy','actual API health missing')
    return value['original']


def collection_pending(value,expected):
    """Only B's explicit asynchronous HTTP publication can be awaited.

    It is never an observation or permission for another App action. A final
    READ must still pass every original source/owner/checkpoint check.
    """
    original=_envelope(value,expected)
    return (original['version']=='G2C-App-smoke-read.1'
            and original['status']=='UNAVAILABLE'
            and original.get('reason')=='APP_SMOKE_HTTP_OUTER_PENDING')


def _host(value,expected,plan,step,kind):
    original=_envelope(value,expected)
    require(original['version']=='G2C-App-smoke-read.1'and original['status']=='READ',
            'original protected read unavailable')
    require((original['source'],original['plan_sha256'],original['window_id'],original['nonce'],original['kind'])==
            (expected['source'],digest(plan),plan['run_id'],step['nonce'],kind),'native read source/plan/step differs')
    require(original['policy_sha256']==expected['policy_sha256']
            and original['scope_sha256']==expected['scope_sha256'],'original policy/owner differs')
    require(original['state']in('ACTIVE','STOP_NEW'),'original control state unavailable')
    return original


@dataclass(frozen=True)
class Checkpoint:
    reference:str
    native_state:dict
    ledger_anchor:dict
    claims:tuple
    history_targets:tuple=()
    default_history_target:dict|None=None


def checkpoint(value,expected,plan,step):
    original=_host(value,expected,plan,step,'checkpoint')
    require(original['state']=='ACTIVE','no new App action under STOP_NEW')
    reference=original['checkpoint_ref'];require(is_sha(reference),'actual server checkpoint reference required')
    state=_state(original['native_state'],expected['scope_sha256'])
    require(state['active']==state['pending']==0,'actual original work remains in flight')
    history=targets(plan,step['locale']);claims=tuple(original['claims'])
    require(tuple(original.get('history_targets',[]))==history,'actual B validated history targets differ from frozen plan')
    check_native(history,state)
    default=default_target(original['default_history_target'],expected['default_conversation_id'],state)
    for value in history:
        if value['conversation_id']==default['conversation_id']:
            require(value==default,'selected default history metadata differs from actual default')
    return Checkpoint(reference,state,original['ledger_anchor'],claims,history,default)


def _components(value):
    """Unwrap actual original bytes, never replace an UNAVAILABLE proof."""
    result=[];ids=set()
    for component in value:
        op=component['operation'];require(op['operation_id']not in ids,'duplicate original operation component')
        ids.add(op['operation_id']);item=dict(component)
        for source,target in(('tool_artifact','artifact'),('logical_input','logical_input')):
            wrapper=component.get(source)
            if wrapper is None:continue
            require(wrapper['status']=='READ'and type(wrapper['utf8'])is str
                    and is_sha(wrapper['sha256'])and sha256(wrapper['utf8'].encode()).hexdigest()==wrapper['sha256'],
                    'original tool input/response unavailable or changed')
            item[target]=decode(wrapper['utf8'].encode())if target=='artifact'else wrapper['utf8']
        result.append(item)
    return result


@dataclass(frozen=True)
class Observation:
    original:dict
    before:dict
    after:dict
    new_message_ids:tuple
    actual_reads:tuple
    components:tuple
    read_collection_status:str
    default_history_target:dict|None=None


def observation(value,point,expected,plan,step):
    kind='observe_read'if step['text']is None else'observe'
    original=_host(value,expected,plan,step,kind)
    before=_state(original['before'],expected['scope_sha256'])
    after=_state(original['after'],expected['scope_sha256'])
    # Client state never creates the checkpoint. This is an extra comparison
    # against the server's authenticated earlier response/reference only.
    require(before==point.native_state,'server original before checkpoint changed')
    check_native((point.default_history_target,),after)
    new=tuple(sorted(set(after['message_ids'])-set(before['message_ids'])))
    require(set(before['message_ids'])<=set(after['message_ids']),'original MESSAGE disappeared during the step')
    http=original['http']
    require(http['http_coverage']=='OBSERVED'and type(http['post_count'])is int,
            'complete HTTP attempt coverage required; observed subtotal is insufficient')
    require(http['read_coverage']in('OBSERVED','PENDING')and not http['unknown_read_exchanges'],
            'actual App read evidence was lost or refused')
    exchanges=http['read_exchanges'];started={};finished={};captured={}
    for item in exchanges:
        require(item['method']=='GET'and item['scope_sha256']==expected['scope_sha256']
                and item['policy_sha256']==expected['policy_sha256'],'actual GET attempt owner/policy differs')
        phase=item['phase'];require(phase in('started','finished','capture_result'),'unknown GET attempt phase')
        table={'started':started,'finished':finished,'capture_result':captured}[phase]
        require(item['exchange_id']not in table,'duplicate GET attempt phase')
        table[item['exchange_id']]=item
    require(sorted(set(started)-set(captured))==http['pending_read_exchanges'],
            'pending GET census differs from actual attempt records')
    if http['read_coverage']=='OBSERVED':
        require(not http['pending_read_exchanges'],'incomplete read attempts cannot be declared observed')
    reads=[];read_ids=set()
    for record in http['actual_reads']:
        require(record['scope_sha256']==expected['scope_sha256']
                and record['policy_sha256']==expected['policy_sha256']
                and record['source_commit']==expected['source'],'actual App read source/owner differs')
        require(record['method']=='GET'and record['status']==200
                and record['route']in('/v1/lio/timeline','/v2/lio/timeline','/v2/lio/messages'),
                'actual successful ordinary App read required')
        require(sha256(record['response_utf8'].encode()).hexdigest()==record['response_sha256'],
                'actual App HTTP response bytes differ')
        if record.get('origin')=='readonly_default':
            target=point.default_history_target
            require(record['route']=='/v1/lio/timeline'
                    and record['default_conversation_id']==target['conversation_id']
                    and record['default_generation']==target['generation'],
                    'actual default read owner/head differs from its native checkpoint')
            if record['binding']is not None:
                require(record['binding']['conversation_id']==target['conversation_id']
                        and record['binding']['generation']==target['generation'],
                        'nonempty default read bound another conversation/head')
        if record['binding']is None:
            target=point.default_history_target
            payload=decode(record['response_utf8'].encode())
            require(record.get('origin')=='readonly_default'and record['route']=='/v1/lio/timeline'
                    and record['selector']=={} and not target['messages']
                    and payload['version']=='LIO-timeline.1'and payload['messages']==[]
                    and payload['next_before']is None
                    and payload['conversation_id']in(None,target['conversation_id']),
                    'only the current-owner actual empty default may have no MESSAGE binding')
        exchange=record['exchange_id']
        require(exchange not in read_ids,'duplicate actual GET response exchange')
        read_ids.add(exchange)
        require(exchange in started and exchange in finished and exchange in captured,
                'read publication is not a request after the server checkpoint')
        start,end,capture=started[exchange],finished[exchange],captured[exchange]
        require(start['route']==end['route']==record['route']and end['selector']==record['selector']
                and end['status']==200 and end['body_fully_observed']is True
                and end['response_sha256']==record['response_sha256']and capture['capture_status']=='CAPTURED',
                'actual GET full-response/capture receipt differs')
        reads.append(record)
    if step['text']is None:
        require(not new and http['post_count']==0,'read-only App action sent a new MESSAGE')
    else:
        claim=original['claim'];message=original['message'];outer=original['outer_request'];inventory=original['inventory']
        mid=message['message_id'];binding=claim['binding']
        require(claim['slot_id']==step['locale']+'.'+step['gate_id']and new==(mid,),
                'unique actual current step MESSAGE required')
        require(sha256(binding['scope'].encode()).hexdigest()==expected['scope_sha256']
                and binding['message_id']==mid and binding['run_id']==message['run_id']==inventory['run_id']
                and binding['conversation_id']==message['conversation_id']
                and binding['generation']==message['generation']and binding['message_sequence']==message['sequence'],
                'actual typed claim MESSAGE/RUN/CID differs')
        require(outer['binding']==binding and outer['slot_id']==claim['slot_id']
                and outer['source_commit']==expected['source']and outer['policy_sha256']==expected['policy_sha256'],
                'actual HTTP outer binding differs')
        raw=outer['outer_utf8'];wire=decode(raw.encode())
        require(sha256(raw.encode()).hexdigest()==outer['input_sha256']==claim['input_sha256']==message['input_sha256'],
                'original native outer digest differs')
        require(claim['canonical_sha256']==outer['canonical_sha256']==message['canonical_sha256']==inventory['message_input_sha256'],
                'canonical MESSAGE digest differs from actual inventory')
        require(wire['version']==outer['protocol']==message['protocol']==plan['app']['protocol']
                and wire['text']==message['text']==step['text']and wire['locale']==message['locale']==step['locale']
                and wire['message_id']==mid,'actual App input differs from frozen step')
        require(outer['method']=='POST'and outer['route']=='/v'+wire['version'].rsplit('.',1)[1]+'/lio/messages',
                'actual native POST route/protocol differs')
        if step['new_conversation']:
            require(wire.get('new_conversation')is True and 'conversation_id'not in wire,'fresh App conversation required')
        else:
            require(wire.get('conversation_id')==message['conversation_id']and 'new_conversation'not in wire,
                    'actual seed continuation changed CID')
        posts=http['post_exchanges'];starts=[r for r in posts if r['phase']=='started'];ends=[r for r in posts if r['phase']=='finished']
        require(http['post_count']==len(starts)==len(ends)==1,'duplicate or incomplete actual POST exchange')
        start,end=starts[0],ends[0]
        for item in (start,end):
            require(item['policy_sha256']==expected['policy_sha256']and item['scope_sha256']==expected['scope_sha256']
                    and item['method']=='POST'and item['route']==outer['route'],'POST source scope differs')
        require(start['exchange_id']==end['exchange_id']and 200<=end['status']<300
                and end['message_id']==mid and end['body_fully_observed']is True
                and end['input_sha256']==claim['input_sha256'],'actual POST result/digest differs')
        require(sha256(message['answer'].encode()).hexdigest()==message['answer_sha256'],'original native answer digest differs')
    return Observation(original,before,after,new,tuple(reads),tuple(_components(original.get('components',[]))),
                       http['read_coverage'],point.default_history_target)
