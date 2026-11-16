"""One serial server-side smoke; A's real UI producer uses private handoff files.

No MESSAGE sender exists here. Prepare UI -> server checkpoint -> actual UI
action -> collect original evidence. Tokens stay inside B's issued client.
"""
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
import time
from pathlib import Path

from cj_api.local_app import ISSUER,scope_for
from cj_message import lio_context
from cj_message.demo_dialogue import lio_conversation

from . import native
from .cost_v2 import costs
from .joint_v2 import Conversations,assess,draft_marker
from .history_v2 import targets
from .plan import VERSION,Invalid,check_plan,decode,digest,packed,require
from .runner import Programs,day_guard,private_read,save


def _original_files(entries):
    require(type(entries)is list and entries,'actual producer originals required')
    for entry in entries:
        require(sha256(private_read(entry['path'])).hexdigest()==entry['sha256'],'producer artifact bytes changed')


def _wait(path,deadline,clock,sleep):
    while clock()<deadline:
        if path.exists():return decode(private_read(path))
        sleep(.25)
    raise Invalid('actual UI handoff deadline reached; no new action may be replayed')


def _request(plan,step,kind,reference=None):
    value=dict(version='G2C-App-smoke-read-request.1',kind=kind,message_id=None,operation_id=None,
               plan_sha256=digest(plan),nonce=step['nonce'],locale=step['locale'])
    if reference is not None:value['checkpoint_ref']=reference
    return value


def _actions(plan):
    for index,parent in enumerate(plan['steps']):
        if parent['gate_id']=='SM04':
            for number,action in enumerate(parent['read_actions'],1):
                yield f'{index:02d}-{number}',dict(parent,**action,parent_nonce=parent['nonce'])
        else:yield f'{index:02d}',parent


def _gate_rows(plan,results):
    rows=[]
    for step in plan['steps']:
        if step['kind']!='gate':continue
        found=[r for r in results if(r['gate_id'],r['locale'])==(step['gate_id'],step['locale'])]
        if step['gate_id']=='SM04':
            status=('FAIL'if any(r['status']=='FAIL'for r in found)else
                    'UNKNOWN'if any(r['status']=='UNKNOWN'for r in found)else
                    'PASS'if len(found)==2 and all(r['status']=='PASS'for r in found)else'UNRUN')
            rows.append(dict(gate_id=step['gate_id'],locale=step['locale'],status=status,actions=found))
        else:rows.append(found[0]if found else dict(gate_id=step['gate_id'],locale=step['locale'],status='UNRUN'))
    return rows


def _purpose(config,plan):
    raw=private_read(config['purpose_receipt']['path'])
    require(sha256(raw).hexdigest()==config['purpose_receipt']['sha256'],'B original purpose receipt changed')
    value=decode(raw);profile=plan['execution_profile']
    require(value['version']=='G2C-App-smoke-purpose-restriction-result.1'
            and value['state']=='C_PURPOSE_RESTRICTED_ACKED_NOT_A_LEASE'and value['new_money_cny']==0
            and value['native_account_quota_changed']is False,'actual original tighter purpose receipt required')
    require((value['cash_ceiling_cny'],value['model_call_bound'],value['tool_call_bound'])==
            (profile['cash_ceiling_cny'],profile['model_call_upper'],profile['total_tool_call_upper']),
            'actual purpose cash/call limits differ from revised quote')
    require(value['restricted_policy']['cap']==value['baseline_policy']['cap']==100*config['pricing']['scale']
            and value['restricted_policy']['active_cap']<=value['baseline_policy']['active_cap'],
            'original C100 or its stricter cap changed')
    used=value['original_usage'];restricted=value['restricted_policy']
    require(restricted['active_cap']==min(value['baseline_policy']['active_cap'],
                used['total']+profile['cash_ceiling_cny']*config['pricing']['scale'])
            and restricted['model_calls']==used['model_calls']+profile['model_call_upper']
            and restricted['tool_calls']==used['tool_calls']+profile['total_tool_call_upper']
            and restricted['max_calls']==used['calls']+profile['model_call_upper']+profile['total_tool_call_upper'],
            'actual original usage and purpose restriction do not match')


