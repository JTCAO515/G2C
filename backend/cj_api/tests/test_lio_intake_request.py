"""Request controls bind first direct commands; they never extract field values."""
from types import SimpleNamespace
import unittest
from jsonschema import Draft202012Validator,ValidationError
from cj_agent.lio_intake_request_schema import response_format,response_format_sha256
from cj_api.local_lio_national import request_intent
from lio_flat_fixture import facts_fixture
from test_lio_intake_start_schema import sample


class RequestContract(unittest.TestCase):
    def mode(self,text,*,previous=None):return request_intent(text,(SimpleNamespace(text=text),),previous)

    def test_unqualified_commands_cover_six_cities_both_languages(self):
        for zh,en in (('上海','Shanghai'),('成都','Chengdu'),('西安',"Xi'an"),('桂林','Guilin'),('广州','Guangzhou'),('杭州','Hangzhou')):
            for text in ('去'+zh+'玩三天','Plan a three-day trip to '+en+'.'):
                with self.subTest(text=text):self.assertEqual(self.mode(text),'plan')

    def test_real_consultation_refusal_and_discussion_are_not_constrained(self):
        for text in ('去哪里玩三天','去哪个城市玩三天','去成都玩三天怎么样？','上海住酒店还是民宿？',
                '去成都玩三天，不要保存','想去杭州玩两天，先聊聊不保存。','日期还没定，先讨论。',
                'Plan a trip to Shanghai but do not save it.','Plan a hypothetical trip to Chengdu.',
                'Should I plan a trip to Chengdu?','Plan a trip to China means what?',
                'Compare a trip to Shanghai with Chengdu.','Who are you?','只有我一人','从明天开始'):
            with self.subTest(text=text):self.assertIsNone(self.mode(text))
        self.assertIsNone(self.mode('去成都玩三天',previous={'authority':'none','status':'discussion'}))
        self.assertIsNone(request_intent('去成都玩三天',(SimpleNamespace(text='先聊'),SimpleNamespace(text='去成都玩三天')),None))

    def test_constraint_is_in_actual_schema_not_a_response_repair(self):
        old,turns=sample('zh',True);data=facts_fixture(old)
        ordinary=response_format(2,None);bound=response_format(2,'plan')
        self.assertNotEqual(response_format_sha256(2,None),response_format_sha256(2,'plan'))
        self.assertEqual(bound['json_schema']['schema']['properties']['intent']['const'],'plan')
        self.assertIs(bound['json_schema']['schema']['properties']['needs_tools']['const'],False)
        Draft202012Validator(bound['json_schema']['schema']).validate(data)
        data['intent']='consult';data['needs_tools']=True
        Draft202012Validator(ordinary['json_schema']['schema']).validate(data)
        with self.assertRaises(ValidationError):Draft202012Validator(bound['json_schema']['schema']).validate(data)
