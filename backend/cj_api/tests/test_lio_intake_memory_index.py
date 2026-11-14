"""#994: Memory user slots shift model source indices; capability wording; diagnostics."""
from copy import deepcopy
import json
import unittest
from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.lio_flow_intake import parse_flow,rebind_sources
from cj_api.lio_national_intake import diagnostic_code
from cj_api.local_lio_national import META_QUESTION
from cj_message.lio_context import self_description,CAPABILITIES_ZH,CAPABILITIES_EN
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow,original


def wire(text,*,days=3,quote=None,index=0,reply='想去哪个城市？',questions=('city',)):
    value=flow(text,city=None,days=days,intent='consult',reply=reply,questions=questions,index=index)
    value['version']='LIO-planning-intake.8'
    if days is not None:
        value['field_sources']=[dict(field='duration_days',source_index=index,quote=quote or text)]
        value['planning_request_index']=index
    else:value['planning_request_index']=None
    return value


def parse(value,turns,**kwargs):
    refs=tuple(dict(message_id='m'+str(n))for n in range(len(turns)-1))
    return parse_flow(json.dumps(value,ensure_ascii=False),turns,refs,'current',None,schema=OptionalIntake,**kwargs)


class MemoryIndexChecks(unittest.TestCase):
    def test_memory_counted_index_is_rebound_to_the_original_quote(self):
        # Model input: [Memory, 三天怎么玩]; the indexed originals are only [三天怎么玩].
        for text,quote in (('三天怎么玩','三天'),('3 days, what should I do?','3 days')):
            with self.subTest(text=text):
                value=wire(text,quote=quote)
                value['field_sources'][0]['source_index']=1
                with self.assertRaises(InvalidInput) as rejected:parse(deepcopy(value),(original(text),))
                self.assertEqual(diagnostic_code(rejected.exception),'field_source_binding')
                intake,_,facts=parse(value,(original(text),),memory_offset=1)
                self.assertEqual(intake.duration_days,3)
                self.assertEqual(intake.sources['duration_days'],[dict(source_index=0,quote=quote)])
                self.assertEqual(facts['duration_days']['sources'],[dict(message_id='current',quote=quote)])

    def test_memory_counted_bare_indices_shift_only_by_the_memory_offset(self):
        turns=(original('你是谁'),original('三天怎么玩'))
        value=wire('三天怎么玩',quote='三天',index=1)
        value['current_source_index']=2;value['planning_request_index']=2;value['field_sources'][0]['source_index']=2
        with self.assertRaises(InvalidInput):parse(deepcopy(value),turns)
        intake,_,facts=parse(value,turns,memory_offset=1)
        self.assertEqual(intake.planning_request_index,1)
        self.assertEqual(intake.sources['duration_days'][0]['source_index'],1)
        self.assertEqual(facts['duration_days']['sources'],[dict(message_id='current',quote='三天')])

    def test_memory_or_invented_quote_still_never_becomes_a_source(self):
        value=wire('三天怎么玩',quote='三天')
        value['party_size']=2
        value['field_sources'].append(dict(field='party_size',source_index=0,quote='两个人'))
        for offset in (0,1):
            with self.subTest(offset=offset),self.assertRaises(InvalidInput) as rejected:
                parse(deepcopy(value),(original('三天怎么玩'),),memory_offset=offset)
            self.assertEqual(diagnostic_code(rejected.exception),'field_source_binding')

    def test_only_the_exact_memory_shift_is_corrected(self):
        turns=(original('想去成都'),original('玩三天'),original('三天够吗'))
        def refs():return {'kept':dict(source_index=2,quote='三天'),'shifted':dict(source_index=2,quote='玩三天'),
                           'other_offset':dict(source_index=0,quote='三天'),'absent':dict(source_index=1,quote='不存在'),
                           'nested':[dict(detail_refs=[dict(source_index=1,quote='想去成都')])]}
        value=refs();self.assertEqual(rebind_sources(value,turns),0);self.assertEqual(value,refs())
        value=refs();self.assertEqual(rebind_sources(value,turns,memory_offset=1),2)
        self.assertEqual([value[k]['source_index']for k in ('kept','shifted','other_offset','absent')],[2,1,0,1])
        self.assertEqual(value['nested'][0]['detail_refs'][0]['source_index'],0)

    def test_schema_failure_has_a_specific_code_and_field_detail(self):
        value=wire('你能做啥',days=None,reply='我可以帮你规划行程。',questions=())
        value['question_fields']=['capabilities']
        with self.assertRaises(InvalidInput) as rejected:parse(value,(original('你能做啥'),))
        self.assertEqual(diagnostic_code(rejected.exception),'flow_schema')
        self.assertEqual(rejected.exception.detail,'question_fields:literal_error')
        self.assertNotIn('capabilities',rejected.exception.detail)


class CapabilityQuestionChecks(unittest.TestCase):
    ASKED=('你能做啥','你能做啥？','你能做什么','你能干啥','你会干嘛','你可以帮我做什么','你可以帮我干嘛',
           '你能帮什么忙','你都会些什么','你有啥功能','你有什么能力','那你能做啥呢','请问你可以做什么？',
           'what can you do','What can you help me with?','how can you help me','what could you do')
    NOT_ASKED=('三天怎么玩','你能帮我规划成都三天吗','你会做饭吗','你能推荐成都美食吗','what can you do in Chengdu',
               '去成都玩三天','你能做啥行程')

    def test_capability_wordings_use_the_capability_answer(self):
        for text in self.ASKED:
            with self.subTest(text=text):
                self.assertIn(self_description(text,'zh'),(CAPABILITIES_ZH,))
                self.assertEqual(self_description(text,'en'),CAPABILITIES_EN)
                self.assertIsNotNone(META_QUESTION.fullmatch(text))

    def test_planning_and_ordinary_questions_are_not_capability_questions(self):
        for text in self.NOT_ASKED:
            with self.subTest(text=text):
                self.assertIsNone(self_description(text,'zh'))
                self.assertIsNone(META_QUESTION.fullmatch(text))
        self.assertIsNotNone(META_QUESTION.fullmatch('我是谁'))


if __name__=='__main__':unittest.main(verbosity=2)
