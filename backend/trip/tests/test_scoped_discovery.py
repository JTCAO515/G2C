import pytest
from cj_trip.scoped_discovery import DiscoveryQuery


def test_original_utf8_message_and_run_ids_are_preserved_without_prefix_guessing():
    q=DiscoveryQuery.parse([('run_id','original-run'),('message_id','消息 / + & %')])
    assert (q.message_id,q.run_id)==('消息 / + & %','original-run')


@pytest.mark.parametrize('pairs',[
    [('message_id','m')], [('message_id','m'),('run_id','r'),('owner','other')],
    [('message_id','m'),('run_id','r'),('run_id','new')],
    [('message_id',''),('run_id','r')], [('message_id','m\0'),('run_id','r')],
    [('message_id','字'*700),('run_id','r')], [('message_id','m'),('run_id','r'*2049)],
])
def test_unbound_missing_duplicate_oversized_or_owner_queries_refuse(pairs):
    with pytest.raises(ValueError):DiscoveryQuery.parse(pairs)
