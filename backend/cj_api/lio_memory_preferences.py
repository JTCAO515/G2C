"""Explicit preference language supported by the synthetic Lio pilot."""
import re


_EN = r"(?:I (?:(?:usually|always|generally) )?(?:prefer|like|enjoy) |prefers? )?"
_ZH = r'(?:我(?:平时|通常|一般|一直)?(?:更)?(?:喜欢|偏爱|偏好|习惯|更爱))?'
_INTEREST_EN = r'(?:art|museums?|architecture|history|nature|scenic walks|food markets|local food)'
_INTEREST_ZH = r'(?:博物馆|美术馆|艺术|建筑|历史|自然风景|城市漫步|美食|菜市场)'
_REMEMBER = re.compile(r'^(?:请(?:帮我)?记住[，、：:\s]*|(?:please )?remember(?: that)?[,:\s]+)', re.I)
_TRAVEL_QUALIFIER = re.compile(r' (?:when I travel|when travelling|when traveling)$', re.I)


def _forms(english, chinese, *, extra=''):
    forms = (_EN + '(?P<en>' + english + ')', _ZH + '(?P<zh>' + chinese + ')')
    return re.compile('|'.join((*forms, extra) if extra else forms), re.IGNORECASE)


_FORMS = {
    'travel.pace': _forms(
        r'(?:a )?(?:slow(?:er)?|fast(?:er)?|relaxed|leisurely) (?:travel pace|pace|trips?)|'
        r'(?:slow|fast)[- ]paced trips?|fewer stops (?:in|per) a? ?day|'
        r'no more than (?:one|two|three|[1-3]) sights a day',
        r'(?:慢节奏|快节奏)(?:(?:的)?(?:旅行|行程|旅游))?|(?:轻松|悠闲)(?:的)?(?:旅行|行程|旅游)|'
        r'每天(?:只|最多)(?:一|两|二|三|[1-3])个景点',
    ),
    'travel.budget': _forms(
        r'(?:budget[- ]friendly|moderate[- ]budget|luxury) trips?|'
        r'(?:a )?budget (?:of )?(?:about |around |under )?[0-9]{1,5} (?:yuan|CNY|RMB|USD) (?:per|a) day',
        r'(?:经济实惠|中等预算|高预算)(?:的)?(?:旅行|行程)|旅行预算(?:通常|一般)?(?:为|是)?每天[0-9]{1,5}元',
        extra=r'I usually budget [0-9]{1,5} (?:yuan|CNY|RMB|USD) (?:per|a) day',
    ),
    'lodging.style': _forms(
        r'(?:staying (?:at|in) )?(?:budget|boutique|central|quiet|upscale|family-friendly) hotels?',
        r'(?:住)?(?:经济型|精品|市中心的|安静的|高档|家庭友好型)(?:酒店|住宿)',
    ),
    'travel.interests': _forms(
        _INTEREST_EN + r'(?: and ' + _INTEREST_EN + r')?',
        _INTEREST_ZH + r'(?:(?:和|、)' + _INTEREST_ZH + r')?',
    ),
    'diet.spicy': _forms(
        r'(?:mild|non[- ]spicy|spicy|not too spicy) food',
        r'(?:吃辣|不吃辣|少辣|微辣|口味清淡|清淡(?:的)?口味|辛辣(?:的)?食物)',
        extra=r"I (?:don't like|avoid) spicy food|no spicy food|我(?:平时|通常)?(?:不吃辣|吃辣)",
    ),
    'diet.taste': _forms(
        r'(?:sweet|savory|sour|salty) (?:food|flavo[u]?rs?)|(?:Cantonese|Sichuan|local) (?:food|cuisine)',
        r'(?:甜口|咸口|酸口|甜味|咸味|酸味|粤菜|川菜|当地菜|当地美食)',
    ),
    'quiet.entrance': _forms(
        r'(?:using )?(?:the )?quiet(?:er)? entrances?(?: (?:at|to) (?:parks|attractions|museums))?',
        r'(?:从|走|使用)?(?:比较)?安静的入口(?:进景点|进入景点)?',
    ),
}

PREFERENCE_SLOTS = frozenset(_FORMS)
_EXISTING_SLOTS = frozenset({'diet.spicy', 'quiet.entrance'})


def _value(form, text):
    text = _REMEMBER.sub('', text.strip()).rstrip('.。!！')
    text = _TRAVEL_QUALIFIER.sub('', text)
    match = form.fullmatch(text)
    if match is None:
        return None
    value = (match['en'] or match['zh'] or match[0]).casefold()
    if value.startswith(('慢节奏', '快节奏')):
        return value[:3]
    return value.removeprefix('a ')


def allows_pilot_preference_write(command):
    if command.slot in _EXISTING_SLOTS:
        return True
    form = _FORMS.get(command.slot)
    return (form is not None and command.kind == 'preference'
            and _value(form, command.text) is not None)


def supported_preference(entry, original):
    """Accept only a supported value stated in the complete original turn."""
    form = _FORMS.get(entry.slot)
    if entry.kind != 'preference' or form is None:
        return False
    value = _value(form, entry.text)
    if value is None or any(_value(form, evidence.quote) != value for evidence in entry.evidence):
        return False
    statements = [part.strip() for part in re.split(r'(?<=[.!。！])\s+|[。！]', original) if part.strip()]
    values = {_value(form, statement) for statement in statements} - {None}
    return (values == {value}
            and all(any(_value(allowed, statement) is not None for allowed in _FORMS.values())
                    for statement in statements))
