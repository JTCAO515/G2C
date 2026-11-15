"""Synthetic source facts and full-place-name replies; no network or stored authority."""
from datetime import date, timedelta
from cj_needs.domain import Command, Revision, Snapshot
from cj_trip.domain import packed
from cj_draft.grouped_plan import DATED_FIRST, DATED_DELTA, ORDINAL_FIRST, ORDINAL_DELTA

EN = ('Tiananmen Square', 'Forbidden City', 'Temple of Heaven', 'Beihai Park',
      'National Museum of China', 'Summer Palace', 'Beijing Zoo', 'Houhai', 'Jingshan Park', '798 Art District')
ZH = ('天安门广场', '故宫', '天坛公园', '北海公园', '中国国家博物馆', '颐和园', '北京动物园', '后海', '景山公园', '798艺术区')
START = date(2026, 11, 17)


def known(value):
    return dict(state='known', value=value)


def source(days, language, *, ordinal=False, party=1, with_fixed=True):
    def event(day, clock):
        return dict(date=dict(state='unknown') if ordinal else known(day.isoformat()),
                    time=known(clock), timezone=known('Asia/Shanghai'), place=dict(state='unknown'))
    fixed = dict(item_id='hotel', kind='appointment', description='酒店集合' if language=='zh' else 'Hotel meetup',
                 applies_to=['self'] if party==1 else ['party'], locked=known(True), booking_status=known('booked'),
                 start=event(START,'09:00'), end=event(START,'10:00'))
    fields = dict(destination_timezone=known('Asia/Shanghai'), party_size=known(party), fixed_items=[fixed] if with_fixed else [],
                  arrival=event(START,'00:00'), departure=event(START+timedelta(days=days-1),'23:59'))
    raw = packed(dict(action_id='declared', needs_id='visit', expected_version=0,
                      source=dict(kind='manual',text='Synthetic explicit city/duration/party and fixed hotel meetup'), changes=fields))
    command = Command(raw)
    snapshot = Snapshot('visit',1,packed(fields))
    return snapshot,(Revision('visit',1,command.action_id,raw,snapshot.content),)


def reply(days, language, *, ordinal=False, delta=False, party=1, periods=2):
    names = ZH if language=='zh' else EN
    version = (ORDINAL_DELTA if delta else ORDINAL_FIRST) if ordinal else (DATED_DELTA if delta else DATED_FIRST)
    groups = []
    for day in range(days):
        key = day+1 if ordinal else (START+timedelta(days=day)).isoformat()
        groups.append([key, [[('b' if delta else 'a')+str(periods*day+i), names[(periods*day+i)%len(names)], begin, end,
                              ['self'] if party==1 else ['party']]
                             for i,(begin,end) in enumerate((('11:00','12:00'),('14:00','16:00'),('19:00','20:00'))[:periods])]])
    value = dict(version=version, days=groups)
    if not delta:
        value['title'] = '北京行程' if language=='zh' else 'Beijing'
    return value
