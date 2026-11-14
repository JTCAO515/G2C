"""The bilingual factor catalogue from #922 §3.1; no publication authority."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Option:
    key: str
    zh: str
    en: str


@dataclass(frozen=True)
class Factor:
    key: str
    tier: str
    weights: tuple[int, int, int]  # exploration, refinement, adjustment
    default: object
    default_zh: str
    default_en: str
    question_zh: str
    question_en: str
    options: tuple[Option, ...]
    inferable: bool = False
    memory_slots: tuple[str, ...] = ()
    multiple: bool = False

    def question(self, locale):
        zh = locale == 'zh'
        return dict(factor_key=self.key, question=self.question_zh if zh else self.question_en,
                    multiple=self.multiple, options=[dict(id=self.key+'.'+o.key,
                    display_text=o.zh if zh else o.en,
                    send_text=(LABELS[self.key][0]+': '+o.zh if zh else LABELS[self.key][1]+': '+o.en))
                    for o in self.options])


def _options(*rows):
    return tuple(Option(*row) for row in rows)


FACTORS = (
    Factor('city', 'framework', (100, 90, 20), '北京', '北京', 'Beijing (北京)',
        '先探索哪一座城市？', 'Which single city would you like to explore?',
        _options(('beijing','北京','Beijing (北京)'), ('chengdu','成都','Chengdu (成都)'),
                 ('shanghai','上海','Shanghai (上海)'), ('hangzhou','杭州','Hangzhou (杭州)'))),
    Factor('duration_days', 'framework', (95, 90, 20), 3, '3天', '3 days',
        '这趟想安排几天？', 'How many days would you like?',
        _options(('three','3天','3 days'), ('four','4天','4 days'),
                 ('five','5天','5 days'), ('seven','7天','7 days'))),
    Factor('season', 'framework', (60, 50, 10), None, '不按季节特别安排，只给通用提示',
        'General advice without a seasonal schedule', '大概哪个季节去？', 'Roughly which season?',
        _options(('spring','春季','Spring'), ('summer','夏季','Summer'),
                 ('autumn','秋季','Autumn'), ('winter','冬季','Winter')), True),
    Factor('first_visit', 'people', (65, 40, 10), True, '第一次来', 'First visit',
        '这是第一次来中国旅行吗？', 'Is this your first trip to China?',
        _options(('first','第一次','First visit'), ('return','来过中国','Returning to China'),
                 ('city_first','来过中国，这座城市是第一次','First visit to this city'))),
    Factor('party_type', 'people', (85, 80, 30), 'two_adults', '两个成人', 'Two adults',
        '这次和谁一起旅行？', 'Who is travelling with you?',
        _options(('solo','一个人','Solo'), ('two_adults','两个成人','Two adults'),
                 ('family','带孩子','With children'), ('friends','和朋友','With friends')), True),
    Factor('interests', 'interests', (90, 85, 80), ('history','food'), '历史和美食', 'History and food',
        '最想体验哪些内容？', 'What would you most like to experience?',
        _options(('history','历史文化','History and culture'), ('food','当地美食','Local food'),
                 ('nature','自然山水','Nature and scenery'), ('modern','现代城市','Modern city life')),
        True, ('travel.interests',), True),
    Factor('pace', 'style', (80, 85, 95), 'moderate', '适中', 'Moderate',
        '喜欢什么旅行节奏？', 'What travel pace do you prefer?',
        _options(('relaxed','轻松','Relaxed'), ('moderate','适中','Moderate'), ('packed','紧凑','Packed')),
        True, ('travel.pace',)),
    Factor('lodging_tier', 'style', (70, 75, 60), 'comfortable', '舒适型', 'Comfortable',
        '住宿偏好哪种风格？', 'What style of accommodation do you prefer?',
        _options(('simple','简洁实用','Simple and practical'), ('comfortable','舒适型','Comfortable'),
                 ('luxury','高端型','Luxury')), True, ('travel.budget','lodging.style')),
    Factor('dietary', 'constraint', (75, 85, 70), (), '无饮食限制', 'No dietary restrictions',
        '饮食方面有什么偏好或限制？', 'Any food preferences or dietary restrictions?',
        _options(('none','无饮食限制','No dietary restrictions'), ('mild','不吃辣','No spicy food'),
                 ('vegetarian','素食','Vegetarian'), ('halal','清真饮食','Halal')),
        False, ('diet.spicy','diet.taste'), True),
    Factor('must_see', 'constraint', (55, 80, 90), (), '无指定必去地点', 'No required stops',
        '有哪些一定想体验的内容？', 'Any experiences you definitely want to include?',
        _options(('museum','博物馆','Museums'), ('old_town','历史街区','Historic neighbourhoods'),
                 ('market','当地市场','Local markets')), False, (), True),
    Factor('avoid', 'constraint', (50, 75, 80), (), '无指定避开事项', 'Nothing specifically excluded',
        '有哪些希望避开的安排？', 'Anything you would like to avoid?',
        _options(('crowds','拥挤地点','Crowded places'), ('shopping','购物安排','Shopping stops'),
                 ('late','深夜活动','Late-night activities')), False, (), True),
    Factor('mobility', 'constraint', (60, 90, 85), None, '无行动限制', 'No mobility restrictions',
        '步行或台阶有什么需要注意的？', 'Anything to consider about walking or stairs?',
        _options(('none','无行动限制','No mobility restrictions'), ('less','少走路','Less walking'),
                 ('stairs','避开台阶','Avoid stairs'), ('wheelchair','需要无障碍路线','Wheelchair-accessible routes'))),
    Factor('arrival', 'constraint', (40, 70, 75), None, '到达时刻未知', 'Arrival time unknown',
        '预计一天里的什么时段到达？', 'Roughly what time of day will you arrive?',
        _options(('morning','上午到达','Arrive in the morning'), ('afternoon','下午到达','Arrive in the afternoon'),
                 ('evening','晚上到达','Arrive in the evening'))),
    Factor('departure', 'constraint', (35, 65, 75), None, '离开时刻未知', 'Departure time unknown',
        '预计一天里的什么时段离开？', 'Roughly what time of day will you leave?',
        _options(('morning','上午离开','Leave in the morning'), ('afternoon','下午离开','Leave in the afternoon'),
                 ('evening','晚上离开','Leave in the evening'))),
)
BY_KEY = {factor.key: factor for factor in FACTORS}
LABELS = {
    'city': ('目的地','Destination','City'), 'duration_days': ('天数','Trip length','Duration'),
    'season': ('季节','Season'), 'first_visit': ('来华经历','Previous visits'),
    'party_type': ('同行人','Travel party'), 'interests': ('兴趣','Interests'),
    'pace': ('节奏','Travel pace','Pace'), 'lodging_tier': ('住宿','Accommodation'),
    'dietary': ('饮食','Dietary preferences'), 'must_see': ('必去','Must see'),
    'avoid': ('避开','Avoid'), 'mobility': ('行动需求','Mobility'),
    'arrival': ('到达','Arrival'), 'departure': ('离开','Departure')}


def defaults(profile):
    """Compute proposals only. The caller must bind a real plan-now policy source.

    These are not user facts, precise dates, NEEDS input or permission to save.
    WP4/WP8 own disclosure and the protected publication boundary.
    """
    values = {factor.key: factor.default for factor in FACTORS
              if factor.key not in profile or profile[factor.key].state in ('not_needed','default')}
    if 'city' in values:
        interests = profile.get('interests')
        if interests is not None:
            choices = interests.value if isinstance(interests.value, tuple) else (interests.value,)
            values['city'] = next((city for key,city in (('history','北京'),('food','成都'),
                ('modern','上海'),('nature','杭州')) if key in choices), '北京')
    return values
