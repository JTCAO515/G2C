"""M-3 (#2001): the ids of the memories an answer used, and their titles read as of now (cj_memory.titles)."""
import json
import os
from types import SimpleNamespace
from unittest import mock

import pytest

from cj_memory import titles as t
from cj_memory.domain import Unavailable


def command(item_id, text, source_id=None, slot='travel.pace', kind='preference', raw=b'raw'):
    return SimpleNamespace(item_id=item_id, text=text, source_id=source_id or 's-' + item_id, source_version=1, slot=slot,
                           kind=kind, raw=raw)


def item(item_id, text, status='active', **kw):
    return SimpleNamespace(command=command(item_id, text, **kw), status=status, version=1)


def run(items, selected=None):
    sources = [i.command.source_id for i in (items if selected is None else selected)]
    payload = json.dumps(dict(version='MEMORY-RUN-CONSUME@1', items=[dict(source_id=s) for s in sources])).encode()
    return SimpleNamespace(payload=payload, snapshot=SimpleNamespace(items=tuple(items), epoch=1))


class FakeRepo:
    """Just enough of the memory transaction: items by id, source rows by (source id, version)."""
    def __init__(self, items, sources=None, fail=None):
        self.items = {i.command.item_id: i for i in items}
        self.sources = sources if sources is not None else {(i.command.source_id, 1): (i.command.raw, True, True) for i in items}
        self.fail = fail
        self.opened = 0

    def transaction(self):
        repo = self
        repo.opened += 1

        class Tx:
            scope = 'scope-a'
            cur = SimpleNamespace()

            def __enter__(self_):
                self_.cur = SimpleNamespace(execute=lambda sql, params: setattr(self_, 'key', (params[1], params[2])),
                                            fetchone=lambda: repo.sources.get(self_.key))
                return self_

            def __exit__(self_, *exc):
                return False

            def detail(self_, item_id):
                if repo.fail == item_id:
                    raise Unavailable('boom')
                return repo.items.get(item_id)
        return Tx()


@pytest.fixture(autouse=True)
def switch():
    with mock.patch.dict(os.environ):
        os.environ.pop('CJ_LIO_MEMORY_USED', None)
        yield


ITEMS = [item('mem-1', '我喜欢慢节奏的旅行'), item('mem-2', 'I prefer quiet hotels', slot='lodging.style'), item('mem-3', '我不吃辣', slot='diet.spicy'),
         item('mem-4', '我喜欢博物馆', slot='travel.interests')]


def test_the_switch_is_off_by_default_and_strict():
    assert t.used_effect(run(ITEMS)) is None
    for bad in ('', '1', 'ON'):
        os.environ['CJ_LIO_MEMORY_USED'] = bad
        with pytest.raises(ValueError):
            t.used_enabled()


def test_the_effect_carries_at_most_three_ids_and_the_count_not_titles():
    os.environ['CJ_LIO_MEMORY_USED'] = 'on'
    effect = t.used_effect(run(ITEMS))
    assert effect.startswith('lio_memory_used:')
    body = json.loads(effect.removeprefix('lio_memory_used:'))
    assert body == dict(item_ids=['mem-1', 'mem-2', 'mem-3'], total=4)
    assert '慢节奏' not in effect and 'quiet' not in effect
    assert t.parse_used(effect) == (['mem-1', 'mem-2', 'mem-3'], 4)


def test_only_what_the_payload_carried_counts_and_unknown_sources_are_skipped():
    os.environ['CJ_LIO_MEMORY_USED'] = 'on'
    chosen = run(ITEMS, selected=[ITEMS[1]])
    assert t.used_item_ids(chosen) == (['mem-2'], 1)
    stranger = SimpleNamespace(payload=json.dumps(dict(items=[dict(source_id='nope')])).encode(), snapshot=SimpleNamespace(items=tuple(ITEMS)))
    assert t.used_effect(stranger) is None
    for broken in (None, SimpleNamespace(), SimpleNamespace(payload=b'not json', snapshot=SimpleNamespace(items=())),
                   SimpleNamespace(payload=b'{"items":[{}]}', snapshot=SimpleNamespace(items=()))):
        assert t.used_effect(broken) is None


def test_a_stored_effect_of_any_other_shape_reads_as_nothing():
    good = 'lio_memory_used:' + json.dumps(dict(item_ids=['a'], total=1))
    assert t.parse_used(good) == (['a'], 1)
    for bad in ('lio_memory_used:', 'lio_memory_used:x', 'lio_memory_used:[]', 'lio_memory_used:{}',
                'lio_memory_used:' + json.dumps(dict(item_ids=[], total=0)),
                'lio_memory_used:' + json.dumps(dict(item_ids=['a', 'a'], total=2)),
                'lio_memory_used:' + json.dumps(dict(item_ids=['a', 'b', 'c', 'd'], total=4)),
                'lio_memory_used:' + json.dumps(dict(item_ids=['a'], total=0)),
                'lio_memory_used:' + json.dumps(dict(item_ids=['a'], total=100)),
                'lio_memory_used:' + json.dumps(dict(item_ids=[1], total=1)),
                'lio_memory_used:' + json.dumps(dict(item_ids=['a b'], total=1)),
                'lio_memory_used:' + json.dumps(dict(item_ids=['a'], total=1, extra=1)), None, 5):
        assert t.parse_used(bad) is None, bad


def test_titles_are_the_current_ones_for_active_items_with_a_valid_source():
    repo = FakeRepo(ITEMS)
    found = t.memory_titles(repo, ['mem-1', 'mem-2'])
    assert found == {'mem-1': '慢节奏的旅行', 'mem-2': 'Quiet hotels'}
    assert repo.opened == 1


def test_a_stopped_withdrawn_or_deleted_item_has_no_title():
    items = [item('mem-1', '我喜欢慢节奏的旅行', status='disabled'), item('mem-2', 'I prefer quiet hotels', status='withdrawn'),
             item('mem-4', '我喜欢博物馆')]
    found = t.memory_titles(FakeRepo(items), ['mem-1', 'mem-2', 'mem-3', 'mem-4'])
    assert found == {} or set(found) == {'mem-4'}
    assert set(found) <= {'mem-4'}      # mem-3 does not exist at all


def test_an_item_whose_source_is_gone_expired_or_changed_has_no_title():
    items = [item('mem-1', '我喜欢慢节奏的旅行'), item('mem-2', 'I prefer quiet hotels'), item('mem-4', '我喜欢博物馆')]
    sources = {('s-mem-1', 1): (b'raw', True, True),            # fine
               ('s-mem-2', 1): (b'other bytes', True, True),    # the approved input no longer matches
               ('s-mem-4', 1): (b'raw', False, True)}           # not confirmed
    found = t.memory_titles(FakeRepo(items, sources), ['mem-1', 'mem-2', 'mem-4'])
    assert set(found) == {'mem-1'}
    assert t.memory_titles(FakeRepo(items, {}), ['mem-1']) == {}


def test_at_most_three_ids_are_read_and_odd_ids_are_ignored():
    repo = FakeRepo(ITEMS)
    found = t.memory_titles(repo, ['mem-1', 'mem-2', 'mem-3', 'mem-4', 'mem-1', 5, None])
    assert set(found) <= {'mem-1', 'mem-2', 'mem-3'}
    assert t.memory_titles(repo, []) == {} and t.memory_titles(repo, [5]) == {}


def test_a_failure_on_one_item_leaves_only_that_item_out():
    repo = FakeRepo(ITEMS, fail='mem-2')
    assert set(t.memory_titles(repo, ['mem-1', 'mem-2'])) == {'mem-1'}
