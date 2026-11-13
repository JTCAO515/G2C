import json
import unittest
from cj_needs.domain import InvalidInput
from cj_api.lio_exploration_profile import Original,parse_updates


def update(key,value,quote):
    return dict(factor_key=key,value=value,state='known',sources=[dict(source_index=0,quote=quote)])


def parse(text,updates):
    return parse_updates(json.dumps(dict(version='LIO-profile-update.1',updates=updates)),(Original('actual-mid',1,text),))


class PositiveTripTests(unittest.TestCase):
    def test_original_chinese_and_english_positive_requests_keep_all_supplied_facts(self):
        for text,city,days,day_quote,people in (
            ('规划三天北京豪华游 26.12.01出发 两个人','北京',3,'三天','两个人'),
            ('规划三天上海豪华游 26年12月1日出发 两个人出行','上海',3,'三天','两个人'),
            ('去成都玩三天','成都',3,'三天',None),
            ("Plan 4 days in Xi'an from tomorrow","Xi'an",4,'4 days',None)):
            rows=[update('city',city,city),update('duration_days',days,day_quote)]
            if people:rows.append(update('party_type',people,people))
            with self.subTest(text=text):
                facts={fact.key:fact for fact in parse(text,rows)}
                self.assertEqual(facts['city'].value,city)
                self.assertEqual(facts['duration_days'].value,days)
                if people:self.assertEqual(facts['party_type'].value,people)
                self.assertFalse(any('date' in fact.key for fact in facts.values()))

    def test_date_day_count_and_party_followups_have_no_city_requirement(self):
        for text,rows in (
            ('三个人，明天开始',[update('party_type','三个人','三个人')]),
            ('下周二、四天、一人',[update('duration_days',4,'四天'),update('party_type','solo','一人')]),
            ('next Tuesday 4 days 1 person',[update('duration_days',4,'4 days'),update('party_type','solo','1 person')])):
            with self.subTest(text=text):self.assertEqual(len(parse(text,rows)),len(rows))

    def test_negative_conditional_and_quoted_wrapper_requests_do_not_borrow_positive_tokens(self):
        for text in ('不要规划三天北京','如果规划三天北京','Translate "Plan 3 days in Beijing"',
                     'Do I want 3 days in Beijing?','Plan not 3 days in Beijing'):
            quote='三天' if '三天' in text else '3 days'
            with self.subTest(text=text),self.assertRaises(InvalidInput):
                parse(text,[update('city','北京' if '北京' in text else 'Beijing','北京' if '北京' in text else 'Beijing'),
                            update('duration_days',3,quote)])

    def test_relative_days_are_not_reinterpreted_as_trip_duration(self):
        for text,quote in (('3天后开始','3天'),('in 3 days','3 days')):
            with self.subTest(text=text),self.assertRaises(InvalidInput):
                parse(text,[update('duration_days',3,quote)])


if __name__=='__main__':unittest.main()
