"""Joint uniqueness checks for ordinary Home, which does not expose native IDs.

This is an assessment, not an authority or release certificate. A supplies actual
AX facts, B supplies native facts, and the admitted client renderer supplies the
exact text projection. No approximate whitespace or time-only join is used.
"""
from dataclasses import dataclass,field

from cj_message.lio_context import display_answer

from .plan import Invalid,require
from .semantics_v2 import semantic


@dataclass
class Conversations:
    views:dict=field(default_factory=dict)
    old_cid:str|None=None
    qa_cid:str|None=None
    history_targets:dict=field(default_factory=dict)


def _transcript(view,project):
    return tuple((m['text'],project(m['answer']))for m in view['messages'])


def _ax_transcript(value):
    require(type(value)is list,'complete ordered actual AX transcript required')
    return tuple((entry['question'],entry['answer'])for entry in value)


def draft_marker(plan,step):
    return 'SYNTH-DRAFT-'+plan['run_id']+'-'+step['locale']+'-'+step['gate_id']


def _views(native):
    from .plan import decode
    pages={};expected={}
    require(native.read_collection_status=='OBSERVED','actual App read collection is not closed')
    for record in native.actual_reads:
        if record['route']not in('/v1/lio/timeline','/v2/lio/timeline'):continue
        view=decode(record['response_utf8'].encode())
        require(view['version']in('LIO-timeline.1','LIO-timeline.2'),'ordinary actual timeline required')
        if record['binding']is None:
            cid=native.default_history_target['conversation_id']
        else:
            cid=record['binding']['conversation_id']
            require(view['conversation_id']==cid,'actual read selected another CID')
        if not all(m['status']=='completed'and m['failure']is None for m in view['messages']):continue
        rows=sorted((m for m in native.after['native_messages']if m['conversation_id']==cid),key=lambda m:m['sequence'])
        expected[cid]=[m['message_id']for m in rows]
        cursor=record['selector'].get('before')
        if cursor is not None and cursor not in expected[cid]:continue
        eligible=expected[cid]if cursor is None else expected[cid][:expected[cid].index(cursor)]
        mids=[m['message_id']for m in view['messages']]
        # A pre-accept poll cannot be the final page if its suffix lacks the
        # newly admitted MESSAGE. Page publication order is never authority.
        if (not mids and eligible)or mids and mids!=eligible[-len(mids):]:continue
        if view['next_before']is not None and(not mids or view['next_before']!=mids[0]):continue
        key=(view['version'],view['next_before'],tuple((m['message_id'],m['text'],m['answer'])for m in view['messages']))
        pages.setdefault(cid,{}).setdefault(cursor,{})[key]=(view,record['exchange_id'])
    result={}
    for cid,by_cursor in pages.items():
        cursor=None;seen=set();chunks=[];refs=[];root=None
        while cursor not in seen:
            seen.add(cursor);variants=by_cursor.get(cursor,{})
            if len(variants)!=1:break
            page,ref=next(iter(variants.values()))
            if root is None:root=page
            if page['version']!=root['version']:break
            chunks.append(page['messages']);refs.append(ref)
            cursor=page['next_before']
            if cursor is None:
                merged=[message for chunk in reversed(chunks)for message in chunk]
                if [m['message_id']for m in merged]==expected[cid]:
                    # Internal transcript reference, never a rewritten raw
                    # response. All original page bytes/hashes remain above.
                    result[cid]=dict(root,messages=merged,next_before=None,
                        view_origin='actual_GET_cursor_chain',source_exchange_ids=refs)
                break
    return result


def _ui(ui,plan,step):
    require(ui['version']=='LIO-basic-app-witness.2'and ui['source']=='actual_ordinary_Home_AX',
            'actual ordinary Home witness required')
    require((ui['run_id'],ui['gate_id'],ui['locale'],ui['nonce'])==
            (plan['run_id'],step['gate_id'],step['locale'],step['nonce']),'A witness belongs to another step')
    require(ui['app']==plan['app'],'actual tested App differs')
    require(ui['message_id_observed']is None and ui['conversation_id_observed']is None,
            'ordinary AX must not pretend B IDs were independently observed')
    require(type(ui['artifacts'])is list and ui['artifacts'],'actual full AX/screenshot originals required')


def _timing(ui,step):
    if step['text']is None:return ui.get('timing')
    timing=ui['timing'];require(timing['clock']=='actual_App_monotonic','actual App timing required')
    for key in ('first_body_ms','complete_ms'):
        require(type(timing[key])in(int,float)and 0<=timing[key]<=90_000,'actual bounded body/completion required')
    require(timing['first_body_ms']<=timing['complete_ms'],'body timing follows completion')
    progress=timing['first_progress_ms']
    require((progress is None and timing['progress_status']in('NOT_EMITTED','NOT_OBSERVED'))or
            (type(progress)in(int,float)and 0<=progress<=timing['complete_ms']
             and timing['progress_status']=='NATIVE_PROGRESS_OBSERVED'and timing['native_progress_ref']),
            'local greeting/ACK cannot supply a native progress time')
    return timing


