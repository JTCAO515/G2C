"""Code-only WP9 notices from protected observations; no model notice input.

The host supplies eligible original facts from its admitted operation. These
projections neither authorize collection nor establish a Trip write grant.
"""
from dataclasses import dataclass
from datetime import date
from hashlib import sha256

from .domain import identifier, packed
from .rich_calendar import classify, statutory_exception
from .structured import SourceRejected


@dataclass(frozen=True)
class Citation:
    title: str
    url: str | None = None
    observed_at: str | None = None

    def wire(self):
        return dict(title=self.title, url=self.url, observed_at=self.observed_at)


@dataclass(frozen=True)
class Notice:
    type: str
    severity: str
    item_ids: tuple[str, ...]
    text: str
    source: Citation
    priority: int
    key: str

    def wire(self):
        identity = packed([self.type, self.item_ids, self.key])
        return dict(id='notice-' + sha256(identity).hexdigest()[:32], type=self.type,
                    severity=self.severity, item_ids=list(self.item_ids), text=self.text,
                    source=self.source.wire())


def select_notices(*groups):
    """Deterministic stable priority; duplicate facts do not use a second slot."""
    selected = []
    seen = set()
    for notice in sorted((n for group in groups for n in group), key=lambda n: (n.priority, n.key, n.item_ids)):
        wire = notice.wire()
        if wire['id'] not in seen:
            selected.append(wire)
            seen.add(wire['id'])
        if len(selected) == 2:
            break
    return selected


def date_check_notices(checks, *, source, locale):
    """Use the exact #860 code result; UNKNOWN is never rendered as clear."""
    result = []
    for check in checks:
        source.date_check(check)
        if check['state'] == 'clear':
            continue
        conflict = check['state'] == 'conflict'
        zh = {'weather': '天气可能影响这段安排，请查看天气检查并调整户外活动。',
              'day_opening': '开放时间检查发现冲突，请调整对应站点。'}
        en = {'weather': 'Weather may affect this part of the plan; check the weather result and adjust outdoor activities.',
              'day_opening': 'The opening check found a conflict; adjust the affected stop.'}
        if conflict:
            text = (zh if locale == 'zh' else en)[check['kind']]
        else:
            text = ('这段安排的天气尚未确认。' if check['kind'] == 'weather' else '这些站点当天是否开放尚未确认。') if locale == 'zh' else (
                'Weather for this part of the plan is unconfirmed.' if check['kind'] == 'weather' else
                'Opening on the planned day is unconfirmed for these stops.')
        # Evidence refs are identifiers, not necessarily public URLs/timestamps.
        citation = Citation('天气检查' if check['kind'] == 'weather' else '开放时间检查') if locale == 'zh' else Citation(
            'Weather check' if check['kind'] == 'weather' else 'Opening check')
        result.append(Notice(check['kind'], 'warning' if conflict else 'info', tuple(check['item_ids']),
                             text, citation, 0 if conflict else 8, sha256(packed(check)).hexdigest()))
    return tuple(result)


