"""Exact #839 copy projection and preserved saved-memory/output boundaries."""
from types import SimpleNamespace
import unittest
from cj_message.lio_context import answer_prompt,self_description,PERSONA
from cj_api.lio_planning_grounding import standalone_question
from cj_message.lio_timeline import TimelineMessage
from cj_api.lio_dialogue_routes import _message


def complete(text):
    return SimpleNamespace(status='completed',text=text,draft_outcome=None,effects=(),budget_exhausted_stage='none')

EXPECTED_IDENTITY_ZH = '我是 Lio，帮来中国旅行的人出主意。从“三天怎么玩”到“今天下雨了还能去哪”，都可以问我。你这次打算去哪儿？'
EXPECTED_IDENTITY_EN = 'I\'m Lio. I help people travelling in China figure things out, from "how should I spend three days here?" to "it\'s raining, where can I go now?" Where are you planning to go?'
EXPECTED_UNKNOWN_ZH = '我们才刚认识，我还不了解你。你点「记住」的内容，之后的对话我都能用上。可以说说你喜欢怎么玩、有没有不吃的东西吗？'
EXPECTED_UNKNOWN_EN = "We've only just met, so I don't know much about you yet. Whatever you tap Remember on, I'll use in future chats. How do you like to travel, and is there anything you don't eat?"
EXPECTED_CAPABILITIES_ZH = """我能帮你：

- **排行程**：告诉我城市、天数和喜好，我排出每天去哪、怎么走，排好的行程会保存到你的行程里。
- **查实用信息**：天气、交通方式、几个地方之间怎么走。拿不准的我会直说，并告诉你去哪确认。
- **随时改计划**：下雨了、累了、想换个地方，跟我说一声，我只改受影响的部分，你定好的安排不动。
- **记住你的习惯**：比如不吃辣、喜欢早起。你点「记住」之后，下次规划就会用上。

订票和付款我做不了，需要你在官方渠道自己完成。想先从哪件事开始？"""
EXPECTED_CAPABILITIES_EN = """Here's how I can help:

- **Plan your days:** tell me the city, how long you're staying and what you like, and I'll map out where to go and how to get around. Your plan is saved to your trip.
- **Practical info:** weather, ways to get around, how to get from one place to another. If I'm not sure about something, I'll say so and tell you where to check.
- **Change plans on the fly:** rain, tired feet, a new idea — just tell me. I'll only change the part that's affected and keep what you've locked in.
- **Learn your style:** say you don't eat spicy food or like early starts. Tap Remember and I'll use it next time I plan.

I can't book or pay for anything — you'll need to do that through official channels. Where would you like to start?"""


class NationalLioIdentity(unittest.TestCase):
    def assert_public_copy(self,answer,expected):
        self.assertEqual(answer,expected)
        for term in ('醒狮','xingshi','lion-dance'):
            self.assertNotIn(term,answer.casefold())

    def test_chinese_identity_uses_approved_copy_despite_wrong_model_intro(self):
        for question in ('你是谁','你是什么？','介绍一下你自己。'):
            with self.subTest(question=question):
                item=TimelineMessage('identity-zh','original-run',1,question,'zh')
                reply=_message(item,complete('我是 Lio，一个武士造型的旅行助手。'))
                self.assert_public_copy(reply['answer'],EXPECTED_IDENTITY_ZH)
        self.assertIn('Use only saved memory',answer_prompt('zh'))
        self.assertIn(EXPECTED_UNKNOWN_ZH,answer_prompt('zh',question='我是谁'))
        self.assertNotIn(EXPECTED_UNKNOWN_ZH,answer_prompt('zh',question='没定日期 没定人数'))
        self.assertTrue(standalone_question('我是谁'))

    def test_english_identity_and_traveler_identity_stay_distinct(self):
        for question in ('Who are you?','What are you.'):
            with self.subTest(question=question):
                item=TimelineMessage('identity-en','original-run',1,question,'en')
                reply=_message(item,complete('I am Lio, a warrior-themed travel assistant.'))
                self.assert_public_copy(reply['answer'],EXPECTED_IDENTITY_EN)
        self.assertIn('Use only saved memory',answer_prompt('en'))
        self.assertIn(EXPECTED_UNKNOWN_EN,answer_prompt('en',question='Who am I?'))
        self.assertNotIn(EXPECTED_UNKNOWN_EN,answer_prompt('en',question='I just want a luxury three-day Beijing itinerary.'))
        self.assertTrue(standalone_question('Who am I?'))
        user=TimelineMessage('user-en','original-run',1,'Who am I?','en')
        text='You have shared a preference for a slower pace.'
        self.assertEqual(_message(user,complete(text))['answer'],text)

    def test_capability_whole_sentence_variants_project_exact_markdown(self):
        variants=(('zh',('你能做什么','你可以做什么？','你会什么。','你有什么能力'),EXPECTED_CAPABILITIES_ZH),
                  ('en',('What can you do?','What do you do.'),EXPECTED_CAPABILITIES_EN))
        for locale,questions,expected in variants:
            for question in questions:
                with self.subTest(locale=locale,question=question):
                    item=TimelineMessage('capability-'+locale,'original-run',1,question,locale)
                    reply=_message(item,complete('I can book and pay for everything.'))
                    self.assert_public_copy(reply['answer'],expected)

    def test_matching_does_not_expand_to_longer_requests(self):
        for question in ('你能做什么来规划成都三日游？','What can you do about this itinerary?','Hello'):
            self.assertIsNone(self_description(question,'en'))

    def test_internal_output_still_fails_before_fixed_projection(self):
        for question in ('你是谁','你能做什么'):
            item=TimelineMessage('blocked','original-run',1,question,'zh')
            blocked=_message(item,complete('The RUN contains run_id.'))
            self.assertEqual((blocked['status'],blocked['answer']),('failed',''))

    def test_persona_greetings_and_existing_constraints_are_preserved(self):
        self.assertTrue(PERSONA.startswith('You are Lio, a travel assistant for visitors to China. '))
        for example in ('你好！准备去哪儿玩？','Hey! Where are you off to?'):
            self.assertIn(example,PERSONA)
        for clause in ('Use only saved memory supplied in the memory data',
                       'Travel preferences do not establish a name, age, nationality or other personal identity.',
                       'Never invent personal facts or answer that the traveler is Lio.',
                       'Never invent prices, opening hours, or transport facts.',
                       'Do not offer to book tickets or take payment.',
                       'Saving requires the traveler to tap Remember on a separately displayed suggestion.'):
            self.assertIn(clause,PERSONA)
        for term in ('醒狮','xingshi','lion-dance'):
            self.assertNotIn(term,PERSONA.casefold())
