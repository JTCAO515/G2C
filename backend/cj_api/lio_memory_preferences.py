"""Explicit preference language supported by the synthetic Lio pilot."""
import re


_EN = r"(?:I (?:(?:usually|always|generally) )?(?:prefer|like|enjoy) |prefers? )?"
_ZH = r'(?:我(?:旅行时|旅游时)?(?:平时|通常|一般|一直)?(?:更)?(?:喜欢|偏爱|偏好|习惯|更爱))?'
_INTEREST_EN = r'(?:art|museums?|architecture|history|nature|scenic walks|food markets|local food)'
_INTEREST_ZH = r'(?:博物馆|美术馆|艺术|建筑|历史|自然风景|城市漫步|美食|菜市场)'
_REMEMBER = re.compile(r'^(?:(?:请(?:帮我)?)?记住[，、：:\s]*|(?:please )?remember(?: that)?[,:\s]+)', re.I)
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
        r'(?:budget[- ]friendly|moderate[- ]budget) trips?|'
        r'(?:a |an )?(?:luxury|luxurious|upscale) (?:trips?|travel(?: experiences?)?|vacations?|holidays?)|'
        r'(?:a )?budget (?:of )?(?:about |around |under )?[0-9]{1,5} (?:yuan|CNY|RMB|USD) (?:per|a) day',
        r'(?:经济实惠|中等预算|高预算|豪华|奢华|高端)(?:的)?(?:旅行|行程|旅游)(?:体验)?|'
        r'旅行预算(?:通常|一般)?(?:为|是)?每天[0-9]{1,5}元',
        extra=r'I usually budget [0-9]{1,5} (?:yuan|CNY|RMB|USD) (?:per|a) day',
    ),
    'lodging.style': _forms(
        r'(?:(?:staying|to stay) (?:at|in) )?(?:budget|boutique|central|quiet|upscale|luxury|luxurious|family-friendly) hotels?',
        r'(?:住)?(?:经济型|精品|市中心的|安静的|高档|豪华|奢华|家庭友好型)(?:的)?(?:酒店|住宿)',
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

# #2000 (M-2): health (allergy, illness, disability, mobility, pregnancy, medication) and religion (faith, halal /
# kosher / fasting, places of worship, "no pork" style diet rules) never become a memory candidate. The seven slots
# above are already ordinary tastes and habits; this is a second, independent gate over the WHOLE original turn and
# over the entry itself, so a sensitive word anywhere makes the turn yield nothing, whatever the model proposed.
# Allergies stay only in the phone-local show card. The match is deliberately broad: a missed preference costs one
# tap; a remembered diagnosis or faith costs trust. Travel-only words (a "temple" to visit) are not on the list.
_SENSITIVE = re.compile(
    r'过敏|敏感体质|哮喘|糖尿病|高血压|心脏病|癌|病史|疾病|生病|患有|患者|胃病|肠胃|肠炎|癫痫|抑郁|焦虑症|精神疾病|精神类|失眠|药|'
    r'怀孕|孕妇|孕期|哺乳|残疾|残障|行动不便|行动困难|腿脚不便|轮椅|拐杖|助行|视障|盲人|听障|耳聋|乳糖不耐|麸质|乳糜|'
    r'透析|手术|康复|医疗|医生|就医|诊断|低糖|无糖|忌口|'
    r'宗教|信仰|信教|教徒|穆斯林|回教|伊斯兰|清真|斋月|开斋|礼拜|祷告|祈祷|佛教|佛祖|拜佛|信佛|基督|天主|耶稣|教会|犹太|印度教|锡克|道教|'
    r'不吃猪|不吃牛|不吃荤|吃素|素食|斋戒|洁食|'
    r'有孕|孕在身|身体不好|身体不太好|腿(?:脚)?(?:不好|不便|疼|痛|有问题)|膝(?:盖)?(?:不好|疼|痛|有问题)|腰(?:不好|疼|痛|有问题)|关节|痛风|溃疡|高血糖|心脏|化疗|头疼|头痛|耳聋|失明|无障碍|自闭|多动症|'
    r'念经|诵经|礼佛|拜拜|安息日|耆那|周五不吃肉|斋日|'
    r'chemo|arthritis|\bdeaf\b|\bblind\b|\bautis|\badhd\b|accessib|\bbad (?:back|knee|knees|leg|legs)\b|can.?t (?:climb|walk)|shabbat|\bjain\b|pescatarian|on fridays|\bkosher\b|'
    r'allerg|asthma|diabet|hypertension|blood pressure|heart (?:disease|condition)|cancer|chronic|disease|illness|medical|'
    r'medicat|medicine|prescription|\bpills?\b|diagnos|disabilit|disabled|wheelchair|mobility|walking (?:aid|stick)|crutch|'
    r'pregnan|nursing mother|breastfeed|depress|anxiety disorder|mental health|epilep|dialysis|surgery|injur|'
    r'gluten|celiac|lactose|intoleran|'
    r'religio|faith|muslim|islam|halal|ramadan|fasting|prayer|\bpray|church|mosque|synagogue|buddhis|christian|'
    r'catholic|jewish|kosher|hindu|\bsikh|taoist|no pork|(?:don.?t|do not|never) eat (?:pork|beef)|vegetarian|vegan',
    re.IGNORECASE)


def sensitive(text):
    """True when text mentions health or religion (see above)."""
    return type(text) is not str or _SENSITIVE.search(text) is not None


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
    if sensitive(command.text):
        return False
    if command.slot in _EXISTING_SLOTS:
        return True
    form = _FORMS.get(command.slot)
    return (form is not None and command.kind == 'preference'
            and _value(form, command.text) is not None)


def explicit_pilot_preference(text, slots):
    """Resolve one complete statement within the newly approved pilot slots."""
    if sensitive(text):
        return None
    statement = _REMEMBER.sub('', text.strip())
    matches = [slot for slot in slots
               if slot in PREFERENCE_SLOTS - _EXISTING_SLOTS and _value(_FORMS[slot], statement) is not None]
    return (matches[0], statement) if len(matches) == 1 else None


def _statements(text):
    return [part.strip() for part in re.split(r'(?<=[.!。！])\s+|[。！]', text) if part.strip()]


def explicit_pilot_preferences(text, slots, *, max_entries):
    """Resolve a whole allowed statement or independent, fully supported statements."""
    single = explicit_pilot_preference(text, slots)
    if single is not None:
        return (single,)
    statements = _statements(text)
    if not statements or len(statements) > max_entries:
        return None
    found = []
    seen = set()
    for statement in statements:
        preference = explicit_pilot_preference(statement, slots)
        if preference is None or preference[0] in seen:
            return None
        seen.add(preference[0])
        found.append(preference)
    return tuple(found)


def supported_preference(entry, original):
    """Accept only a supported value stated in the complete original turn."""
    if sensitive(original) or sensitive(entry.text) or any(sensitive(evidence.quote) for evidence in entry.evidence):
        return False
    form = _FORMS.get(entry.slot)
    if entry.kind != 'preference' or form is None:
        return False
    value = _value(form, entry.text)
    if value is None or any(_value(form, evidence.quote) != value for evidence in entry.evidence):
        return False
    statements = _statements(original)
    values = {_value(form, statement) for statement in statements} - {None}
    return (values == {value}
            and all(any(_value(allowed, statement) is not None for allowed in _FORMS.values())
                    for statement in statements))
