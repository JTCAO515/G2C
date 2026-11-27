"""Reviewed tap-to-ask questions by topic and by missing information (#1978, P0-4).

Pure data in the C6 draft shape (`coord/codex/C6-followup-chips.md`): `topics` and `missing_info`
map a group to rows `{"zh": ..., "en": ...}`, each written the way the traveler would say it.
The server picks from this table; the model never writes a chip. Rows are checked by
`lio_followups.chips()` when they are used and by `validate()` in the tests, so a row that is too long
or has a control character can never reach a traveler.

Adding rows: a Codex draft (`codex-inbox/C6/chips.json`) is a draft. After a human has reviewed it,
paste its rows here; nothing is loaded from `codex-inbox/`. Limits: Chinese at most 12 characters,
English at most 24, one line. No medical, religious or visa-type judgement; no business or trade-fair
content (59 is travel only).
"""

# C6 topic names; `trip` doubles as the general fallback when a question matches no other topic.
TOPICS = ('trip', 'route', 'food', 'stay', 'sight', 'money', 'network', 'entry')
# C6 missing-information groups. The task guidance's missing facts map onto them (`MISSING_TO_GROUP`).
GROUPS = ('arrival_date', 'days', 'party', 'budget', 'city', 'interests')
# lio_tasks.MISSING_FIELDS -> group; a fact without a group (venue, hotel, nationality) adds no answer chip.
MISSING_TO_GROUP = {'dates': 'arrival_date', 'days': 'days', 'party': 'party', 'budget': 'budget', 'city': 'city'}

