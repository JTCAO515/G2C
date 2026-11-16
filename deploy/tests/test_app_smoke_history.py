"""Read-only old targets cannot become writer/model/Memory capture claims."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import pytest

from cj_api.app_smoke_history import VERSION,targets,require_census,require_original,anchors
from cj_usage.authorization_budget import canonical
from runtime_adapter.contract import Unavailable


def anchor(cid,mid,run):
    return dict(version=VERSION,conversation_id='lio-dialogue-'+cid*32,generation='old-generation',
        messages=[dict(message_id=mid,run_id=run,sequence=1,canonical_sha256=sha256(canonical(dict(text='old'))).hexdigest())])


def plan():
    zh=anchor('a','old-zh','run-zh');second=anchor('b','old-second','run-second');en=anchor('c','old-en','run-en')
    return dict(first_setup=False,old_chats=dict(zh=dict(zh,conversations=[zh,second]),en=en))


def test_declared_local_history_census_stays_separate_from_execution_claims():
    value=plan();selected=targets(value,dict(zh='scope-zh',en='scope-en'))
    assert len(selected)==3 and all(x['origin']=='readonly_history'for x in selected)
    assert all('slot_id'not in x and 'producer_return'not in x for x in selected)
    assert anchors(selected[:2])==value['old_chats']['zh']['conversations']
    state=dict(native_messages=[dict(message_id=x['binding']['message_id'],run_id=x['binding']['run_id'],
        conversation_id=x['binding']['conversation_id'],generation=x['binding']['generation'],
        sequence=x['binding']['message_sequence'],canonical_sha256=x['canonical_sha256'])for x in selected[:2]])
    state['native_messages'].append(dict(conversation_id='server-only-not-in-local-history'))
    require_census(selected[:2],state)
    state['native_messages'].append(dict(state['native_messages'][0],message_id='unqualified-new-message',sequence=2))
    with pytest.raises(Unavailable,match='CENSUS_CHANGED'):require_census(selected[:2],state)


def test_same_owner_original_receipt_and_canonical_bytes_are_required():
    target=targets(plan(),dict(zh='scope-zh',en='scope-en'))[0];b=target['binding'];raw=canonical(dict(text='old'))
    receipt=SimpleNamespace(conversation_id=b['conversation_id'],generation=b['generation'],message_id=b['message_id'],
        run_id=b['run_id'],sequence=b['message_sequence'],input_sha256=sha256(raw).hexdigest())
    original=SimpleNamespace(receipt=receipt,raw=raw)
    assert require_original(SimpleNamespace(scope='scope-zh'),original,target)is original
    for scope,item in [('foreign',original),('scope-zh',SimpleNamespace(receipt=receipt,raw=raw+b' ')),('scope-zh',None)]:
        with pytest.raises(Unavailable):require_original(SimpleNamespace(scope=scope),item,target)


@pytest.mark.parametrize('change',['selected_missing','duplicate','digest','generation','sequence'])
def test_malformed_partial_or_duplicate_history_declarations_refuse(change):
    value=plan();root=value['old_chats']['zh'];item=root['conversations'][0]
    if change=='selected_missing':root['conversations'].pop(0)
    elif change=='duplicate':root['conversations'].append(deepcopy(root['conversations'][0]))
    elif change=='digest':item['messages'][0]['canonical_sha256']='not-a-digest'
    elif change=='generation':item['generation']=''
    else:item['messages'][0]['sequence']=0
    with pytest.raises(Unavailable):targets(value,dict(zh='scope-zh',en='scope-en'))
