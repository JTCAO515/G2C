import pytest

from cj_api.lio_memory_preferences import supported_preference
from cj_memory_jobs.extraction import Entry, Evidence


def entry(slot, text, *, quote=None, kind='preference'):
    return Entry('self', slot, kind, text, 'long_term', 'date unknown',
                 (Evidence('original', quote if quote is not None else text),))


@pytest.mark.parametrize('slot,text', [
    ('travel.pace', 'I always prefer a slower travel pace.'),
    ('travel.pace', '我平时喜欢慢节奏旅行。'),
    ('travel.budget', 'I prefer a budget of around 400 yuan per day.'),
    ('travel.budget', '旅行预算通常是每天400元。'),
    ('lodging.style', 'I prefer staying in central hotels.'),
    ('lodging.style', '我通常喜欢住精品酒店。'),
    ('travel.interests', 'I enjoy museums and architecture.'),
    ('travel.interests', '我喜欢博物馆和历史。'),
    ('diet.taste', 'I prefer Cantonese cuisine.'),
    ('diet.spicy', '我不吃辣。'),
    ('quiet.entrance', 'I prefer using quieter entrances at attractions.'),
])
def test_common_explicit_preference_forms(slot, text):
    assert supported_preference(entry(slot, text))


@pytest.mark.parametrize('candidate', [
    entry('health.condition', 'I have asthma.', kind='fact'),
    entry('religion', 'I prefer museums.'),
    entry('travel.interests', 'I attend services because I am Catholic.'),
    entry('travel.pace', 'I prefer a slow pace because I have asthma.'),
    entry('diet.spicy', '我不吃辣，因为我有胃病。'),
    entry('travel.interests', 'I prefer museums.', quote='I am Catholic.'),
    entry('travel.pace', 'I have asthma.', quote='I prefer a slow pace.'),
    entry('travel.budget', 'My salary is 500 yuan per day.'),
])
def test_sensitive_or_mislabeled_content_does_not_become_a_tag(candidate):
    assert not supported_preference(candidate)
