"""Tool cards inside an answer: taxi, metro, intercity transport, currency (#1990, D-2; LIO-answer-rich.1).

Fixed table, code-chosen, never the model: the topic of the traveler's question picks the type, and every
parameter comes from this turn's own tool result (the taxi destination) or from a fixed table (cities,
currencies). `build` decides, `effect` stores, `wire` is what a read sends after checking every card again
against the same tables. Off by default: `CJ_LIO_CARDS=on` writes the effect; a row carries `rich.cards`
only for a poll that declared LIO-answer-rich.1 while `CJ_LIO_ANSWER_RICH=on` as well.

Not in this version (the contract allows them, the code does not send them yet): station data for the metro
card (needs a transit tool), and the exchange rate on the currency card (the ECB cache is read by the
internal tools service, not on the answer path; a card without a rate is a valid card).
"""
import json
import os
import re

from .lio_followups import _CONTROL, checked_parameters, valid_location

CARDS_EFFECT = 'lio_cards:'
MAX_CARDS = 3
ORDER = ('taxi', 'metro', 'transport', 'currency')
TOOLS = {'taxi': 'taxi', 'metro': 'metro-guide', 'transport': 'transport', 'currency': 'currency'}
LABELS = {
    'taxi': ('打车去这里', 'Taxi there'),
    'metro': ('看地铁线路', 'Metro map'),
    'transport': ('查火车和航班', 'Trains & flights'),
    'currency': ('汇率换算', 'Convert currency'),
}
# The six library cities that have a bundled metro map in the App (`Resources/Metro/LioMetroMap.<id>.v1.json`);
# a test compares this with the files. A city outside it gets no metro card.
METRO_CITIES = ('beijing', 'shanghai', 'guangzhou', 'shenzhen', 'chengdu', 'chongqing')
QUOTES = {
    'USD': ('美元', '美金', 'usd', 'us dollar', 'dollars'), 'EUR': ('欧元', 'eur', 'euro'), 'GBP': ('英镑', 'gbp', 'pound'),
    'JPY': ('日元', '日币', 'jpy', 'yen'), 'KRW': ('韩元', 'krw'), 'HKD': ('港币', '港元', 'hkd'),
    'AUD': ('澳元', 'aud'), 'CAD': ('加元', 'cad'), 'SGD': ('新币', '新加坡元', 'sgd'), 'THB': ('泰铢', 'thb', 'baht'),
}
_TOPICS = {
    'metro': re.compile(r'地铁|轨道交通|metro|subway', re.I),
    'transport': re.compile(r'高铁|火车|动车|航班|机票|train|flight|high-speed', re.I),
    'currency': re.compile(r'汇率|换钱|兑换|\bexchange\b|\bconvert|currency', re.I),
}
_DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
_TEXT_LIMIT = 40


def cards_enabled():
    """`CJ_LIO_CARDS`: write the effect. Default off; anything but off/on is a configuration error."""
    value = os.environ.get('CJ_LIO_CARDS', 'off')
    if value not in ('off', 'on'):
        raise ValueError('explicit CJ_LIO_CARDS value required')
    return value == 'on'


def _cities():
    from cj_api.lio_transport import CITIES   # the same twelve cities as the App
    return CITIES


def _city(city):
    return dict(id=city.id, zh=city.name_zh, en=city.name_en)


def _found_cities(question):
    """Transport cities named in the question, in the order they appear, each once."""
    folded = question.casefold()
    found = []
    for city in _cities().values():
        positions = [i for i in (question.find(city.name_zh), _word_at(folded, city.name_en.casefold())) if i >= 0]
        if positions:
            found.append((min(positions), city))
    return [city for _, city in sorted(found, key=lambda item: item[0])]


def _word_at(text, word):
    for match in re.finditer(re.escape(word), text):
        before = text[match.start() - 1:match.start()]
        after = text[match.end():match.end() + 1]
        if not before.isalnum() or not before.isascii():
            if not (after.isalnum() and after.isascii()):
                return match.start()
    return -1


def _quote(question):
    folded = question.casefold()
    found = {code for code, names in QUOTES.items()
             if any(name in question if name.isascii() is False else re.search(r'(?<![a-z])' + re.escape(name) + r'(?![a-z])', folded)
                    for name in names)}
    return found.pop() if len(found) == 1 else None


