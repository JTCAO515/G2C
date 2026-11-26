"""Answer follow-ups for the one-screen layout (W2-1, #1727): fixed action buttons, bounded chips.

Pure functions, no I/O and no wire format. The server chooses which buttons an answer may carry
(`allowed_actions`); the model never writes a tool name, a parameter, a coordinate, a URL or a
button label. Anything outside the list is dropped, and a model chip that is too long or has
control characters is dropped, so a bad follow-up never fails the answer.

The buttons match what the App registers today (`LioToolRegistry`, #1724): `payment-guide` takes
no parameters and `taxi` takes `destination`, `destinationEN`, `address`, `lat`, `lng`. A button
for a tool or a parameter the App does not register yet (a payment troubleshooting section, a
saved trip) is added together with the App, as a table row and a test, not before.

    {"tool": "payment-guide", "parameters": {}, "label": "打开支付开通指南"}
    {"tool": "taxi", "parameters": {} | {"destination", "lat", "lng", ...}, "label": "打车" | "打车去这里"}
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import secrets
import time

VERSION = 'LIO-answer-followups.1'
MAX_ACTIONS = 2
MAX_CHIPS = 3
MAX_PARAMETERS = 8
MAX_VALUE_CHARS = 200
MAX_PARAMETERS_BYTES = 600
CHIP_LABEL_LIMIT = {'zh': 12, 'en': 24}
TICKET_SECONDS = 24 * 3600
_TICKET = re.compile(r'[A-Za-z0-9_-]{43}')

_CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f​-‏ -‮⁠-⁤﻿]')
_LNG = re.compile(r'-?[0-9]{1,3}(?:\.[0-9]{1,6})?')
_LAT = re.compile(r'-?[0-9]{1,2}(?:\.[0-9]{1,6})?')
# GCJ-02 only covers mainland China; the box is a coarse guard, not a border.
_CHINA_LNG, _CHINA_LAT = (73.0, 136.0), (3.0, 54.0)

# tool -> {parameter name: required}; the App's route declares the same names and drops any other key.
_PARAMETER_NAMES = {
    'payment-guide': {},
    'taxi': {'destination': False, 'destinationEN': False, 'address': False, 'lat': False, 'lng': False},
}

LABELS = {
    'payment_setup': ('打开支付开通指南', 'Payment setup guide'),
    'taxi_to': ('打车去这里', 'Taxi there'),
    'taxi': ('打车', 'Get a taxi'),
}

_PAYMENT = re.compile(r'支付宝|微信支付|alipay|wechat\s*pay|weixin\s*pay|付款|移动支付|扫码|银行卡|信用卡|'
                      r'visa\s+(?:card|credit|debit)|mastercard|pay(?:ing)?\s+with\b|\bpay(?:ing|ment)?\b|怎么付|如何支付', re.I)
_TAXI = re.compile(r'打车|打的|叫车|叫个车|出租车|网约车|滴滴|\bdidi\b|\btaxis?\b|\bcabs?\b|\buber\b|\bride[- ]?hail', re.I)


@dataclass(frozen=True)
class Action:
    tool: str
    parameters: dict
    label: str

    def wire(self):
        return dict(tool=self.tool, parameters=dict(self.parameters), label=self.label)


@dataclass(frozen=True)
class Destination:
    """A place the server already sent in this answer's tool evidence; never model text."""
    name_zh: str
    location: str  # "lng,lat" GCJ-02
    address_zh: str | None = None
    name_en: str | None = None


def _clean(value):
    """A parameter value: a string without control characters, stripped, non-empty, bounded."""
    if type(value) is not str or _CONTROL.search(value):
        return None
    value = value.strip()
    return value if 0 < len(value) <= MAX_VALUE_CHARS else None


def _in_china(lng, lat):
    if _LNG.fullmatch(lng) is None or _LAT.fullmatch(lat) is None:
        return False
    return _CHINA_LNG[0] <= float(lng) <= _CHINA_LNG[1] and _CHINA_LAT[0] <= float(lat) <= _CHINA_LAT[1]


def valid_location(value):
    """'lng,lat' with at most six decimals, inside the mainland China box."""
    lng, comma, lat = value.partition(',') if type(value) is str else ('', '', '')
    return bool(comma) and _in_china(lng, lat)