def venue_notices(entry, *, source, reference, item_id, amap_id, visit_date, locale):
    """Bind a validated H entry to the exact captured venue applicability.

    entry is the host's validated visitor-entry.2 original, not a model object.
    Qualified provider/subject mapping and freshness are captured upstream; no
    name/city matching or blanket city rules are introduced here.
    """
    bound = source.observation(reference, 'tip')
    subject = entry['subject']
    if (sha256(packed(entry)).hexdigest() != bound['entry_sha256']
            or entry['id'] != bound['entry_id']
            or entry['checked_on'] != bound['checked_on'] or entry['expires_on'] != bound['expires_on']
            or subject is None or subject['key'] != bound['subject_key']
            or item_id not in bound['item_ids'] or amap_id not in bound['amap_ids']):
        raise SourceRejected('notice.venue', 'exact eligible entry, subject, item and provider identity required')
    if visit_date is not None and type(visit_date) is not date:
        raise ValueError('explicit visit date or undated is required')
    conditions = entry['conditions']
    citation = Citation(subject['name_zh'] if locale == 'zh' else subject['name_en'], entry['source_urls'][0])
    result = []
    closed = conditions['closed_weekdays']
    if visit_date is not None and closed is not None and visit_date.isoweekday() in closed:
        exception = statutory_exception(classify(visit_date)) if conditions['closed_weekdays_public_holiday_exception'] else False
        if exception is not True:
            text = ('这一天是该场馆的常规闭馆日，建议调换。' if locale == 'zh' else
                    'This is a regular closing day for this venue; consider swapping the stop.') if exception is False else (
                    '这一天落在常规闭馆日，但节假日例外是否适用尚待确认。' if locale == 'zh' else
                    'This falls on a regular closing day; whether the public-holiday exception applies is unconfirmed.')
            result.append(Notice('day_opening', 'warning', (item_id,), text, citation, 1,
                                 entry['id'] + ':closure:' + visit_date.isoformat()))
    elif visit_date is None and closed:
        result.append(Notice('day_opening', 'info', (item_id,),
                             '这家场馆有每周闭馆日，确定出发日期后需要再查。' if locale == 'zh' else
                             'This venue has weekly closing days; check them after choosing your departure date.',
                             citation, 7, entry['id'] + ':undated-closure'))
    required = conditions['reservation_required']
    days = conditions['advance_booking_days']
    rule = conditions['advance_booking_rule']
    if required is True:
        text = '这家场馆需要预约。' if locale == 'zh' else 'This venue requires a reservation.'
        if days is not None and rule == 'minimum_lead':
            text = f'这家场馆需要至少提前{days}天预约。' if locale == 'zh' else f'This venue requires booking at least {days} days ahead.'
        elif days is not None and rule == 'window_max':
            text += f'最多可提前{days}天预约。' if locale == 'zh' else f' Reservations open up to {days} days ahead.'
        result.append(Notice('reservation', 'warning', (item_id,), text, citation, 2, entry['id'] + ':booking'))
    elif days is not None and rule == 'window_max':
        text = (f'常规散客无需强制预约；可选预约最多提前{days}天，并非至少提前{days}天。' if locale == 'zh' else
                f'Regular individual visits do not require booking; optional reservations open up to {days} days ahead, not a {days}-day minimum.') if required is False else (
                f'预约渠道最多可提前{days}天；是否必须预约仍需确认。' if locale == 'zh' else
                f'The booking channel opens up to {days} days ahead; whether booking is required remains unconfirmed.')
        result.append(Notice('reservation', 'info', (item_id,), text, citation, 6, entry['id'] + ':booking'))
    return tuple(result)


def calendar_notices(days, *, locale):
    result = []
    citation = Citation('中国节假日安排' if locale == 'zh' else 'China holiday calendar',
                        'https://github.com/liriansu-opus/chinese-calendar')
    for day in days:
        observation = classify(day)
        if observation.kind == 'makeup_workday':
            text = f'{day.isoformat()}是调休工作日，请按工作日核对营业与交通安排。' if locale == 'zh' else (
                f'{day.isoformat()} is a makeup working day; check weekday opening and transport arrangements.')
        elif observation.long_break:
            text = f'{day.isoformat()}处于节日长假，建议提前核对交通和预约安排。' if locale == 'zh' else (
                f'{day.isoformat()} is within a long holiday break; check transport and reservations ahead.')
        elif observation.kind == 'unknown':
            text = f'{day.isoformat()}的节假日安排尚未确认。' if locale == 'zh' else f'The holiday calendar for {day.isoformat()} is unconfirmed.'
        else:
            continue
        result.append(Notice('holiday', 'info', (), text, citation, 5, day.isoformat()))
    return tuple(result)


def route_notices(legs, *, source, locale):
    result = []
    for leg in legs:
        if leg['state'] != 'estimated':
            continue
        observation = source.observation(leg['source'], 'route')
        if (observation['duration_seconds'] != leg['duration_seconds']
                or observation['distance_m'] != leg['distance_m'] or observation['mode'] != leg['mode']):
            raise SourceRejected('notice.route', 'actual route quantities and mode required')
        # Complete endpoint/coordinate binding is checked by structured_v4's
        # candidate validator before the host renders/saves this same candidate.
        if leg['duration_seconds'] > 3600:
            result.append(Notice('long_transfer', 'info', (leg['from_item_id'], leg['to_item_id']),
                                 '这段交通预计超过60分钟，建议留足时间。' if locale == 'zh' else
                                 'This transfer is estimated to take over 60 minutes; allow enough time.',
                                 Citation('高德路线估算' if locale == 'zh' else 'Amap route estimate'), 3,
                                 sha256(packed(leg)).hexdigest()))
    return tuple(result)


def winter_outdoor_notice(*, season, outdoor_item_ids, locale):
    """Only an accepted explicit season and protected outdoor classifications.

    No city latitude, undated date or outdoor status is guessed from a name.
    This is generic preparation advice, not a weather/opening claim.
    """
    if season != 'winter' or not outdoor_item_ids:
        return ()
    for item_id in outdoor_item_ids:
        identifier(item_id)
    return (Notice('season', 'info', tuple(dict.fromkeys(outdoor_item_ids)),
                   '冬季户外活动注意保暖，并在出发前查看天气。' if locale == 'zh' else
                   'Dress warmly for winter outdoor activities and check the weather before setting out.',
                   Citation('冬季出游通用提示' if locale == 'zh' else 'General winter travel advice'),
                   9, 'winter-outdoor'),)
