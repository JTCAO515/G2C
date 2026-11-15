"""Real local journal, controlled native originals; no live eligibility."""
from datetime import datetime,timezone
from hashlib import sha256
from types import SimpleNamespace as NS
import json
import pytest
from cj_api.runtime_episode_cost import EpisodeCostInventory
from cj_usage.authorization_budget import AuthorizationBudget,CNY_SCALE
from runtime_adapter import Binding,Unavailable
from runtime_adapter.contract import encode
from eval.lio_simulated_user.runner import HostUnavailable


@pytest.fixture
def episode(tmp_path,monkeypatch):
 monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER','codex-mac')
 budget=AuthorizationBudget(tmp_path/'fees',clock=lambda:datetime(2026,11,14,tzinfo=timezone.utc))
 token='episode-local-token';binding=Binding('scope',sha256(token.encode()).hexdigest(),budget.ledger_id,budget.producer);pins=NS(key='a'*64)
 dut=NS(originals=[]);actor=NS(originals=[],clock=lambda:70)
 rows={};tails={};backgrounds={};state={'allowed':True,'missing_fee':set()}
 def guard(**kw):
  assert kw['binding']==binding and kw['pins_sha256']==pins.key and kw['purpose']=='query'and kw['read_only']
  if not state['allowed']:raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE')
 authority=NS(require=guard)
 def fee(credential,mid,op):
  attempt=next(r['attempt_id']for r in rows[mid]if r['operation_id']==op)
  if attempt in state['missing_fee']:raise Unavailable('ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE')
  with budget.connect()as db:r=db.execute('SELECT kind,input_sha,state,receipt FROM attempt WHERE id=?',(attempt,)).fetchone()
  return encode(dict(attempt_id=attempt,ledger_id=budget.ledger_id,kind=r[0],actual_wire_input_sha256=r[1],state=r[2],receipt_utf8=r[3]))
 def inventory(credential,mid):return encode(dict(message_id=mid,run_id='r-'+mid,status='completed',operations=rows[mid]))
 originals=NS(budget=budget,inventory=inventory,fee=fee,meter=lambda *a:encode(dict(state='settled',receipt={'original':True})),cost_tail=lambda credential,mid:encode(dict(message_id=mid,run_id='r-'+mid,**tails[mid])))
 def bg_read(credential,jid,attempt):
  if (jid,attempt)not in backgrounds:raise Unavailable('EPISODE_BACKGROUND_ORIGINAL_MISSING')
  return encode(backgrounds[jid,attempt])
 accounting=EpisodeCostInventory(dut,actor,originals,originals,NS(read=bg_read),authority,binding,pins,lambda:token,deadline=100,host_unavailable=HostUnavailable)
 def charge(attempt,*,intent=False):
  budget.begin(attempt,'model',attempt.encode())
  if not intent:budget.finish(attempt,dict(model_id='qwen3.8-flash',region='cn-beijing',endpoint='https://dashscope.aliyuncs.com/compatible-mode/v1',receipt_sha256=sha256(attempt.encode()).hexdigest(),usage=dict(prompt_tokens=10,completion_tokens=2,total_tokens=12)))
 def add(mid,role,attempt):
  charge(attempt);rows[mid]=[dict(operation_id='op-'+attempt,attempt_id=attempt,registration_id='model.answer',kind='model')]
  if role=='dut':
   dut.originals.append(dict(step_id=mid));tails[mid]=dict(delivery_acknowledged=True,associated_history_jobs=[])
  else:actor.originals.append(NS(argument=NS(binding=NS(message_id=mid))))
 def background(*,intent=False):
  attempt='background-fee';charge(attempt,intent=intent)
  with budget.connect()as db:r=db.execute('SELECT kind,input_sha,state,receipt FROM attempt WHERE id=?',(attempt,)).fetchone()
  ref=dict(job_id='job',attempt_id='job-attempt',state='unknown'if intent else'completed')
  for tail in tails.values():tail['associated_history_jobs']=[ref]
  backgrounds['job','job-attempt']=dict(original=dict(meter_attempt_id=attempt,meter_operation_id='bg-op',registration_id='model.background',state='unknown'if intent else'completed'),fee=dict(attempt_id=attempt,ledger_id=budget.ledger_id,kind=r[0],actual_wire_input_sha256=r[1],state=r[2],receipt_utf8=r[3]),meter=dict(state='unknown'if intent else'settled',receipt=None if intent else{'original':True}))
 return NS(accounting=accounting,add=add,background=background,charge=charge,budget=budget,dut=dut,actor=actor,rows=rows,tails=tails,backgrounds=backgrounds,state=state)


def test_all_three_roles_original_costs_and_duplicate_job_associations_count_once(episode):
 e=episode;e.add('d1','dut','fee1');e.add('d2','dut','fee2');e.add('a1','actor','fee3');e.background()
 before=e.budget.inspect();r=e.accounting.collect(deadline=100)
 assert r['coverage_status']=='COMPLETE'and r['accounting_status']=='SETTLED'
 assert len(r['attempts'])==4 and {x['role']for x in r['attempts']}=={'dut','actor','background'}
 assert r['cost']==dict(conservative_cny='0.0000536',token_estimate_cny='0.0000536',actual_paid_cny=None)
 assert r['episode_before']['count']==0 and r['episode_after']['count']==4
 assert e.accounting()==r['cost']and e.budget.inspect()==before


def test_intent_background_retains_hold_and_never_invents_settlement(episode):
 e=episode;e.add('d1','dut','fee1');e.add('a1','actor','fee2');e.background(intent=True)
 r=e.accounting.collect(deadline=100)
 assert r['accounting_status']==r['coverage_status']=='UNKNOWN'
 assert r['cost']==dict(conservative_cny=None,token_estimate_cny=None,actual_paid_cny=None)
 assert r['known_conservative_cny_1e7']==CNY_SCALE+268
 assert next(x for x in r['attempts']if x['role']=='background')['financial_state']=='INTENT'


def test_missing_associated_job_does_not_become_an_empty_free_background(episode):
 e=episode;e.add('d1','dut','fee1');e.background();e.backgrounds.clear()
 r=e.accounting.collect(deadline=100)
 assert r['coverage_status']=='UNKNOWN'and r['cost']['conservative_cny']is None
 assert {x['field']for x in r['missing']}=={'background_original','episode_journal_delta_coverage'}


def test_missing_one_fee_keeps_other_originals_and_unknown_amount(episode):
 e=episode;e.add('d1','dut','fee1');e.add('a1','actor','fee2');e.state['missing_fee'].add('fee1')
 r=e.accounting.collect(deadline=100)
 assert len(r['attempts'])==2 and r['coverage_status']=='UNKNOWN'
 assert r['known_estimated_cny_1e7']==134 and r['cost']['conservative_cny']is None


def test_unrelated_journal_delta_and_lost_ack_keep_coverage_unknown(episode):
 e=episode;e.add('d1','dut','fee1');e.charge('unrelated');e.tails['d1']['delivery_acknowledged']=False
 r=e.accounting.collect(deadline=100)
 assert {x['field']for x in r['missing']}=={'delivery_acknowledgement','episode_journal_delta_coverage'}
 assert r['cost']['conservative_cny']is None


def test_duplicate_native_attempt_never_double_counts_and_auth_withholds(episode):
 e=episode;e.add('d1','dut','fee1');e.actor.originals.append(NS(argument=NS(binding=NS(message_id='d1'))))
 with pytest.raises(Unavailable,match='DUPLICATE'):e.accounting.collect(deadline=100)
 e.state['allowed']=False
 with pytest.raises(HostUnavailable):e.accounting()
