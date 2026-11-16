"""Offline slot planning, not MID allocation, capture or spending authority."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import uuid

from cj_strict_json import compact, reject_duplicates

VERSION='LIO-basic-chain-plan.1'
DESIGN=Path(__file__).resolve().parents[2]/'docs/quality/m4-stage0-1048/basic-chain-smoke.v1.json'
PROMPTS={
    'SM02':{'zh':'北京是中国的首都吗？','en':'Is Beijing the capital of China?'},
    'SM05':{'zh':'你是谁','en':'Who are you?'},
    'SM06':{'zh':'你能做啥','en':'What can you do?'},
    'SM07':{'zh':'北京三日游','en':'A three-day trip to Beijing.'},
}


class Invalid(ValueError):
    pass


def require(value,reason):
    if not value:raise Invalid(reason)


def decode(raw,limit=4_500_000):
    require(type(raw)is bytes and 0<len(raw)<=limit,'bounded original JSON required')
    def constant(_):raise Invalid('nonfinite original JSON')
    try:
        value=json.loads(raw.decode('utf8'),object_pairs_hook=reject_duplicates(Invalid,'duplicate field'),parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError) as error:
        raise Invalid('complete strict original JSON required')from error
    require(type(value)is dict,'original object required')
    return value


def packed(value):return compact(value,sort_keys=True)
def digest(value):return sha256(packed(value)).hexdigest()
def is_sha(value):return type(value)is str and re.fullmatch('[a-f0-9]{64}',value)is not None


def make_plan(*,app,old_chats,first_setup=False,run_id=None):
    """Use the real App's future allocated MIDs; null is never a wildcard."""
    raw=DESIGN.read_bytes();design=decode(raw)
    run_id=run_id or 'basic-'+datetime.now(timezone.utc).strftime('%Y%m%d')+'-'+uuid.uuid4().hex
    require(type(run_id)is str and re.fullmatch('[A-Za-z0-9_-]{1,96}',run_id)is not None,'safe new run ID required')
    require(type(first_setup)is bool,'explicit setup choice required')
    steps=[]
    if first_setup:
        for locale in ('zh','en'):
            marker='SYNTH-OLD-'+run_id+'-'+locale
            texts=([f'本段合成测试对话的代号是 {marker}，只用于本段对话，不要保存为记忆。','请复述本段对话的代号。']
                   if locale=='zh'else[f'This synthetic chat has code {marker}. Use it only in this chat, not saved memory.','Repeat this chat code.'])
            for i,text in enumerate(texts,1):
                steps.append(dict(gate_id='SEED'+str(i),locale=locale,text=text,
                    text_sha256=sha256(text.encode()).hexdigest(),new_conversation=i==1,
                    expected_mid=None,nonce=uuid.uuid4().hex,kind='setup'))
    for locale in ('zh','en'):
        for number in range(1,8):
            gate='SM'+str(number).zfill(2);text=PROMPTS.get(gate,{}).get(locale)
            steps.append(dict(gate_id=gate,locale=locale,text=text,
                text_sha256=None if text is None else sha256(text.encode()).hexdigest(),
                new_conversation=text is not None,expected_mid=None,nonce=uuid.uuid4().hex,kind='gate'))
    budget=design['budget']['first_setup'if first_setup else'standard_run']
    return dict(version=VERSION,run_id=run_id,design_sha256=sha256(raw).hexdigest(),
        synthetic_only=True,app=app,old_chats=old_chats,first_setup=first_setup,
        message_binding='REQUIRES_B_ISSUED_BOUNDED_APP_CLAIMS',
        budget_ceiling_cny=budget['requested_temporary_spend_ceiling_cny'],steps=steps,
        planned_gate_checks=14,planned_message_count=12 if first_setup else 8,
        evidence_status='UNRUN',release_allowed=False)


def check_plan(plan):
    require(plan.get('version')==VERSION and plan.get('synthetic_only')is True,'fixed synthetic basic plan required')
    require(plan.get('message_binding')=='REQUIRES_B_ISSUED_BOUNDED_APP_CLAIMS','no wildcard MID/capture mode')
    require(plan.get('planned_gate_checks')==14,'seven checks in each language required')
    expected=make_plan(app=plan['app'],old_chats=plan['old_chats'],first_setup=plan['first_setup'],run_id=plan['run_id'])
    require(plan['design_sha256']==expected['design_sha256'],'frozen design bytes changed; new plan required')
    require(plan['budget_ceiling_cny']==expected['budget_ceiling_cny'],'original quote changed')
    require(len(plan['steps'])==len(expected['steps']),'complete ordered steps required')
    nonces=set()
    for actual,wanted in zip(plan['steps'],expected['steps'],strict=True):
        require(type(actual)is dict and set(actual)==set(wanted),'exact step fields required')
        require(all(actual[key]==wanted[key] for key in wanted if key!='nonce'),'frozen input/locale/order changed')
        require(type(actual['nonce'])is str and re.fullmatch('[a-f0-9]{32}',actual['nonce'])is not None
                and actual['nonce'] not in nonces,'unique original step nonce required')
        nonces.add(actual['nonce'])
    require(plan['planned_message_count']==expected['planned_message_count'],'message bound changed')
    return plan
