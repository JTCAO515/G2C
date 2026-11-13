"""WP1 density in the new opt-in shape; old source and publication guards remain."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from types import SimpleNamespace

from jsonschema import Draft202012Validator, ValidationError
import pytest

from cj_draft.grouped_plan import (GENERATION_PROFILES, LioGroupedPlanPublisher, grouped_input,
                                  response_format, response_format_sha256)
from cj_draft.rich_first import LioRichFirstCalendarPublisher, LioRichFirstPlanPublisher, normalize
from cj_draft.rich_schema import Pace, PROFILES, SIGHT_COUNTS
from cj_trip.domain import Trip, packed
from grouped_draft_fixtures import START, source, reply


def publisher(days, language, ordinal, pace, *, fixed=False):
    snapshot, revisions = source(days, language, ordinal=ordinal, with_fixed=fixed)
    capture = SimpleNamespace(binding='original', records=lambda: (snapshot, revisions),
        basis=SimpleNamespace(day_count=days, start_date=None,
                              day_indices=lambda: {'hotel': (1, 1)} if fixed else {}))
    cls = LioRichFirstCalendarPublisher if ordinal else LioRichFirstPlanPublisher
    host = cls.__new__(cls)
    host.pace = pace
    host.source = SimpleNamespace(contexts={'original': None})
    host.draft_guidance = ''
    return host, capture


def rich_reply(days, language, ordinal, pace):
    sights = ('故宫', '景山公园', '天坛', '北海公园') if language == 'zh' else (
        'Forbidden City 故宫', 'Jingshan Park 景山公园', 'Temple of Heaven 天坛', 'Beihai Park 北海公园')
    meals = ('午餐：京味斋', '晚餐：四季民福') if language == 'zh' else (
        'Lunch at Jingweizhai 京味斋', 'Dinner at Siji Minfu 四季民福')
    clocks = [('09:00', '10:00'), ('10:30', '11:30'), ('14:00', '15:00'), ('15:30', '16:30')]
    groups = []
    for n in range(days):
        rows = [[f's{n}-{i}', name, *clocks[i], ['self']]
                for i, name in enumerate(sights[:SIGHT_COUNTS[pace]])]
        food = [[f'm{n}-{i}', name, *clock, ['self']]
                for i, (name, clock) in enumerate(zip(meals, [('12:00', '13:00'), ('18:00', '19:00')]))]
        groups.append([n + 1 if ordinal else (START+timedelta(days=n)).isoformat(), rows, food])
    return dict(version=PROFILES[ordinal, pace], title='北京行程' if language == 'zh' else 'Beijing 北京', days=groups)


@pytest.mark.parametrize('days', [4, 5])
@pytest.mark.parametrize('language', ['zh', 'en'])
@pytest.mark.parametrize('ordinal', [False, True])
@pytest.mark.parametrize('pace', list(Pace))
def test_full_four_five_days_preserve_names_participants_and_canonical_versions(days, language, ordinal, pace):
    host, capture = publisher(days, language, ordinal, pace)
    value = rich_reply(days, language, ordinal, pace)
    Draft202012Validator(response_format(value['version'])['json_schema']['schema']).validate(value)
    messages = host.model_messages('original', 'plan', capture, [])
    packet = grouped_input(host, capture, messages, object())
    assert packet.profile == value['version'] and value['version'] in packet.system
    assert response_format_sha256(packet.profile) != response_format_sha256(reply(days, language, ordinal=ordinal)['version'])
    content, candidate, _ = host.build_plan(packed(value), capture)
    document = json.loads(content)
    count = SIGHT_COUNTS[pace] + 2
    assert document['content_version'] == ('structured.3' if ordinal else 'structured.2')
    assert len(document['items']) == days * count
    expected = [row for _, sights, meals in value['days'] for row in sorted(sights+meals, key=lambda r: r[2])]
    assert [item['text'] for item in document['items']] == [row[1] for row in expected]
    assert [item['id'] for item in document['items']] == [row[0] for row in expected]
    assert all('kind' not in item and 'place' not in item and item['verification'] == 'pending'
               and item['evidence'] == [] and item['source_refs'] == [] for item in document['items'])
    assert all(item['applies_to'] == ['self'] for item in json.loads(candidate.content)['fixed_items'])
    # Existing saved rows have no kind: subsequent deltas use the original
    # profile and retain every saved row, without claiming total G6 density.
    host.source.contexts['original'] = SimpleNamespace(trip=Trip('trip', 1, content), proposed=candidate.content)
    host.model_messages('original', 'add', capture, [])
    delta = reply(days, language, ordinal=ordinal, delta=True)
    assert grouped_input(host, capture, [], object()).profile == delta['version']
    after, _, _ = host.build_plan(packed(delta), capture)
    assert json.loads(after)['items'][:len(document['items'])] == document['items']


@pytest.mark.parametrize('ordinal', [False, True])
def test_fixed_source_uses_old_profile_and_never_guesses_or_discards_a_kind(ordinal):
    host, capture = publisher(4, 'en', ordinal, Pace.MODERATE, fixed=True)
    old = reply(4, 'en', ordinal=ordinal)
    host.model_messages('original', 'plan', capture, [])
    assert grouped_input(host, capture, [], object()).profile == old['version']
    content, _, _ = host.build_plan(packed(old), capture)
    assert json.loads(content)['items'][0]['id'] == 'hotel'
    assert json.loads(content)['items'][0]['fixed'] == dict(state='known', value=True)
    with pytest.raises(ValueError):
        host.build_plan(packed(rich_reply(4, 'en', ordinal, Pace.MODERATE)), capture)


@pytest.mark.parametrize('change', [
    lambda v: v.update(extra=True),
    lambda v: v.update(version=PROFILES[False, Pace.PACKED]),
    lambda v: v['days'][0][1].pop(),
    lambda v: v['days'][0][2].pop(),
    lambda v: v['days'].pop(),
    lambda v: v['days'].append(deepcopy(v['days'][0])),
    lambda v: v['days'][0].append([]),
    lambda v: v['days'][0][1][0].append(dict(fixed=False)),
    lambda v: v['days'][0][1][0].__setitem__(2, 9),
    lambda v: v['days'][0][1][0].__setitem__(2, '25:00'),
    lambda v: v['days'][0][1][0].__setitem__(4, ['companion:forged']),
    lambda v: v['days'][0][2][0].__setitem__(0, v['days'][0][1][0][0]),
    lambda v: v['days'][0].__setitem__(0, '2027-01-01'),
])
def test_wrong_profile_counts_coverage_authority_and_clock_are_not_repaired(change):
    host, capture = publisher(4, 'zh', False, Pace.MODERATE)
    value = rich_reply(4, 'zh', False, Pace.MODERATE)
    change(value)
    with pytest.raises(ValueError):
        host.build_plan(packed(value), capture)


def test_incomplete_duplicate_json_and_prompt_selected_profiles_are_refused():
    host, capture = publisher(4, 'en', False, Pace.MODERATE)
    raw = packed(rich_reply(4, 'en', False, Pace.MODERATE))
    for malformed in (raw[:-1], b'{"version":1,"version":2}'):
        with pytest.raises(ValueError): normalize(malformed, capture, ordinal=False, pace=Pace.MODERATE)
    for pace in ('moderate', None):
        with pytest.raises(ValueError, match='typed Pace'): LioRichFirstPlanPublisher(pace=pace)
    host.model_messages('original', PROFILES[False, Pace.PACKED], capture, [])
    assert grouped_input(host, capture, [], object()).profile == PROFILES[False, Pace.MODERATE]
    bad = rich_reply(4, 'en', False, Pace.MODERATE)
    bad['days'][0][2].append(deepcopy(bad['days'][0][2][0]))
    with pytest.raises(ValidationError):
        Draft202012Validator(response_format(bad['version'])['json_schema']['schema']).validate(bad)


def test_new_and_old_first_decoders_are_exclusive_and_global_item_bound_remains():
    host, capture = publisher(4, 'en', False, Pace.MODERATE)
    with pytest.raises(ValueError): host.build_plan(packed(reply(4, 'en')), capture)
    legacy = LioGroupedPlanPublisher.__new__(LioGroupedPlanPublisher)
    legacy.source = host.source
    with pytest.raises(ValueError):
        legacy.build_plan(packed(rich_reply(4, 'en', False, Pace.MODERATE)), capture)
    host, capture = publisher(11, 'en', False, Pace.PACKED)
    with pytest.raises(ValueError): host.build_plan(packed(rich_reply(11, 'en', False, Pace.PACKED)), capture)


def test_four_frozen_generation_schemas_keep_their_original_bytes():
    expected = (
        'ebe9c03ff327c01fc86b97457f8536d6a99004dbda38d49bc8dd40d51b963ef9',
        'd23d6dcb58ef8c1d53023f6468c58cbf80aee905d23b7477d585416d3f102c01',
        'cea0aa19587ab4b383653051eb88b41bee7c16475630b921bc70fb06308be3a0',
        '3b9ad0014cd9996d11919ba8e72d3b89dd6f4fd8da089a60faa84c79f83e9cc6')
    assert tuple(sha256(packed(response_format(profile))).hexdigest()
                 for profile in GENERATION_PROFILES[:4]) == expected
