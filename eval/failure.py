"""Bounded diagnostic categories; neither a model judge nor a retry policy."""
from contextlib import contextmanager
from hashlib import sha256
import logging
import re

CATEGORIES=('integration_protocol','source_tool','model_quality','judge','environment','UNKNOWN')
PATTERN=re.compile(r'M4_MODEL_UNKNOWN attempt_sha256=([0-9a-f]{64}) phase=([a-z_]{1,64}) '
    r'http_status=(None|[1-5][0-9]{2}) done=(True|False) finished=(True|False) usage=(True|False) '
    r'content_chars=([0-9]{1,9}) tool_count=([0-9]{1,4})$')


def parse_audit(text):
    result=[]
    for line in text.splitlines():
        start=line.find('M4_MODEL_UNKNOWN ')
        if start<0:continue
        match=PATTERN.fullmatch(line[start:])
        if match is None:continue  # Never retain arbitrary logger text/content.
        digest,phase,status,done,finished,usage,chars,tools=match.groups()
        result.append(dict(attempt_sha256=digest,phase=phase,http_status=None if status=='None' else int(status),
            done=done=='True',finished=finished=='True',usage=usage=='True',content_chars=int(chars),tool_count=int(tools)))
    return result


@contextmanager
def capture(evidence):
    class Handler(logging.Handler):
        def emit(self,record):
            events.extend(parse_audit(record.getMessage()))
    events=[];handler=Handler();logger=logging.getLogger('cj_provider.audit');logger.addHandler(handler)
    try:yield
    finally:
        logger.removeHandler(handler)
        evidence['provider_failure_diagnostics']=evidence.get('provider_failure_diagnostics',[])+events


def classify(raw,verdict):
    if verdict=='PASS':return None
    stage=raw.get('execution_stage');error=raw.get('error_kind')
    ids={sha256(op['attempt_id'].encode()).hexdigest() for op in raw.get('operations',[])}
    diagnostics=[d for d in raw.get('provider_failure_diagnostics',[]) if d['attempt_sha256'] in ids]
    if error and stage=='independent_judge':category='judge';reason='independent_judge_raised'
    elif error in ('OSError','FileNotFoundError','PermissionError','ModuleNotFoundError'):
        category='environment';reason=error
    elif diagnostics:
        diagnostic=diagnostics[-1];stage=diagnostic['phase']
        category='environment' if stage=='transport' and diagnostic['http_status'] is None else 'integration_protocol'
        reason='original_provider_failure_phase'
    elif any(h['status']>=400 for h in raw.get('http',[])):
        http=next(h for h in reversed(raw['http']) if h['status']>=400)
        category='environment' if http['status'] in (408,429,503) else 'integration_protocol'
        stage='api.'+http['name'];reason='original_http_'+str(http['status'])
    else:
        pending=[r for r in raw.get('authorization_attempts',[]) if r['state']=='INTENT']
        tools=[r for r in pending if r['kind']!='model']
        if tools:category='source_tool';stage='tool.'+tools[0]['kind'];reason='original_tool_intent_without_receipt'
        elif pending:category='integration_protocol';stage='model';reason='original_model_intent_without_receipt'
        else:
            bad=[r for r in raw.get('authorization_attempts',[]) if r['kind'] in ('place','route','weather')
                 and r.get('receipt') is not None and r['receipt'].get('result_status')!=('observed' if r['kind']=='weather' else 'ok')]
            observed=raw.get('observed') or {}
            if bad:category='source_tool';stage='tool.'+bad[0]['kind'];reason='original_tool_result_not_usable'
            elif observed.get('run_status') in ('unknown','failed','cancelled'):
                category='integration_protocol';stage='run';reason='original_RUN_not_completed'
            else:
                proof=raw.get('judgment') or {}
                failed=[c['name'] for c in proof.get('checks',[]) if c['status']=='FAIL'] if proof.get('kind')=='program' and proof.get('independent') else []
                if failed and set(failed)<=set(('max_days','max_daily_items','budget_limit','verified_transfer_feasibility')):
                    category='model_quality';stage='completed_output_constraint';reason=','.join(failed)
                elif failed:category='integration_protocol';stage='independent_state';reason=','.join(failed)
                else:category='UNKNOWN';reason='insufficient_machine_evidence'
    return dict(category=category,stage=stage or 'UNKNOWN',reason=reason,root_cause='UNKNOWN',
        provider_diagnostics=diagnostics,
        scope='Evidence component/effect only; not vendor blame, finish-reason inference or a new verdict')