def build(question, locale, *, destination=None, library_city=None, taxi_topic=False):
    """The cards this answer may carry, in table order, at most MAX_CARDS (a list of wire dicts, maybe empty).

    `destination` is a `lio_followups.Destination` from this answer's own map result (never model text) or None;
    `library_city` the confirmed destination city id (`lio_entities.city_for_adcode`) or None; `taxi_topic`
    says the question is about a taxi (decided by `lio_followups.topics`).
    """
    index = 0 if locale == 'zh' else 1
    cards = []
    if taxi_topic and destination is not None and valid_location(destination.location) and _clean(destination.name_zh):
        lng, _, lat = destination.location.partition(',')
        parameters = dict(destination=destination.name_zh.strip(), lat=lat, lng=lng)
        for name, value in (('address', destination.address_zh), ('destinationEN', destination.name_en)):
            if _clean(value):
                parameters[name] = value.strip()
        if checked_parameters('taxi', parameters) is not None:
            cards.append(dict(type='taxi', label=LABELS['taxi'][index], open=dict(tool='taxi', parameters=parameters)))
    if _TOPICS['metro'].search(question) and library_city in METRO_CITIES and library_city in _cities():
        cards.append(dict(type='metro', label=LABELS['metro'][index], open=dict(tool='metro-guide', parameters={}),
                          data=dict(city=_city(_cities()[library_city]))))
    if _TOPICS['transport'].search(question):
        named = _found_cities(question)
        pair = None
        if len(named) >= 2:
            pair = named[:2]
        elif len(named) == 1 and library_city in _cities() and library_city != named[0].id:
            pair = [_cities()[library_city], named[0]]
        if pair is not None:
            cards.append(dict(type='transport', label=LABELS['transport'][index],
                              open=dict(tool='transport', parameters={'from': pair[0].id, 'to': pair[1].id}),
                              data={'from': _city(pair[0]), 'to': _city(pair[1])}))
    if _TOPICS['currency'].search(question):
        card = dict(type='currency', label=LABELS['currency'][index], open=dict(tool='currency', parameters={}))
        quote = _quote(question)
        if quote is not None:
            card['data'] = dict(quote=quote)
        cards.append(card)
    return cards[:MAX_CARDS]


def _clean(value):
    return type(value) is str and bool(value.strip()) and _CONTROL.search(value) is None and len(value.strip()) <= 200


def effect(cards, issued_at):
    return CARDS_EFFECT + json.dumps(dict(cards=cards, issued_at=int(issued_at)), ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def card_entry(card, library=None):
    """The card as it may go on the wire, or None when anything about it fails the tables (read-side re-check)."""
    try:
        kind = card['type']
        allowed = {'type', 'label', 'open', 'data'} if kind in ('metro', 'transport', 'currency') else {'type', 'label', 'open'}
        if kind not in TOOLS or not set(card) <= allowed or card['label'] not in LABELS[kind]:
            return None
        opened = card['open']
        if type(opened) is not dict or set(opened) != {'tool', 'parameters'} or opened['tool'] != TOOLS[kind]:
            return None
        parameters = opened['parameters']
        data = card.get('data')
        if kind == 'taxi':
            if checked_parameters('taxi', parameters) is None or not {'destination', 'lat', 'lng'} <= set(parameters) or data is not None:
                return None
        elif kind == 'metro':
            if parameters != {} or type(data) is not dict or set(data) != {'city'} or not _city_ok(data['city'], METRO_CITIES):
                return None
        elif kind == 'transport':
            if (type(parameters) is not dict or set(parameters) != {'from', 'to'} or parameters['from'] == parameters['to']
                    or type(data) is not dict or set(data) != {'from', 'to'}
                    or not _city_ok(data['from'], tuple(_cities())) or not _city_ok(data['to'], tuple(_cities()))
                    or (data['from']['id'], data['to']['id']) != (parameters['from'], parameters['to'])):
                return None
        else:
            if parameters != {} or (data is not None and (type(data) is not dict or set(data) != {'quote'} or data['quote'] not in QUOTES)):
                return None
        return card
    except (KeyError, TypeError):
        return None


def _city_ok(value, ids):
    if type(value) is not dict or set(value) != {'id', 'zh', 'en'} or value['id'] not in ids or value['id'] not in _cities():
        return False
    city = _cities()[value['id']]
    return (value['zh'], value['en']) == (city.name_zh, city.name_en)


def wire(effect_value):
    """`rich.cards` for a row: a list in table order (one per type, at most MAX_CARDS), or None. A card that fails
    the tables is dropped alone; a record of any shape that cannot be read gives None. Never raises."""
    try:
        payload = json.loads(effect_value.removeprefix(CARDS_EFFECT))
        if type(payload) is not dict or set(payload) != {'cards', 'issued_at'} or type(payload['cards']) is not list:
            return None
        found = {}
        for card in payload['cards']:
            entry = card_entry(card)
            if entry is not None and entry['type'] not in found:
                found[entry['type']] = entry
        rows = [found[kind] for kind in ORDER if kind in found][:MAX_CARDS]
        return rows or None
    except Exception:   # a stored value of any shape reads as nothing; the row still goes out
        return None


def card_effect(question, locale, *, destination, adcode, taxi_topic, now):
    """The effect string for a finished answer, or None (switch off, no card applies)."""
    if not cards_enabled():
        return None
    from .lio_entities import city_for_adcode
    cards = build(question, locale, destination=destination, library_city=city_for_adcode(adcode), taxi_topic=taxi_topic)
    return effect(cards, now) if cards else None
