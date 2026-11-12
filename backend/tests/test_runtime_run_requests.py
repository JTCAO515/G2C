"""Worker selection/capture mechanics; controlled source/AUTH, no live calls."""
from types import SimpleNamespace
from hashlib import sha256

import pytest

from cj_api.runtime_run_requests import RunRequests,REFLECTION_MESSAGE
from cj_api.runtime_message_input import lio_input
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
    claims=SimpleNamespace(binding=SimpleNamespace(scope=bound.scope),read=read,query=lambda context,mid:context.query_message(mid),history_profile='message.1')
    context=SimpleNamespace(scope=bound.scope,query_message=lambda mid:SimpleNamespace(
        receipt=SimpleNamespace(run_id=bound.run_id,conversation_id=bound.conversation_id,
            generation=bound.generation,sequence=bound.message_sequence),raw=encode({'text':state['text']})))
    state['native_digest']=sha256(lio_input(bound.scope,state['request'])).hexdigest()
    context.query_lio_receipt=lambda mid:SimpleNamespace(input_sha256=state['native_digest'])
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


def test_typed_lio_receipt_requires_exact_outer_request_not_only_same_text(routing):
    resolver,bound,state,tools=routing
    resolver.claims.history_profile='lio.2'
    assert resolver.registrations(bound)=={'runtime':C0}
    # A same-owner client races the claim with the same MID/text but a different
    # locale/conversation selector. Its persisted outer digest is a different
    # native operation, even though the inner displayed text still matches.
    state['native_digest']=sha256(encode(dict(version='LIO-message.2',message_id=bound.message_id,
        text=REFLECTION_MESSAGE,locale='zh',conversation_id='lio-dialogue-'+'f'*32))).hexdigest()
    assert resolver.registrations(bound)=={}
    with pytest.raises(BudgetUnknown,match='query only'):resolver.reflection(bound)
