"""Worker source-holder ordering controls; no native Trip4/provider claim."""
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from cj_needs.domain import Denied as NeedsDenied
from test_worker_cancel import fixture,CancelsDuringAnswer


def publication(version,*,withdraw=False):
 worker,runs,binding,_,_=fixture(CancelsDuringAnswer)
 runs.accept(binding)
 worker._event(binding,runs.snapshot(binding),'started')
 held=[];checks=[]
 @contextmanager
 def hold(name,value):
  held.append(name)
  try:yield value
  finally:assert held.pop()==name
 def message_check(actual):
  assert actual==binding and held[0]=='M';checks.append('M')
 def memory_check():
  assert held[:2]==['M','Mem'];checks.append('Mem')
 def needs_check():
  assert held==['M','Mem','N'];checks.append('N')
  if withdraw:raise NeedsDenied('withdrawn original source')
 worker.message_context=SimpleNamespace(hold_for_effect=lambda actual,source_lock:hold('M',SimpleNamespace(check=message_check)))
 worker.memory_run=SimpleNamespace(hold=lambda actual:hold('Mem',memory_check))
 worker.drafts=SimpleNamespace(content_version=version,hold_for_publication=lambda actual:hold('N',needs_check))
 return worker,runs,binding,held,checks


@pytest.mark.parametrize('version',['structured.2','structured.3','structured.4'])
def test_publication_holds_original_sources_through_trip_and_deadline(version):
 worker,runs,binding,held,checks=publication(version)
 def trip_check():
  assert held==['M','Mem','N'];checks.append('Trip')
 def deadline():
  assert held==['M','Mem','N'];checks.append('deadline')
 def publish():
  assert held==['M','Mem','N']
  worker._publication_check(check_trip=trip_check)
  return 'candidate'
 state,value=worker._step(binding,publish,lambda value:'trip_proposal:original',draft=True,publication_deadline=deadline)
 assert value=='candidate'and state.effects==('trip_proposal:original',)and not held
 assert checks[-5:]==['M','Mem','N','Trip','deadline']


@pytest.mark.parametrize('version',['structured.2','structured.3','structured.4'])
def test_withdrawn_source_never_invokes_publisher_or_records_effect(version):
 worker,runs,binding,held,checks=publication(version,withdraw=True)
 invoked=[]
 with pytest.raises(NeedsDenied):worker._step(binding,lambda:invoked.append(True),lambda value:'trip_proposal:forbidden',draft=True)
 assert not invoked and not held and runs.snapshot(binding).effects==()