def checked_parameters(tool, parameters):
    """The parameters when the tool and every value pass the App registry rules, else None."""
    names = _PARAMETER_NAMES.get(tool)
    if names is None or type(parameters) is not dict or len(parameters) > MAX_PARAMETERS or not set(parameters) <= set(names):
        return None
    cleaned = {}
    for name, value in parameters.items():
        value = _clean(value)
        if value is None:
            return None
        cleaned[name] = value
    # A destination needs its Chinese name and both coordinates together; half a destination is dropped.
    if tool == 'taxi' and cleaned and (not {'destination', 'lat', 'lng'} <= set(cleaned)
                                      or not _in_china(cleaned['lng'], cleaned['lat'])):
        return None
    if len(json.dumps(cleaned, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')) > MAX_PARAMETERS_BYTES:
        return None
    return cleaned


def topics(question):
    """Which button topics a question is about: payment, taxi."""
    return [name for name, pattern in (('payment', _PAYMENT), ('taxi', _TAXI)) if pattern.search(question)]


def allowed_actions(question, locale, *, destination=None):
    """The buttons this answer may carry, at most MAX_ACTIONS, in a fixed order.

    `destination` is a Destination taken from this run's tool evidence (never from the model).
    Labels come from the fixed table.
    """
    index = 0 if locale == 'zh' else 1
    found = topics(question)
    actions = []
    if 'payment' in found:
        actions.append(Action('payment-guide', {}, LABELS['payment_setup'][index]))
    if 'taxi' in found:
        parameters = {}
        key = 'taxi'
        if destination is not None and valid_location(destination.location) and _clean(destination.name_zh):
            lng, _, lat = destination.location.partition(',')
            parameters = {'destination': destination.name_zh.strip(), 'lat': lat, 'lng': lng}
            for name, value in (('address', destination.address_zh), ('destinationEN', destination.name_en)):
                if _clean(value):
                    parameters[name] = value.strip()
            key = 'taxi_to'
        actions.append(Action('taxi', parameters, LABELS[key][index]))
    return [action for action in actions if checked_parameters(action.tool, action.parameters) is not None][:MAX_ACTIONS]


def pick_actions(offered, chosen):
    """The model's chosen buttons, as indexes into `offered`; anything outside the list is dropped."""
    picked = []
    for item in chosen if type(chosen) is list else []:
        if type(item) is int and not isinstance(item, bool) and 0 <= item < len(offered) and offered[item] not in picked:
            picked.append(offered[item])
    return picked[:MAX_ACTIONS]


def chips(raw, locale, *, forbidden=()):
    """Model chips (a list of label strings) that pass the length and character rules, at most MAX_CHIPS.

    A chip that repeats an action label, repeats another chip or has a control character is dropped.
    """
    limit = CHIP_LABEL_LIMIT['zh' if locale == 'zh' else 'en']
    kept = []
    for label in raw if type(raw) is list else []:
        if type(label) is not str or _CONTROL.search(label):
            continue
        label = ' '.join(label.split())
        if not 1 <= len(label) <= limit or label in kept or label in forbidden:
            continue
        kept.append(label)
    return kept[:MAX_CHIPS]


# Tap-to-ask questions, chosen by the code from the topic of the traveler's question and reviewed here,
# not written by the model. The App sends the label back as the next question; it is an ordinary
# question to Lio, so a chip cannot ask for anything a typed question could not.
CHIP_TABLE = {
    'payment': (('付不了怎么办', 'What if payment fails?'), ('哪些地方不能用', "Where can't I use it?"),
                ('怎么开通地铁乘车码', 'How do I ride the metro?')),
    'taxi': (('打车怎么付款', 'How do I pay a taxi?'), ('怎么告诉司机去哪', 'How to tell the driver?'),
             ('机场打车注意什么', 'Airport taxi tips')),
}


def chips_for(question, locale):
    """The chip labels for this question's first topic that has any, at most MAX_CHIPS, checked."""
    index = 0 if locale == 'zh' else 1
    for topic in topics(question):
        rows = CHIP_TABLE.get(topic)
        if rows:
            return chips([row[index] for row in rows], locale)
    return []


def label_sha256(label):
    """Exactly the bytes the App sends back as the question text; no normalisation."""
    return sha256(label.encode('utf-8')).hexdigest()


def new_tickets(count):
    """Fresh one-time tickets: 32 random bytes, 43 characters of base64url."""
    return [secrets.token_urlsafe(32) for _ in range(count)]


def valid_ticket(value):
    return type(value) is str and _TICKET.fullmatch(value) is not None


def followups_payload(actions, chips_with_tickets, *, now=None):
    """What the worker stores for a row: the buttons, the chips with their tickets and the issue time."""
    return dict(actions=list(actions), chips=[dict(label=label, ticket=ticket) for label, ticket in chips_with_tickets],
                issued_at=int(time.time() if now is None else now))


def wire_followups(payload, *, now=None):
    """The `followups` object for a timeline row from a stored payload, or None when nothing valid is left.

    The stored record was written by the server; the read re-checks it anyway so a damaged record can
    never put an unlisted tool, a bad parameter or a malformed ticket on the wire. A chip keeps its
    ticket for 24 hours after it was offered; after that it is shown without one (not tappable).
    """
    if type(payload) is not dict or set(payload) - {'actions', 'chips', 'issued_at'}:
        return None
    kept = []
    for item in payload.get('actions') if type(payload.get('actions')) is list else []:
        if (type(item) is not dict or set(item) != {'tool', 'parameters', 'label'} or type(item['label']) is not str
                or not item['label'] or len(item['label']) > 24 or _CONTROL.search(item['label'])):
            continue
        parameters = checked_parameters(item['tool'], item['parameters'])
        if parameters is not None and parameters == item['parameters']:
            kept.append(dict(tool=item['tool'], parameters=parameters, label=item['label']))
    issued = payload.get('issued_at')
    fresh = type(issued) is int and 0 <= int(time.time() if now is None else now) - issued < TICKET_SECONDS
    shown = []
    for item in payload.get('chips') if type(payload.get('chips')) is list else []:
        if type(item) is not dict or set(item) - {'label', 'ticket'} or type(item.get('label')) is not str:
            continue
        label = item['label']
        if not label or len(label) > 24 or _CONTROL.search(label) or label != ' '.join(label.split()) or any(c['label'] == label for c in shown):
            continue
        chip = dict(label=label)
        if fresh and valid_ticket(item.get('ticket')):
            chip['ticket'] = item['ticket']
        shown.append(chip)
    result = dict(version=VERSION)
    if kept[:MAX_ACTIONS]:
        result['actions'] = kept[:MAX_ACTIONS]
    if shown[:MAX_CHIPS]:
        result['chips'] = shown[:MAX_CHIPS]
    return result if len(result) > 1 else None
