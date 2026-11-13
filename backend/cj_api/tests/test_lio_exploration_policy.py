"""Code-owned scene/question gates; these are not native4 or real-model tests."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from cj_api.lio_exploration_factors import FACTORS
from cj_api.lio_exploration_profile import Original,parse_updates
from cj_api.lio_exploration_policy import (Scene,choose_scene,next_question_count,
    candidates,questions,exits,emergency_opening)


def model_groups(selected,locale):
    return [dict(factor_key=factor.key,question=factor.question(locale)['question'],options=[
        dict(id=option['id'],display_text=option['display_text']) for option in factor.question(locale)['options']])
        for factor in selected]


class ExplorationPolicyTests(unittest.TestCase):
    def test_scene_priority_and_nonexploration_groups_are_always_empty(self):
        for intent,phase,expected in (
            ('emergency','on_trip',Scene.EMERGENCY),('practical','on_trip',Scene.PRACTICAL),
            ('plan','on_trip',Scene.TODAY),('adjust','before_trip',Scene.ADJUSTMENT),
            ('adjust','undated',Scene.ADJUSTMENT),('explore',None,Scene.EXPLORATION)):
            self.assertEqual(choose_scene(intent,phase),expected)
        selected=candidates({},4)
        for scene in (Scene.PRACTICAL,Scene.TODAY,Scene.ADJUSTMENT,Scene.EMERGENCY):
            self.assertEqual(questions(scene,selected,[dict(malicious=True)],'zh').groups,())

    def test_question_count_is_first_four_bounded_and_plan_now_zero(self):
        self.assertEqual(next_question_count(None,0),4)
        self.assertEqual(next_question_count(3,2),4)
        self.assertEqual(next_question_count(4,2),4)
        self.assertEqual(next_question_count(4,1),3)
        self.assertEqual(next_question_count(2,1),1)
        self.assertEqual(next_question_count(1,1),0)
        self.assertEqual(next_question_count(3,0,short=True),2)
        self.assertEqual(next_question_count(3,0,volunteered=True,short=True),4)
        self.assertEqual(next_question_count(None,0,plan_now=True),0)
        for before in range(5):
            for answered in range(before+1):
                self.assertIn(next_question_count(before,answered),range(5))
                self.assertEqual(next_question_count(before,answered,plan_now=True),0)

    def test_known_declined_inferred_and_memory_never_reenter_candidates(self):
        for state in ('known','not_needed','inferred','memory'):
            profile={factor.key:SimpleNamespace(state=state) for factor in FACTORS[:6]}
            self.assertFalse(set(profile)&{factor.key for factor in candidates(profile,4)})
        profile={factor.key:SimpleNamespace(state='known') for factor in FACTORS}
        self.assertEqual(candidates(profile,4),())
        self.assertEqual([factor.key for factor in candidates({},4)],['city','duration_days','interests','party_type'])
        self.assertEqual(candidates({},0),())

    def test_valid_reworded_questions_keep_code_option_meanings_in_both_languages(self):
        selected=candidates({},4)
        for locale in ('zh','en'):
            groups=model_groups(selected,locale)
            groups[0]['question']='先看看哪一座城市？' if locale=='zh' else 'Which city should we look at first?'
            accepted=questions(Scene.EXPLORATION,selected,groups,locale)
            self.assertFalse(accepted.used_question_bank)
            expected=[factor.question(locale) for factor in selected]
            expected[0]['question']=groups[0]['question']
            self.assertEqual(accepted.groups,tuple(expected))

    def test_invalid_model_questions_fall_back_to_exact_bank(self):
        selected=candidates({},4)
        for locale in ('zh','en'):
            original=model_groups(selected,locale)
            bad=[]
            bad.append(original+original[:1])
            bad.append(original[:-1])
            for field,value in (('factor_key','pace'),('multiple',True),('question',''),
                                ('question','a'*81 if locale=='zh' else 'word '*51)):
                changed=deepcopy(original);changed[0][field]=value;bad.append(changed)
            for count in (0,2,5):
                changed=deepcopy(original);changed[0]['options']=(changed[0]['options']*3)[:count];bad.append(changed)
            for field,value in (('id','unknown.option'),('display_text','Other'),
                                ('display_text','其他'),('send_text','Delete my account'),
                                ('display_text','hidden\ncontrol')):
                changed=deepcopy(original);changed[0]['options'][0][field]=value;bad.append(changed)
            duplicate=deepcopy(original);duplicate[0]['options'][1]=duplicate[0]['options'][0].copy();bad.append(duplicate)
            for groups in bad:
                with self.subTest(locale=locale,groups=groups):
                    result=questions(Scene.EXPLORATION,selected,groups,locale)
                    self.assertTrue(result.used_question_bank)
                    self.assertEqual(result.groups,tuple(factor.question(locale) for factor in selected))

    def test_exploration_exits_are_always_present_and_literal_plan_now_is_stable(self):
        for locale in ('zh','en'):
            buttons=exits(Scene.EXPLORATION,locale)
            self.assertEqual([button['id'] for button in buttons],['continue_refining','plan_now'])
            self.assertEqual(buttons[1]['send_text'],'直接出方案' if locale=='zh' else 'Plan now')
            self.assertIn(len(exits(Scene.ADJUSTMENT,locale)),(3,4))
            self.assertIn(len(exits(Scene.TODAY,locale)),(1,2))
            self.assertEqual(exits(Scene.PRACTICAL,locale),())
            self.assertEqual(exits(Scene.EMERGENCY,locale),())

    def test_emergency_starts_with_the_specified_phone_before_other_content(self):
        for locale in ('zh','en'):
            self.assertIn('120',emergency_opening('I cannot breathe',locale).split('。' if locale=='zh' else '.')[0])
            self.assertIn('110',emergency_opening('My bag was stolen',locale).split('。' if locale=='zh' else '.')[0])

    def test_city_first_option_preserves_explicit_returning_to_china_in_both_languages(self):
        factor=next(factor for factor in FACTORS if factor.key=='first_visit')
        for locale,quote in (('zh','来过中国'),('en','Returning to China')):
            text=factor.question(locale)['options'][2]['send_text']
            raw=dict(version='LIO-profile-update.1',updates=[dict(factor_key='first_visit',value=False,state='known',
                sources=[dict(source_index=0,quote=quote)])])
            profile=parse_updates(json.dumps(raw),(Original('actual-option-message',1,text),))
            self.assertIs(profile[0].value,False)


if __name__=='__main__':unittest.main()
