"""Worker selection/capture mechanics; controlled source/AUTH, no live calls."""
from types import SimpleNamespace

import pytest

from cj_api.runtime_run_requests import RunRequests,REFLECTION_MESSAGE
from cj_run.core import Binding
from cj_usage.metered_exit import BudgetUnknown
from runtime_adapter.contract import encode,Unavailable
from runtime_adapter.profiles import C0


@pytest.fixture
def routing():
    mid='runtime-'+'a'*64
    bound=Binding('original-owner','chat','generation',mid,'run',1)
    state={'request':dict(step_id=mid,kind='reflection',candidate=C0,payload={'components':['prompt.answer_style']}),
        'allowed':True,'native_reads':0,'text':REFLECTION_MESSAGE}
    def read(*args,**kwargs):
        if not state['allowed']:raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE')
        return encode(state['request'])
    claims=SimpleNamespace(binding=SimpleNamespace(scope=bound.scope),read=read,query=lambda context,mid:context.query_message(mid))
    context=SimpleNamespace(scope=bound.scope,query_message=lambda mid:SimpleNamespace(
        receipt=SimpleNamespace(run_id=bound.run_id,conversation_id=bound.conversation_id,
            generation=bound.generation,sequence=bound.message_sequence),raw=encode({'text':state['text']})))
    def native(token,project):state['native_reads']+=1;return project(context)
    tools=SimpleNamespace(registrations={'original':object()},runtime_registrations=lambda candidate,**kwargs:{'runtime':candidate})
    resolver=RunRequests(claims,SimpleNamespace(with_history_context=native),lambda:'fixture-token',tools)
    return resolver,bound,state,tools


def test_native_identity_and_message_binding_precede_runtime_selection(routing):
    resolver,bound,state,tools=routing
    assert resolver.registrations(bound)=={'runtime':C0}
    assert resolver.reflection(bound)==state['request']['payload']
    assert resolver.selects(bound)
    assert state['native_reads']==2
    # Capture does not try to reacquire MESSAGE locks inside a provider step.
    assert resolver.selects(bound) and state['native_reads']==2


def test_late_revocation_or_changed_canonical_bytes_stops_capture(routing):
    resolver,bound,state,tools=routing;resolver.registrations(bound)
    state['allowed']=False
    with pytest.raises(BudgetUnknown,match='capture authority'):resolver.selects(bound)
    state['allowed']=True;state['request']['candidate']={**C0,'prompt.answer_style':'changed canonical source'}
    with pytest.raises(BudgetUnknown,match='request changed'):resolver.selects(bound)


def test_failed_source_is_closed_registry_then_unknown_before_memory_or_provider(routing):
    resolver,bound,state,tools=routing;state['text']='different original message'
    assert resolver.registrations(bound)=={} and not resolver.selects(bound)
    with pytest.raises(BudgetUnknown,match='query only'):resolver.reflection(bound)


def test_ordinary_original_message_keeps_its_registry_and_is_not_captured(routing):
    resolver,bound,state,tools=routing
    ordinary=Binding(bound.scope,bound.conversation_id,bound.generation,'ordinary-id',bound.run_id,1)
    assert resolver.registrations(ordinary) is tools.registrations
    assert resolver.reflection(ordinary) is None and not resolver.selects(ordinary)
    assert state['native_reads']==0
