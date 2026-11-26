"""Answer follow-ups for the one-screen layout (W2-1, #1727): fixed actions and tap-to-ask chips.

Pure functions, no I/O and no wire format. The server chooses which buttons an answer may carry
(`allowed_actions`); the model never writes a tool name, a parameter, a coordinate, a URL or a
button label. Anything outside the list is dropped, and a model chip that is too long or has
control characters is dropped, so a bad follow-up never fails the answer.

The four actions match the App registry (`payment-guide`, `taxi`, `trip`):

    {"tool": "payment-guide", "parameters": {}, "label": "打开支付开通指南"}
    {"tool": "payment-guide", "parameters": {"section": "troubleshooting"}, "label": "支付遇到问题"}
    {"tool": "taxi", "parameters": {} | {destination_*}, "label": "打车" | "打车去这里"}
    {"tool": "trip", "parameters": {"trip_id": "..."}, "label": "查看行程"}
"""
from dataclasses import dataclass
import re

VERSION = 'LIO-answer-followups.1'
MAX_ACTIONS = 2
MAX_CHIPS = 3
MAX_PARAMETERS = 8
MAX_VALUE_CHARS = 200
MAX_PARAMETERS_BYTES = 600
CHIP_LABEL_LIMIT = {'zh': 12, 'en': 24}

_CONTROL = re.compile(r'[\x00-\x1f\x7f  ]')
_TRIP_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
_COORDINATE = re.compile(r'(-?[0-9]{1,3}(?:\.[0-9]{1,6})?),(-?[0-9]{1,2}(?:\.[0-9]{1,6})?)')
# GCJ-02 only covers mainland China; the box is a coarse guard, not a border.
_CHINA_LNG, _CHINA_LAT = (73.0, 136.0), (3.0, 54.0)

# tool -> {parameter name: required}; the App's own validation uses the same names.
_PARAMETER_NAMES = {
    'payment-guide': {'section': False},
    'taxi': {'destination_name_zh': False, 'destination_name_en': False,
             'destination_location': False, 'destination_address_zh': False},
    'trip': {'trip_id': True},
}
_SECTIONS = ('troubleshooting',)

LABELS = {
    'payment_setup': ('打开支付开通指南', 'Payment setup guide'),
    'payment_trouble': ('支付遇到问题', 'Payment problems'),
    'taxi_to': ('打车去这里', 'Taxi there'),
    'taxi': ('打车', 'Get a taxi'),
    'trip': ('查看行程', 'View trip'),
}

_PAYMENT = re.compile(r'支付宝|微信支付|alipay|wechat\s*pay|weixin\s*pay|付款|移动支付|扫码|银行卡|信用卡|\bvisa\b|mastercard|'
                      r'\bpay(?:ing|ment)?\b|怎么付|如何支付', re.I)
_PAYMENT_TROUBLE = re.compile(r'付不了|失败|出错|报错|不成功|没成功|绑不了|绑不上|不能用|用不了|被拒|扣不了|'
                              r'declined|(?:not|n\'t|cannot|can\'t)\s+(?:work|pay|link|add)|failed|error', re.I)
_TAXI = re.compile(r'打车|叫车|出租车|网约车|滴滴|\bdidi\b|\btaxi\b|\bcab\b|\buber\b|\bride[- ]?hail', re.I)


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


def valid_location(value):
    """'lng,lat' with at most six decimals, inside the mainland China box."""
    match = _COORDINATE.fullmatch(value) if type(value) is str else None
    if match is None:
        return False
    lng, lat = float(match.group(1)), float(match.group(2))
    return _CHINA_LNG[0] <= lng <= _CHINA_LNG[1] and _CHINA_LAT[0] <= lat <= _CHINA_LAT[1]


def checked_parameters(tool, parameters):
    """The parameters when the tool and every value pass the App registry rules, else None."""
    names = _PARAMETER_NAMES.get(tool)
    if names is None or type(parameters) is not dict or len(parameters) > MAX_PARAMETERS:
        return None
    if not set(parameters) <= set(names) or any(required and name not in parameters for name, required in names.items()):
        return None
    cleaned = {}
    for name, value in parameters.items():
        value = _clean(value)
        if value is None:
            return None
        cleaned[name] = value
    if tool == 'trip' and _TRIP_ID.fullmatch(cleaned['trip_id']) is None:
        return None
    if tool == 'payment-guide' and cleaned.get('section', _SECTIONS[0]) not in _SECTIONS:
        return None
    if tool == 'taxi':
        # A destination needs its name and a coordinate together; half a destination is dropped.
        has = {name for name in cleaned if name in ('destination_name_zh', 'destination_location')}
        if cleaned and has != {'destination_name_zh', 'destination_location'}:
            return None
        if cleaned and not valid_location(cleaned['destination_location']):
            return None
    if len(repr(sorted(cleaned.items())).encode('utf-8')) > MAX_PARAMETERS_BYTES:
        return None
    return cleaned


def topics(question):
    """Which button topics a question is about: payment, payment_trouble, taxi."""
    found = []
    if _PAYMENT.search(question):
        found.append('payment')
        if _PAYMENT_TROUBLE.search(question):
            found.append('payment_trouble')
    if _TAXI.search(question):
        found.append('taxi')
    return found


def allowed_actions(question, locale, *, destination=None, saved_trip_id=None):
    """The buttons this answer may carry, at most MAX_ACTIONS, in a fixed order.

    `destination` is a Destination taken from this run's tool evidence (never from the model);
    `saved_trip_id` is a trip the account has saved. Labels come from the fixed table.
    """
    index = 0 if locale == 'zh' else 1
    found = topics(question)
    actions = []
    if 'payment' in found:
        actions.append(Action('payment-guide', {}, LABELS['payment_setup'][index]))
        if 'payment_trouble' in found:
            actions.append(Action('payment-guide', {'section': 'troubleshooting'}, LABELS['payment_trouble'][index]))
    if 'taxi' in found:
        parameters = {}
        key = 'taxi'
        if destination is not None and valid_location(destination.location) and _clean(destination.name_zh):
            parameters = {'destination_name_zh': destination.name_zh.strip(), 'destination_location': destination.location}
            for name, value in (('destination_address_zh', destination.address_zh), ('destination_name_en', destination.name_en)):
                if _clean(value):
                    parameters[name] = value.strip()
            key = 'taxi_to'
        actions.append(Action('taxi', parameters, LABELS[key][index]))
    if saved_trip_id is not None and _TRIP_ID.fullmatch(saved_trip_id) and not actions:
        actions.append(Action('trip', {'trip_id': saved_trip_id}, LABELS['trip'][index]))
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
