"""Joint UI/native checks. None of welcome/ACK/HTTP200/completed is sufficient."""
from hashlib import sha256
import re

from .cost import costs
from .plan import decode, require, Invalid, is_sha

_PLACE=re.compile(r'故宫|颐和园|天坛|景山|胡同|长城|北海|雍和宫|国子监|天安门|798|'
    r'Forbidden City|Palace Museum|Summer Palace|Temple of Heaven|Jingshan|hutong|Great Wall|Beihai|Lama Temple|Tiananmen',re.I)
_BAD=re.compile(r'暂时还没有回答|暂时看不到对话|暂时打不开|no chat allowance|something went wrong|no answer yet',re.I)


def semantic(gate,text,locale):
    """Small auditable oracles. Unrecognized valid wording stays UNKNOWN.

    Beijing landmarks here belong only to this fixed smoke question, not a
    product city/place whitelist. They neither verify a booking nor establish G6.
    """
    if type(text)is not str or not text.strip():return 'FAIL','empty_body'
    if _BAD.search(text):return 'FAIL','failure_placeholder'
    if locale=='en'and len(re.findall('[A-Za-z]',text))<max(3,len(re.findall('[\u3400-\u9fff]',text))):
        return 'FAIL','wrong_output_language'
    if locale=='zh'and len(re.findall('[\u3400-\u9fff]',text))<2:return 'UNKNOWN','chinese_answer_not_observed'
    if gate=='SM02':
        if re.fullmatch(r'\s*(yes[.!]?|是的[。！]?|是[。！]?)\s*',text,re.I):return 'PASS','explicit_affirmation'
        if re.search(r'不是|并非|not.{0,35}capital|isn.t.{0,25}capital',text,re.I):return 'FAIL','capital_denied'
        if re.search(r'不确定|不知道|是否|don.t know|not sure|uncertain|whether',text,re.I):
            return 'UNKNOWN','capital_fact_not_affirmed'
        affirmative=(r'^\s*(?:是的[，,。！\s]*)?北京(?:市)?是(?:中华人民共和国|中国)的?首都(?:[。！.!]|$)'
                     if locale=='zh'else r'^\s*(?:Yes[,!.\s]*)?Beijing is (?:the )?capital of China(?:[.!]|$)')
        return ('PASS','capital_fact')if re.search(affirmative,text,re.I)else('UNKNOWN','capital_semantics_unresolved')
    if gate=='SM05':
        if re.search(r'不是\s*Lio|not\s+Lio',text,re.I):return 'FAIL','identity_denied'
        identity=re.search(r'(?:我是|我叫)\s*Lio|\b(?:I am|I.m|This is)\s+Lio\b',text,re.I)
        return ('PASS','lio_identity')if identity else('UNKNOWN','identity_not_established')
    if gate=='SM06':
        if re.search(r'(?:不能|无法).*?(?:规划|行程|旅行)|(?:cannot|can.t|do not|don.t|not able to|unable to)(?:\s+[A-Za-z]+){0,5}\s+(?:plan\w*|travel|itinerar\w*)|(?:travel|planning|itinerary).{0,30}unavailable',text,re.I):
            return 'FAIL','travel_capability_denied'
        positive=(r'我(?:可以|能|会|擅长|帮)[^。！？\n]{0,35}(?:规划|行程|旅行|天气|景点|住宿)'
                  if locale=='zh'else r'\bI (?:can (?!not\b)|help\b|offer\b|provide\b|am able to\b)[^.!?\n]{0,65}\b(?:plan\w*|itinerar\w*|travel|weather|accommodation|attractions)\b')
        return ('PASS','travel_capability')if re.search(positive,text,re.I)else('UNKNOWN','travel_capability_not_affirmed')
    if gate=='SM07':
        if not re.search(r'北京|Beijing',text,re.I):return 'UNKNOWN','plan_city_not_established'
        marker=re.compile(r'第\s*([123一二三])\s*天|\bDay\s*([123])\b',re.I)
        hits=list(marker.finditer(text));days={}
        for i,hit in enumerate(hits):
            key=hit[1]or hit[2];key={'一':'1','二':'2','三':'3'}.get(key,key)
            segment=text[hit.end():hits[i+1].start()if i+1<len(hits)else len(text)]
            days.setdefault(key,[]).append(segment)
        if set(days)!={'1','2','3'}:return 'FAIL','three_complete_days_missing'
        if any(len(parts)!=1 for parts in days.values()):return 'UNKNOWN','ambiguous_day_projection'
        if not all(_PLACE.search(parts[0])for parts in days.values()):
            return 'UNKNOWN','concrete_day_venues_require_independent_review'
        if re.search(r'稍后.*(?:生成|提供)|行程待生成|will (?:generate|provide).*later',text,re.I):
            return 'FAIL','plan_is_promise_not_result'
        return 'PASS','concrete_three_day_smoke_plan'
    return 'UNKNOWN','no_semantic_oracle'