TABLE = {
    'topics': {
        'trip': [
            {'zh': '帮我排三天行程', 'en': 'Plan 3 days for me'},
            {'zh': '第一次来玩什么', 'en': 'First-visit must-dos'},
            {'zh': '想轻松点怎么排', 'en': 'Plan a relaxed pace'},
            {'zh': '带小孩怎么安排', 'en': 'Plan a trip with kids'},
            {'zh': '第一天从哪开始', 'en': 'Where to start on day 1'},
            {'zh': '帮我加上美食', 'en': 'Add food stops'},
            {'zh': '雨天有什么备选', 'en': 'Rainy-day backup ideas'},
            {'zh': '行程里留点空闲', 'en': 'Leave some free time'},
        ],
        'route': [
            {'zh': '机场怎么进市区', 'en': 'Airport to city center'},
            {'zh': '地铁怎么坐', 'en': 'How to ride the metro'},
            {'zh': '高铁怎么买票', 'en': 'How to buy train tickets'},
            {'zh': '两城之间怎么走', 'en': 'Getting between cities'},
            {'zh': '步行距离远吗', 'en': 'Is it walkable?'},
            {'zh': '末班车是几点', 'en': 'When is the last metro?'},
            {'zh': '共享单车能用吗', 'en': 'Can I use bike sharing?'},
            {'zh': '换乘要走多远', 'en': 'How far is the transfer?'},
        ],
        'food': [
            {'zh': '附近有清真餐厅吗', 'en': 'Any halal food nearby?'},
            {'zh': '有不辣的菜吗', 'en': "Dishes that aren't spicy"},
            {'zh': '推荐当地特色菜', 'en': 'Local dishes to try'},
            {'zh': '怎么点菜', 'en': 'How do I order food?'},
            {'zh': '素食者吃什么', 'en': 'Vegetarian food options'},
            {'zh': '早餐吃什么', 'en': "What's for breakfast?"},
            {'zh': '可以叫外卖吗', 'en': 'Can I order delivery?'},
            {'zh': '小吃街在哪', 'en': 'Where are street snacks?'},
        ],
        'stay': [
            {'zh': '住哪个区域好', 'en': 'Best area to stay in'},
            {'zh': '怎么办理入住', 'en': 'How does check-in work?'},
            {'zh': '酒店怎么预订', 'en': 'How to book a hotel'},
            {'zh': '酒店能寄存行李吗', 'en': 'Can hotels hold luggage?'},
            {'zh': '民宿可以住吗', 'en': 'Are homestays okay?'},
            {'zh': '退房后行李怎么办', 'en': 'Luggage after check-out'},
            {'zh': '机场附近住哪', 'en': 'Hotels near the airport'},
            {'zh': '酒店要付押金吗', 'en': 'Do hotels take deposits?'},
        ],
        'sight': [
            {'zh': '景点要预约吗', 'en': 'Do sights need booking?'},
            {'zh': '哪些景点免费', 'en': 'Which sights are free?'},
            {'zh': '什么时候去最好', 'en': 'Best time to visit'},
            {'zh': '一个景点逛多久', 'en': 'How long per sight?'},
            {'zh': '拍照有什么限制', 'en': 'Photo rules at sights'},
            {'zh': '有适合亲子的吗', 'en': 'Any kid-friendly sights?'},
            {'zh': '景点要带护照吗', 'en': 'Do I need my passport?'},
            {'zh': '夜景去哪看', 'en': 'Where to see night views'},
        ],
        'money': [
            {'zh': '怎么换人民币', 'en': 'How to get RMB?'},
            {'zh': '外国卡能用吗', 'en': 'Do foreign cards work?'},
            {'zh': '哪里有ATM', 'en': 'Where is an ATM?'},
            {'zh': '要给小费吗', 'en': 'Do I need to tip?'},
            {'zh': '还需要现金吗', 'en': 'Is cash still needed?'},
            {'zh': '微信支付怎么开', 'en': 'Set up WeChat Pay'},
            {'zh': '每天大概花多少', 'en': 'Daily budget estimate'},
            {'zh': '汇率怎么查', 'en': 'Where to check rates'},
        ],
        'network': [
            {'zh': '怎么买手机卡', 'en': 'How to get a SIM card'},
            {'zh': '谷歌地图能用吗', 'en': 'Does Google Maps work?'},
            {'zh': '国际漫游行不行', 'en': 'Is roaming an option?'},
            {'zh': '哪里有免费WiFi', 'en': 'Where is free WiFi?'},
            {'zh': 'eSIM怎么用', 'en': 'How do eSIMs work?'},
            {'zh': '用哪个地图App', 'en': 'Which map app to use'},
            {'zh': '有翻译App吗', 'en': 'Best translation apps'},
            {'zh': '微信怎么注册', 'en': 'Sign up for WeChat'},
        ],
        'entry': [
            {'zh': '去哪查官方签证信息', 'en': 'Where to check visa info'},
            {'zh': '入境要填什么', 'en': 'What to fill at entry'},
            {'zh': '要带哪些证件', 'en': 'Which documents to bring'},
            {'zh': '免签政策怎么查', 'en': 'Where to check visa-free'},
            {'zh': '住宿登记怎么办', 'en': 'How to register lodging'},
            {'zh': '过境要看什么政策', 'en': 'Transit rules to check'},
            {'zh': '护照要有效多久', 'en': 'Passport validity rules?'},
            {'zh': '海关能带什么', 'en': 'What can I bring in?'},
        ],
    },
    'missing_info': {
        'arrival_date': [
            {'zh': '我 12 月 5 日到', 'en': 'I arrive on Dec 5'},
            {'zh': '还没定哪天到', 'en': "Dates aren't set yet"},
        ],
        'days': [
            {'zh': '大概玩三天', 'en': 'About 3 days'},
            {'zh': '还没想好几天', 'en': 'Not sure how long'},
        ],
        'party': [
            {'zh': '我一个人', 'en': "I'm traveling alone"},
            {'zh': '我们两个人', 'en': 'There are two of us'},
        ],
        'budget': [
            {'zh': '预算中等就行', 'en': 'Mid-range budget'},
            {'zh': '想省点钱', 'en': 'Keep it low-budget'},
        ],
        'city': [
            {'zh': '先去北京', 'en': 'Beijing first'},
            {'zh': '先去上海', 'en': 'Shanghai first'},
        ],
        'interests': [
            {'zh': '喜欢历史文化', 'en': 'Into history and culture'},
            {'zh': '喜欢美食', 'en': 'Love trying food'},
        ],
    },
}

MIN_PER_TOPIC = 6
LIMIT = {'zh': 12, 'en': 24}


def validate(table=None):
    """Raise ValueError when the table breaks its own rules; used by the tests and a table review."""
    table = TABLE if table is None else table
    if type(table) is not dict or set(table) != {'topics', 'missing_info'}:
        raise ValueError('chip table needs exactly topics and missing_info')
    for key, names, minimum in (('topics', TOPICS, MIN_PER_TOPIC), ('missing_info', GROUPS, 2)):
        groups = table[key]
        if type(groups) is not dict or set(groups) != set(names):
            raise ValueError(f'{key} must have exactly {sorted(names)}')
        for name, rows in groups.items():
            if type(rows) is not list or len(rows) < minimum:
                raise ValueError(f'{key}.{name} needs at least {minimum} rows')
            seen = set()
            for row in rows:
                if type(row) is not dict or set(row) != {'zh', 'en'}:
                    raise ValueError(f'{key}.{name} row needs zh and en')
                for lang, text in row.items():
                    if (type(text) is not str or text != ' '.join(text.split()) or not 1 <= len(text) <= LIMIT[lang]
                            or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in text)):
                        raise ValueError(f'{key}.{name} {lang} label is not a single short line: {text!r}')
                    if (lang, text) in seen:
                        raise ValueError(f'{key}.{name} repeats {text!r}')
                    seen.add((lang, text))
    return True
