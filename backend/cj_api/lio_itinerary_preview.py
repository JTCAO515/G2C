"""The optional structured plan behind a visible read-only Lio discussion."""
from hashlib import sha256
import json

from cj_message.lio_context import display_answer
from cj_needs.domain import InvalidInput, decode


VERSION = 'LIO-itinerary-preview.1'
_EFFECT = 'lio_itinerary_preview.1:'
_VERBS = {
    'visit': ('参观', 'Visit'), 'explore': ('游览', 'Explore'),
    'walk': ('漫步', 'Walk around'), 'eat': ('去用餐', 'Eat at'),
    'shop': ('去逛', 'Shop at'), 'relax': ('去休息', 'Relax at'),
}
_PERIODS = {
    None: ('', ''), 'morning': ('上午', 'Morning: '),
    'afternoon': ('下午', 'Afternoon: '), 'evening': ('晚上', 'Evening: '),
}
FORMAT = (
    ' For a complete day-by-day plan, use the following response format: one JSON object with answer, days and follow_up. '
    'Answer is the complete standalone plain-text reply in case the structured plan is unavailable. '
    'Days is an ordered array with one object per requested day: day_index and activities. '
    'Each activity has exactly place_name (full proper name in the answer language), '
    'verb (visit, explore, walk, eat, shop or relax), and period (morning, afternoon, evening or null). '
    'Only include suggested visits you would actually show to the traveler. '
    'Follow_up is one useful adjustment question in the answer language. '
    'If you cannot provide the complete structured plan, return only answer.'
)


def _short_line(text, limit):
    return (type(text) is str and text == text.strip() and text.isprintable()
            and 0 < len(text.encode('utf-8')) <= limit)


def _days(value, count):
    if type(value) is not list or not 1 <= count <= 366 or len(value) != count:
        return None
    for index, day in enumerate(value, 1):
        if (type(day) is not dict or day.keys() != {'day_index', 'activities'}
                or type(day['day_index']) is not int or day['day_index'] != index
                or type(day['activities']) is not list or not 1 <= len(day['activities']) <= 8):
            return None
        for activity in day['activities']:
            if (type(activity) is not dict or activity.keys() != {'place_name', 'verb', 'period'}
                    or not _short_line(activity['place_name'], 240)
                    or type(activity['verb']) is not str or activity['verb'] not in _VERBS
                    or activity['period'] is not None and (type(activity['period']) is not str
                                                           or activity['period'] not in _PERIODS)):
                return None
    return value


def render(days, count, follow_up, locale):
    days = _days(days, count)
    if days is None:
        return None
    zh = locale == 'zh'
    lang = 0 if zh else 1
    lines = []
    for day in days:
        activities = []
        for activity in day['activities']:
            verb, name = _VERBS[activity['verb']][lang], activity['place_name']
            if zh and activity['verb'] in ('eat', 'relax'):
                action = '去' + name + verb[1:]
            else:
                action = verb + ('' if zh else ' ') + name
            activities.append(_PERIODS[activity['period']][lang] + action)
        index = day['day_index']
        lines.append(f'第{index}天：' + '，'.join(activities) + '。' if zh else
                     f'Day {index}: ' + '. '.join(activities) + '.')
    if _short_line(follow_up, 280) and follow_up.endswith(('?', '？')):
        lines.append(follow_up)
    answer = '\n'.join(lines)
    if display_answer(answer, locale) != answer:
        return None
    return answer, days


def _content_digest(text, days):
    raw = json.dumps((text, days), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return sha256(raw.encode()).hexdigest()


def effect(text, days):
    return _EFFECT + json.dumps(dict(content_sha256=_content_digest(text, days), days=days),
                                ensure_ascii=False, separators=(',', ':'))


def read_preview(state, locale):
    if (state is None or state.status != 'completed' or state.draft_outcome is not None
            or state.trip_proposal_published or not state.text.strip()
            or display_answer(state.text, locale) != state.text):
        return None
    records = [entry.removeprefix(_EFFECT) for entry in state.effects if entry.startswith(_EFFECT)]
    if len(records) != 1:
        return None
    try:
        record = decode(records[0].encode())
        if (type(record) is not dict or record.keys() != {'content_sha256', 'days'}
                or type(record['days']) is not list
                or record['content_sha256'] != _content_digest(state.text, record['days'])):
            return None
        days = _days(record['days'], len(record['days']))
    except (InvalidInput, UnicodeError):
        return None
    if days is None:
        return None
    return dict(destination=None, days=[dict(day_index=day['day_index'], activities=[
        dict(place_name=activity['place_name'], cancelled=False) for activity in day['activities']]) for day in days])
