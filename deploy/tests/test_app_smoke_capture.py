"""Ordinary App generated IDs: durable bounded selection, never alternate sends."""
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from cj_api.app_smoke_capture import AppSmokeCapture, VERSION, CLAIMS
from cj_api.local_app import ISSUER, scope_for
from cj_api.runtime_private import PrivateFileError
from cj_message.demo_dialogue import _identity
from cj_run.core import Binding
from cj_usage.authorization_budget import canonical, HK_PRODUCER
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.sublimits import scope_hash


SUBJECTS=('m4-synthetic-demo-aaaaaaaaaaaa','m4-synthetic-demo-bbbbbbbbbbbb')
NOW=1794804000


def write(path,value):
    path.write_bytes(canonical(value));path.chmod(0o600)


class Native:
    def __init__(self):self.rows={};self.statuses={}
    def original(self,binding,text,locale,*,native4=False):
        raw=canonical({'text':text})
        selector=({'new_conversation':True}if binding.message_sequence==1 else{'conversation_id':binding.conversation_id})
        wire=canonical(dict(version='LIO-message.2',message_id=binding.message_id,text=text,locale=locale,**selector))
        self.rows[tuple(asdict(binding).values())]=('LIO-message.1','LIO-message.4'if native4 else None,
            wire if native4 else None,locale,sha256(wire).hexdigest(),raw,sha256(raw).hexdigest())
    @contextmanager
    def connect(self,scope):
        owner=self
        class Connection:
            def execute(self,sql,args=None):
                if sql=='SET TRANSACTION READ ONLY':return None
                if sql.startswith('SELECT r.status,'):
                    return SimpleNamespace(fetchone=lambda:owner.statuses.get(tuple(args)))
                assert sql.startswith('SELECT demo_dialogue_protocol,')
                assert args[0]==scope
                # The SQL binds scope/MID/RUN/CID/generation/sequence.
                key=(args[0],args[3],args[4],args[1],args[2],args[5])
                return SimpleNamespace(fetchone=lambda:owner.rows.get(key))
        yield Connection()


class OriginalBudget:
    ledger_id='original-ledger'
    producer=HK_PRODUCER
    def __init__(self,path):self.path=path
    @contextmanager
    def connect(self):
        with sqlite3.connect('file:'+str(self.path)+'?mode=ro',uri=True)as db:yield db
    def require_producer(self,db):
        assert db.execute('SELECT producer FROM producer').fetchone()==(HK_PRODUCER,)


def fixture(tmp_path):
    tmp_path.chmod(0o700)
    claims=tmp_path/'claims';claims.mkdir(mode=0o700)
    evidence=tmp_path/'evidence';evidence.mkdir(mode=0o700)
    lock=claims/'claims.lock';lock.touch(mode=0o600)
    specs=[]
    for subject,locale in zip(SUBJECTS,('zh','en')):
        for index in range(4):
            specs.append(dict(slot_id=locale+str(index),nonce=sha256((locale+str(index)).encode()).hexdigest()[:32],
                subject=subject,locale=locale,protocol='LIO-message.2',
                text_sha256=sha256(('question-'+str(index)).encode()).hexdigest(),setup=False,
                conversation_mode='new',prior_slot_id=None))
    stamp=lambda n:datetime.fromtimestamp(n,timezone.utc).isoformat()
    ep=tmp_path/'evidence.json'
    write(ep,dict(version='G2C-runtime-evidence-window.4',directory=str(evidence),subjects=list(SUBJECTS),
        kinds=['model','tool'],source_commit='b'*40,expires_at=stamp(NOW+3600)))
    p=tmp_path/'policy.json'
    policy=dict(version=VERSION,window_id='smoke-new',source_commit='b'*40,app_source='a'*40,plan_sha256='c'*64,
        starts_at=stamp(NOW-1),ends_at=stamp(NOW+3600),directory=str(claims),
        directory_device=claims.stat().st_dev,directory_inode=claims.stat().st_ino,
        evidence_manifest=str(ep),evidence_sha256=sha256(ep.read_bytes()).hexdigest(),
        artifact_device=evidence.stat().st_dev,artifact_inode=evidence.stat().st_ino,
        slots=specs,ledger_id='original-ledger',producer_id=HK_PRODUCER)
    write(p,policy)
    write(claims/'claims.json',dict(version=CLAIMS,policy_sha256=sha256(p.read_bytes()).hexdigest(),state='ACTIVE',claims=[]))
    budget=tmp_path/'original.sqlite'
    with sqlite3.connect(budget)as db:
        db.execute('CREATE TABLE producer(producer)');db.execute('INSERT INTO producer VALUES(?)',(HK_PRODUCER,))
        db.execute('CREATE TABLE scope_sublimit(scope_hash,line)')
        db.executemany('INSERT INTO scope_sublimit VALUES(?,?)',[(scope_hash(scope_for(ISSUER,s)),'C')for s in SUBJECTS])
    clock=[NOW];database=Native();registrations={'retained':object()};authorization=OriginalBudget(budget)
    def load():return AppSmokeCapture(p,SUBJECTS,registrations,database,authorization,clock=lambda:clock[0])
    return SimpleNamespace(path=p,claims=claims,policy=policy,database=database,clock=clock,load=load,
                           registrations=registrations,budget=budget,evidence_policy=ep)