def _same(value,expected,keys,reason):
    require(all(value.get(key)==expected[key]for key in keys),reason)


def judge(plan,step,observation,context,pricing):
    """Consume facts obtained by qualified adapters, not imported PASS labels.

    context is this execution's pinned owner/candidate and freshly issued nonce.
    Adapter raw artifacts remain with the run; this function grants no capability.
    """
    reasons=[];fail=[];unknown=[];money=None
    try:
        require(observation.get('version')=='LIO-basic-chain-observation.1','original observation version required')
        _same(observation,dict(run_id=plan['run_id'],gate_id=step['gate_id'],locale=step['locale'],nonce=step['nonce']),
              ('run_id','gate_id','locale','nonce'),'wrong run/gate/locale/nonce')
        _same(observation['binding'],context,('source','image','schema','subject','qualification_sha256'),'candidate/owner/qualification changed')
        _same(observation['app'],plan['app'],('build','source_sha','artifact_sha256','protocol'),'wrong App artifact/mode')
        require(observation['app']['ordinary_home']is True,'ordinary Home required')
        ui=observation['ui'];backend=observation['backend']
        require(ui['producer_ref']and ui['artifacts_verified']is True,'A original UI artifacts missing')
        require(backend['protected_read_verified']is True and backend['source_unchanged']is True,'native protected read/source missing')
        require(is_sha(backend['evidence_sha256']),'native evidence original reference required')
        money=costs(backend['accounting'],pricing)
        if not money['full_coverage']:unknown.append('foreground_background_accounting_not_closed')
        if money['unresolved_attempt_count']:unknown.append('unresolved_original_attempt_or_model_usage')
        if ui.get('error_visible')is True or ui.get('spinner_past_deadline')is True:fail.append('App_visible_failure')
        if backend.get('unexpected_mutation')is True:fail.append('unexpected_native_side_effect')
        gate=step['gate_id']
        if step['text'] is None:
            require(backend['new_message_ids']==[],'read-only check must not send new messages')
            require(money['attempt_count']==0,'read-only step created paid/background operation')
            before=backend['before'];after=backend['after']
            require(before['memory_sha256']==after['memory_sha256']and before['trip_sha256']==after['trip_sha256'],
                    'read-only check changed Trip or Memory')
            if gate in ('SM01','SM04'):
                expected_cid=context['old_cid']if gate=='SM01'else context['qa_cid']
                require(ui['before_cid']==expected_cid==ui['after_cid']==backend['conversation_id'],'conversation continuity missing')
                require(ui['messages_visible']is True and ui['draft_before']==ui['draft_after'],'old messages/draft not restored')
                require(ui['new_greeting_count']==0,'new greeting inserted')
                require(backend['expected_message_ids_present']is True,'expected original messages missing')
                if gate=='SM04':require(ui['background_returned']is True and ui['lock_returned']is True,'both transitions required')
            elif gate=='SM03':
                require({context['old_cid'],context['qa_cid']}<=set(ui['listed_cids']),'old/new local history entries missing')
                require(ui['selected_cids_verified']is True,'listed entries did not open correct CIDs')
            else:unknown.append('unsupported_read_only_gate')
        else:
            original=backend['message'];outer=backend['outer_request']
            require(outer['provenance']=='B_actual_HTTP_boundary'and outer['protected_capture_verified']is True,
                    'actual protected HTTP outer original required; reconstructed JSON is not evidence')
            wire=decode(outer['utf8'].encode())
            require(wire.get('version')==plan['app']['protocol']and wire.get('locale')==step['locale']
                    and wire.get('text')==step['text'],'actual App outer input changed')
            require(outer['method']=='POST'and outer['route']=='/v'+plan['app']['protocol'].rsplit('.',1)[1]+'/lio/messages',
                    'actual native HTTP route/protocol differs')
            if step['new_conversation']:
                require(wire.get('new_conversation')is True and 'conversation_id'not in wire,'fresh user conversation required')
            else:
                require(wire.get('conversation_id')==context['old_cid'] and 'new_conversation'not in wire,'seed continuation changed conversation')
            require(wire.get('message_id')==original['message_id']==ui['render_source_mid'],'UI/native MID mismatch')
            require(sha256(outer['utf8'].encode()).hexdigest()==outer['sha256']==original['outer_input_sha256'],
                    'actual outer SHA mismatch')
            require(is_sha(original['canonical_sha256'])and original['canonical_sha256']==backend['inventory']['message_input_sha256'],
                    'native canonical input SHA mismatch')
            require(original['run_id']==backend['inventory']['run_id'],'native RUN mismatch')
            require(original['conversation_id']==ui['after_cid'],'native CID mismatch')
            require(backend['new_message_ids']==[original['message_id']],'unplanned additional MESSAGE')
            require(backend['bounded_claim_verified']is True,'B bounded actual App claim missing')
            require(original['native_origin_verified']is True,'actual native origin evidence missing')
            require(ui['post_count']==1,'App duplicate/absent POST')
            if backend['inventory']['status']=='unknown':unknown.append('native_RUN_UNKNOWN')
            elif backend['inventory']['status']!='completed':fail.append('native_RUN_not_completed')
            require(is_sha(original['answer_sha256'])and sha256(original['answer'].encode()).hexdigest()==original['answer_sha256'],
                    'original answer digest differs')
            require(ui['received_answer_sha256']==original['answer_sha256'],'App did not receive this original answer')
            require(ui['answer_visible']is True,'actual original answer not displayed')
            timing=backend['timing']
            require(timing['source']=='A_actual_App_monotonic','actual App timing required')
            for key in ('first_body_ms','complete_ms'):
                require(type(timing[key])in(int,float)and 0<=timing[key]<=90_000,'bounded actual body/completion time required')
            require(timing['first_body_ms']<=timing['complete_ms'],'body arrived after completion')
            progress=timing['first_progress_ms']
            require((progress is None and timing['progress_status']=='NOT_EMITTED')or
                    (type(progress)in(int,float)and 0<=progress<=timing['complete_ms']
                     and timing['progress_status']=='OBSERVED'),'actual progress timing or explicit absence required')
            for label,text in [('native',original['answer']),('App',ui['visible_answer'])]:
                if step['kind']=='setup':
                    marker='SYNTH-OLD-'+plan['run_id']+'-'+step['locale']
                    status,reason=('PASS','seed_code_recalled')if marker in text else('UNKNOWN','seed_code_not_observed')
                else:status,reason=semantic(gate,text,step['locale'])
                reasons.append(label+':'+reason)
                if status=='FAIL':fail.append(label+':'+reason)
                elif status=='UNKNOWN':unknown.append(label+':'+reason)
            if gate!='SM07':
                require(backend['before']['trip_sha256']==backend['after']['trip_sha256'],'ordinary QA wrote a Trip')
            else:
                require(backend['itinerary_verified']is True and ui['three_day_readback_verified']is True,
                        'actual itinerary object/readback missing')
                require(backend['unrequested_date_or_party']is False,'plan invented a date or party size')
                if backend['claims_saved']is True or plan['app']['protocol']in('LIO-message.3','LIO-message.4'):
                    require(backend['save_receipt_verified']is True and backend['trip_readback_verified']is True,'actual saved version/history missing')
                else:
                    require(backend['before']['trip_sha256']==backend['after']['trip_sha256'],'legacy preview unexpectedly persisted Trip')
            require(backend['before']['memory_sha256']==backend['after']['memory_sha256'],'unrequested saved Memory activation')
        status='FAIL'if fail else'UNKNOWN'if unknown else'PASS'
        return dict(gate_id=step['gate_id'],locale=step['locale'],status=status,reasons=[*fail,*unknown,*reasons],
            cost=money,evidence_sha256=backend['evidence_sha256'],native_status=backend.get('inventory',{}).get('status'),
            timing=backend.get('timing'))
    except (Invalid,KeyError,TypeError,ValueError) as error:
        return dict(gate_id=step['gate_id'],locale=step['locale'],status='FAIL'if fail else'UNKNOWN',
            reasons=[*fail,*unknown,'required_joint_evidence_unavailable:'+type(error).__name__],
            cost=money or dict(conservative_cny=None,token_estimate_cny=None,actual_paid_cny=None,full_coverage=False),timing=None)