def execute(plan,config,directory,*,now=lambda:datetime.now(timezone.utc),clock=time.monotonic,sleep=time.sleep,call=None):
    check_plan(plan)
    require(plan['version']==VERSION and config['version']=='LIO-basic-chain-host.2','current append-only execution versions required')
    require(config['app']==plan['app']and config['synthetic_only']is True,'actual synthetic App candidate required')
    require(plan['app']['surface']in('simulator','physical_device'),'actual App surface required')
    require(plan['app']['protocol']=='LIO-message.2','this ordinary-Home cohort is not native3/4 autosave acceptance')
    require(sha256(Path(lio_context.__file__).read_bytes()).hexdigest()==config['candidate']['display_answer_source_sha256'],
            'local server display projection differs from B actual deployed source qualification')
    _purpose(config,plan)
    contexts={language:Conversations(
        old_cid=None if plan['first_setup']else plan['old_chats'][language]['conversation_id'],
        history_targets={value['conversation_id']:value for value in targets(plan,language)})for language in('zh','en')}
    root=Path(directory);root.mkdir(mode=0o700,exist_ok=False)
    save(root/'plan.json',plan)
    controls=call is not None
    call=call or Programs(config,root)
    results=[];attempts=set();stopped=False;read_references=set()
    for stem,step in _actions(plan):
        if stopped:break
        reference=None;money=None
        try:
            day_guard(now())
            state=contexts[step['locale']]
            instruction=dict(version='LIO-basic-ui-instruction.2',run_id=plan['run_id'],step=step,app=plan['app'],
                expected_draft=draft_marker(plan,step)if step['gate_id']in('SM01','SM04')else None,
                accepted_conversations=state.views,
                rule=('Read-only preparation may open history and read necessary candidates solely to select the target chat. '
                      'Do not send, terminate, background, lock or perform the official SM03 history inspection until admission. '
                      'Preparation reads cannot satisfy gate evidence after the server checkpoint.'))
            save(root/f'{stem}-prepare.json',instruction)
            prepared=_wait(root/f'{stem}-A-prepared.json',clock()+config['ui_prepare_seconds'],clock,sleep)
            require(prepared['version']=='LIO-basic-app-prepared.2'
                    and (prepared['run_id'],prepared['nonce'])==(plan['run_id'],step['nonce'])
                    and prepared['send_taps']==0 and prepared['app']==plan['app'],
                    'actual read-only UI preparation differs')
            _original_files(prepared['artifacts'])
            scope=scope_for(ISSUER,config['subjects'][step['locale']])
            expected=dict(config['candidate'],scope_sha256=sha256(scope.encode()).hexdigest(),
                          default_conversation_id=lio_conversation(scope))
            request=_request(plan,step,'checkpoint');request['expected_source']=expected['source']
            host=call('backend',request)
            point=native.checkpoint(host,expected,plan,step);reference=point.reference
            require(reference not in read_references,'server checkpoint reused across distinct actions')
            read_references.add(reference)
            day_guard(now())
            save(root/f'{stem}-admission.json',dict(version='LIO-basic-ui-admission.2',run_id=plan['run_id'],
                nonce=step['nonce'],checkpoint_ref=reference,qualification_sha256=expected['qualification_sha256']))
            ui=_wait(root/f'{stem}-A-completed.json',clock()+config['ui_action_seconds'],clock,sleep)
            _original_files(ui['artifacts'])
            require(ui['before']==prepared['ui_before'],'A actual pre-action state changed after server checkpoint')
            kind='observe_read'if step['text']is None else'observe'
            request=_request(plan,step,kind,reference);request['expected_source']=expected['source']
            # Only explicit collection PENDING can be polled, on the same
            # original checkpoint. Transport/guard failure is never retried.
            collection_end=clock()+config['original_collection_seconds']
            while True:
                host=call('backend',request)
                if native.collection_pending(host,expected):
                    require(clock()<collection_end,'original HTTP publication remained PENDING')
                    sleep(.25)
                    continue
                observed=native.observation(host,point,expected,plan,step)
                original=observed.original
                terminal_unknown=step['text']is not None and original['inventory']['status']in('unknown','failed','cancelled','context_invalid')
                pending_fields={m['field']for m in original['accounting']['missing']}
                known_pending=pending_fields and pending_fields<={'native_producer_return','memory_history_producer_not_closed'}
                if terminal_unknown or observed.read_collection_status!='PENDING'and not known_pending:break
                require(clock()<collection_end,'original collection remained PENDING')
                sleep(.25)
            original=observed.original
            operations={}if step['text']is None else{o['operation_id']:o for o in original['inventory']['operations']}
            binding=dict(source_commit=expected['source'],tool_implementation_sha256=expected['tool_implementation_sha256'],
                scope_sha256=expected['scope_sha256'],message_id=None if step['text']is None else original['message']['message_id'],
                run_id=None if step['text']is None else original['message']['run_id'],ledger_id=config['native_ledger_id'],operations=operations)
            money=costs(original['accounting'],config['pricing'],observed.components,binding)
            projections={}
            def project(raw):
                if raw in projections:return projections[raw]
                value=call('projector',dict(version='LIO-reply-projection-request.1',app=plan['app'],
                    raw_utf8=raw,input_sha256=sha256(raw.encode()).hexdigest()))
                require(value['version']=='LIO-reply-projection.1'and value['app']==plan['app']
                        and value['input_sha256']==sha256(raw.encode()).hexdigest()
                        and value['renderer_source_sha256']==plan['app']['renderer_source_sha256']
                        and value['rejected']is False,'same-source actual renderer projection unavailable')
                require(sha256(value['rendered_utf8'].encode()).hexdigest()==value['rendered_sha256'],
                        'renderer projected bytes changed')
                projections[raw]=value['rendered_utf8']
                return projections[raw]
            result=assess(plan,step,point,observed,ui,state,project,money)
            for row in original['accounting']['attempts']:
                identity=(row['ledger_id'],row['attempt_id'])
                require(identity not in attempts,'overlapping step fee attempts; no aggregate total is provable')
                attempts.add(identity)
        except (Invalid,KeyError,TypeError,ValueError,OSError)as error:
            result=dict(gate_id=step['gate_id'],locale=step['locale'],status='UNKNOWN',
                        reasons=['execution_stopped:'+type(error).__name__],cost=money,timing=None)
        if 'action'in step:result['action']=step['action']
        results.append(result);save(root/f'{stem}-result.json',result)
        if result['status']!='PASS':
            stopped=True
            try:
                request=_request(plan,step,'stop_new',reference);request['expected_source']=config['candidate']['source']
                call('backend',request)
            except (Invalid,KeyError,TypeError,ValueError,OSError):
                save(root/'stop-new-UNKNOWN.json',dict(status='UNKNOWN',reason='B control receipt unavailable; C sends no further action'))
    rows=_gate_rows(plan,results)
    counts={status:sum(r['status']==status for r in rows)for status in('PASS','FAIL','UNKNOWN','UNRUN')}
    passed=counts['PASS']==14 and not stopped
    amounts=[r.get('cost')for r in results]
    complete=bool(amounts)and all(a and a['full_coverage']for a in amounts)
    total={key:(str(sum((Decimal(a[key])for a in amounts),Decimal(0)))
                if complete and all(a[key]is not None for a in amounts)else None)
           for key in('conservative_cny','token_estimate_cny','actual_paid_cny')}
    known=sum((Decimal(a['observed_conservative_cny'])for a in amounts if a and a.get('observed_conservative_cny')is not None),Decimal(0))
    report=dict(version='LIO-basic-chain-result.2',run_id=plan['run_id'],app=plan['app'],candidate=config['candidate'],
        denominator=14,rows=rows,attempt_results=results,totals=counts,success_rate=f'{counts["PASS"]}/14',
        status='PASS'if passed else results[-1]['status'],release_allowed=False,
        jt_invitation_status='UNRUN',
        service_layer='L0_CONTROL'if controls else'L2',
        app_layer='L0_CONTROL'if controls else'L1'if plan['app']['surface']=='simulator'else'L3',
        physical_device_acceptance=False,real_gate_status='UNRUN'if controls else'PASS'if passed else results[-1]['status'],
        cost=total,known_conservative_subtotal_cny=str(known),original_cost_coverage='COVERED'if complete else'UNKNOWN',
        note='Per-attempt original amounts retained. No invoice or final cost is inferred from partial coverage; UI simulator is not a tested distribution IPA.')
    save(root/'report.json',report)
    return report