def binding(index=0,*,subject=SUBJECTS[0]):
    scope=scope_for(ISSUER,subject);mid='actual-app-uuid-'+str(index)
    return Binding(scope,'lio-dialogue-'+_identity(scope,'lio-new:'+mid),'generation',mid,'native-run-'+str(index),1)


def test_actual_ids_are_claimed_once_and_survive_restart_without_charging(tmp_path):
    f=fixture(tmp_path);a=f.load();b=binding();f.database.original(b,'question-0','zh')
    before=f.budget.read_bytes()
    assert not a.selects(b)
    assert a.registrations(b)is f.registrations and a.selects(b)
    assert a.evidence.captures_model(b)
    assert f.load().registrations(b)is f.registrations
    rows=json.loads((f.claims/'claims.json').read_bytes())['claims']
    assert len(rows)==1 and rows[0]['binding']==asdict(b) and rows[0]['slot_id']=='zh0'
    assert f.budget.read_bytes()==before
    assert a.reflection(b)is None and a.exit_observer(b)is None


def test_wrong_input_wrong_native_origin_and_extra_message_fail_before_registration(tmp_path):
    f=fixture(tmp_path);a=f.load();b=binding()
    f.database.original(b,'unplanned content','zh')
    with pytest.raises(BudgetUnknown,match='next fixed slot'):a.registrations(b)
    assert not a.selects(b)
    f.database.original(b,'question-0','zh',native4=True)
    with pytest.raises(BudgetUnknown,match='native3/4'):a.registrations(b)
    for index in range(4):
        b=binding(index);f.database.original(b,'question-'+str(index),'zh');a.registrations(b)
    b=binding(4);f.database.original(b,'question-4','zh')
    with pytest.raises(BudgetUnknown,match='next fixed slot'):a.registrations(b)
    assert len(json.loads((f.claims/'claims.json').read_bytes())['claims'])==4


def test_unrelated_owner_is_not_captured_and_original_binding_cannot_change(tmp_path):
    f=fixture(tmp_path);a=f.load();other=binding(subject='m4-synthetic-demo-cccccccccccc')
    assert a.registrations(other)is f.registrations and not a.selects(other)
    b=binding();f.database.original(b,'question-0','zh');a.registrations(b)
    changed=replace(b,run_id='different-run');f.database.original(changed,'question-0','zh')
    with pytest.raises(BudgetUnknown,match='binding changed'):a.registrations(changed)
    assert not a.selects(changed)


def test_directory_policy_and_expiry_changes_fail_closed(tmp_path):
    f=fixture(tmp_path);a=f.load();b=binding();f.database.original(b,'question-0','zh')
    f.clock[0]=NOW+3600
    with pytest.raises(BudgetUnknown,match='not active'):a.registrations(b)
    f.clock[0]=NOW
    f.claims.chmod(0o755)
    with pytest.raises(BudgetUnknown,match='directory authority'):a.registrations(b)
    f.claims.chmod(0o700)
    f.path.write_bytes(f.path.read_bytes()+b'\n')
    with pytest.raises(BudgetUnknown,match='policy changed'):a.registrations(b)


def test_wrong_allocation_and_missing_claims_do_not_initialize_or_reset(tmp_path):
    f=fixture(tmp_path)
    with sqlite3.connect(f.budget)as db:db.execute("UPDATE scope_sublimit SET line='A'")
    with pytest.raises(ValueError,match='original C allocation'):f.load()
    with sqlite3.connect(f.budget)as db:db.execute("UPDATE scope_sublimit SET line='C'")
    (f.claims/'claims.json').unlink()
    with pytest.raises(FileNotFoundError):f.load()
    assert not (f.claims/'claims.json').exists()