def assess(plan,step,point,native,ui,conversations,project,money):
    """project is the actual admitted same-source renderer, never a model.

    Updates the accepted in-window conversation census only after PASS. The
    caller verifies producer programs and artifact bytes; these facts do not
    claim a physical device when the actual surface is a simulator.
    """
    fail=[];unknown=[];reasons=[];next_view=None;timing=None;accepted_views=dict(conversations.views)
    try:
        _ui(ui,plan,step)
        if ui['after']['errors']or ui['after'].get('spinner_past_deadline')is True:
            fail.append('actual_App_visible_failure')
        if step['gate_id']=='SM03':
            if any(entry['errors']for entry in ui['history']['opened']):fail.append('actual_history_row_open_failure')
        if step['gate_id']in('SM01','SM04'):
            if any(entry['errors']for entry in ui['lifecycle']):fail.append('actual_intermediate_lifecycle_failure')
        require(ui['after']['body_complete']is True,'actual final AX has not completed')
        if not money['full_coverage']or money['unresolved_attempt_count']:
            unknown.append('original_all_producer_or_accounting_evidence_incomplete')
        before,after=native.before,native.after
        if before['memory_sha256']!=after['memory_sha256']:fail.append('unrequested_Saved_Memory_mutation')
        views=_views(native)
        gate=step['gate_id'];actual_ax=_ax_transcript(ui['after']['transcript'])
        if step['text']is not None:
            require(ui['send_taps']==1 and ui['submitted_text']==step['text'],'one actual UI tap/exact input required')
            original=native.original;message=original['message'];cid=message['conversation_id']
            if original['inventory']['status']=='unknown':unknown.append('original_RUN_UNKNOWN')
            elif original['inventory']['status']!='completed':fail.append('original_RUN_not_completed')
            require(cid in views,'actual App final timeline/response is missing')
            view=views[cid]
            require(view['messages'][-1]['message_id']==message['message_id']
                    and view['messages'][-1]['answer']==display_answer(message['answer'],step['locale']),
                    'actual App response differs from same-source server projection of original native answer')
            if step['new_conversation']:
                require('new_chat'in ui['actions']and _ax_transcript(ui['before']['transcript'])==(),
                        'actual new-chat transition and empty pre-send transcript required')
                require(len(view['messages'])==1,'new conversation contains other user messages')
            else:
                require(cid==conversations.old_cid,'seed continuation changed its original CID')
            require(actual_ax==_transcript(view,project),'actual complete AX differs from original renderer projection')
            if step['kind']=='setup':
                if gate=='SEED2':
                    marker='SYNTH-OLD-'+plan['run_id']+'-'+step['locale']
                    if marker not in message['answer']:unknown.append('original_chat_code_not_recalled')
            else:
                status,reason=semantic(gate,message['answer'],step['locale']);reasons.append(reason)
                if status=='FAIL':fail.append(reason)
                elif status=='UNKNOWN':unknown.append(reason)
            # This profile is the explicit ordinary-v2 preview cohort. It does
            # not certify native3/4 autosave or silently inherit their writer.
            if before['trip_sha256']!=after['trip_sha256']:fail.append('unexpected_formal_Trip_mutation')
            if gate=='SM07':
                require(plan['app']['protocol']=='LIO-message.2','separate native3/4 save qualification required')
                require(ui['after']['three_day_readback']is True,'all three actual itinerary days must be readable')
                require(view['messages'][-1]['trip']is None,'preview cannot masquerade as a formal saved card')
            timing=_timing(ui,step);next_view=view
        else:
            require(ui['send_taps']==0 and ui['submitted_text']is None and not native.new_message_ids,
                    'read-only UI action submitted a new message')
            if before['trip_sha256']!=after['trip_sha256']:fail.append('read_only_Trip_mutation')
            require(ui['after']['new_greeting_count']==0,'restored conversation inserted a new greeting')
            claimed={c['binding']['conversation_id']for c in point.claims}
            historical={value['conversation_id']:value for value in point.history_targets}
            require(historical==conversations.history_targets,'actual old history targets differ from accepted metadata')
            claimed|=set(historical)
            default=point.default_history_target;default_cid=default['conversation_id']
            required=claimed|{default_cid}
            require(required==set(conversations.views)|set(historical)|{default_cid},
                    'admissible current-window candidate census is incomplete')
            # Body references only enter from actual App GET responses whose
            # source/owner/exchange and full native MESSAGE census were checked.
            for cid in (set(historical)|{default_cid})-accepted_views.keys():
                if cid in views:accepted_views[cid]=views[cid]
            if gate=='SM03':require(required<=set(views),'actual App reads do not cover every local/default candidate')
            if gate in('SM01','SM04'):
                nonempty=required if default['messages']else required-{default_cid}
                require(nonempty<=set(accepted_views),'complete old candidate bodies are not available for a unique restore')
                expected_cid=conversations.old_cid if gate=='SM01'else conversations.qa_cid
                require(expected_cid in views,'required actual App restore/resume read is missing')
                require(ui['before']['draft']==ui['after']['draft']==draft_marker(plan,step),'unique unsent draft changed or was not prepared')
                matches=[cid for cid,view in accepted_views.items()if _transcript(view,project)==actual_ax]
                require(matches==[expected_cid],'actual restored transcript has no unique native CID match')
                require(_ax_transcript(ui['before']['transcript'])==actual_ax,'original conversation differed before lifecycle action')
                require(actual_ax==_transcript(views[expected_cid],project),'actual App read did not restore the original full transcript')
                require('cold_launch'in ui['actions']if gate=='SM01'else
                        ui['actions']==[step['action']],'required actual lifecycle transition missing')
                checkpoints=ui['lifecycle'];action='cold_launch'if gate=='SM01'else step['action']
                require(len(checkpoints)==1 and checkpoints[0]['action']==action,
                        'the immediate independently admitted lifecycle snapshot is required')
                for entry in checkpoints:
                    require(_ax_transcript(entry['transcript'])==actual_ax
                            and entry['draft']==draft_marker(plan,step)and not entry['errors']and entry['body_complete']is True,
                            'the immediate lifecycle result failed; later navigation cannot repair it')
                if gate=='SM04':
                    require(any(r['binding']is not None and r['binding']['conversation_id']==expected_cid
                                 and r['route']in('/v1/lio/timeline','/v2/lio/timeline')for r in native.actual_reads),
                            'this lifecycle action needs its own checkpoint-fenced actual App read')
            elif gate=='SM03':
                rows=ui['history']['rows'];opened=ui['history']['opened']
                require(len(rows)==len(opened)==len(required),'every listed admissible/default row must be opened')
                require(len({r['row_key']for r in rows})==len(rows)
                        and {r['row_key']for r in rows}=={r['row_key']for r in opened},'history row/open census differs')
                default_key=ui['history']['default_row_key']
                require(rows[-1]['row_key']==default_key
                        and [row['row_key']for row in rows]==[row['row_key']for row in opened],
                        'actual signed.history default is the final row; every row must be opened in observed order')
                found=[]
                for entry in opened:
                    require(entry['body_complete']is True and not entry['errors'],
                            'each opened history row needs its own complete error-free actual result')
                    transcript=_ax_transcript(entry['transcript'])
                    matches=([default_cid]if transcript==_transcript(views[default_cid],project)else[])if entry['row_key']==default_key else[
                        cid for cid,view in accepted_views.items()if cid!=default_cid and _transcript(view,project)==transcript]
                    require(len(matches)==1,'history selected row cannot uniquely identify a native conversation')
                    cid=matches[0];require(transcript==_transcript(views[cid],project),'actual history read differs')
                    found.append(cid)
                require(set(found)==required and len(found)==len(set(found)),'history opens duplicated or missed a native CID')
            else:unknown.append('unsupported_read_gate')
        status='FAIL'if fail else'UNKNOWN'if unknown else'PASS'
    except (Invalid,KeyError,TypeError,ValueError)as error:
        unknown.append('required_joint_evidence_unavailable:'+type(error).__name__)
        status='FAIL'if fail else'UNKNOWN'
    if status=='PASS':conversations.views.update(accepted_views)
    if status=='PASS'and next_view is not None:
        cid=next_view['conversation_id'];conversations.views[cid]=next_view
        if step['gate_id']in('SEED1','SEED2'):conversations.old_cid=cid
        elif step['gate_id']=='SM02':conversations.qa_cid=cid
    return dict(version='LIO-basic-joint-assessment.2',gate_id=step['gate_id'],locale=step['locale'],
        status=status,reasons=[*fail,*unknown,*reasons],cost=money,timing=timing,
        ui_message_id_observed=None,ui_conversation_id_observed=None,
        native_ids_source='B_actual_protected_HTTP_claim_and_state',
        join_method='bounded_single_writer_exact_input_complete_renderer_AX_and_current_actual_reads',
        evidence_scope='DATA_ASSESSMENT_ONLY_NOT_A_RELEASE_CERTIFICATE')