def test_producer_return_requires_actual_ack_and_never_claims_cost_completion(tmp_path):
    f=fixture(tmp_path);a=f.load();b=binding();f.database.original(b,'question-0','zh');a.registrations(b)
    outcome=SimpleNamespace(message_id=b.message_id,run_id=b.run_id,status='completed')
    key=(b.scope,b.run_id,b.message_id)
    f.database.statuses[key]=('completed',3,False)
    with pytest.raises(BudgetUnknown,match='not acknowledged'):a.completed([outcome])
    assert json.loads((f.claims/'claims.json').read_bytes())['claims'][0]['producer_return'] is None
    f.database.statuses[key]=('completed',3,True);a.completed([outcome])
    prior=(f.claims/'claims.json').read_bytes()
    assert json.loads(prior)['claims'][0]['producer_return']['cost_coverage']=='NOT_ASSERTED'
    f.load().completed([outcome])
    assert (f.claims/'claims.json').read_bytes()==prior
    f.clock[0]=NOW+3600
    a.completed([]) # expired capture must not disturb unrelated idle worker loops


def test_changed_evidence_and_replaced_directories_refuse_capture(tmp_path):
    f=fixture(tmp_path);a=f.load();b=binding();f.database.original(b,'question-0','zh')
    raw=f.evidence_policy.read_bytes();f.evidence_policy.write_bytes(raw+b'\n')
    with pytest.raises(BudgetUnknown,match='evidence policy changed'):a.registrations(b)
    f.evidence_policy.write_bytes(raw)
    f.claims.rename(f.claims.with_name('old-claims'));f.claims.mkdir(mode=0o700)
    with pytest.raises(BudgetUnknown,match='directory replaced'):a.registrations(b)


def test_crash_pending_file_is_not_overwritten_or_replayed(tmp_path):
    f=fixture(tmp_path);a=f.load();b=binding();f.database.original(b,'question-0','zh')
    pending=f.claims/'claims.pending';pending.write_bytes(b'uncertain original write');pending.chmod(0o600)
    before=(f.claims/'claims.json').read_bytes()
    with pytest.raises(BudgetUnknown,match='uncertain prior claim write'):a.registrations(b)
    assert (f.claims/'claims.json').read_bytes()==before and pending.read_bytes()==b'uncertain original write'


def test_seed_continuation_is_bound_to_the_prior_original_and_not_a_new_chat(tmp_path):
    f=fixture(tmp_path);base=f.policy['slots'][0]
    first=dict(base,slot_id='seed-zh-1',nonce=sha256(b'seed-first').hexdigest()[:32],setup=True,text_sha256=sha256(b'seed-first').hexdigest())
    second=dict(base,slot_id='seed-zh-2',nonce=sha256(b'seed-next').hexdigest()[:32],setup=True,text_sha256=sha256(b'seed-next').hexdigest(),
                conversation_mode='continuation',prior_slot_id='seed-zh-1')
    f.policy['slots']=[first,second,*f.policy['slots']]
    write(f.path,f.policy)
    write(f.claims/'claims.json',dict(version=CLAIMS,policy_sha256=sha256(f.path.read_bytes()).hexdigest(),state='ACTIVE',claims=[]))
    a=f.load();b=binding();f.database.original(b,'seed-first','zh');a.registrations(b)
    wrong=binding(1);f.database.original(wrong,'seed-next','zh')
    with pytest.raises(BudgetUnknown,match='seed continuation'):a.registrations(wrong)
    actual=replace(b,message_id='actual-seed-next',run_id='seed-run-next',message_sequence=2)
    f.database.original(actual,'seed-next','zh');a.registrations(actual)
    rows=json.loads((f.claims/'claims.json').read_bytes())['claims']
    assert [x['slot_id']for x in rows]==['seed-zh-1','seed-zh-2']
    assert all(a.selects(x)for x in (b,actual))


def test_missing_lock_is_not_created_automatically(tmp_path):
    f=fixture(tmp_path);(f.claims/'claims.lock').unlink()
    with pytest.raises(FileNotFoundError):f.load()
    assert not (f.claims/'claims.lock').exists()


def test_stop_new_is_persistent_and_does_not_erase_existing_capture_authority(tmp_path):
    f=fixture(tmp_path);a=f.load();b=binding();f.database.original(b,'question-0','zh');a.registrations(b)
    before=json.loads(a.claims_snapshot())['claims'];a.stop_new()
    again=f.load();assert json.loads(again.claims_snapshot())['state']=='STOP_NEW'
    assert json.loads(again.stop_new())['claims']==before and again.selects(b)
    new=binding(1);f.database.original(new,'question-1','zh')
    with pytest.raises(BudgetUnknown,match='stopped'):again.registrations(new)
    assert json.loads(again.claims_snapshot())['claims']==before
