"""Code-owned scene/question gates; these are not native4 or real-model tests."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from cj_api.lio_exploration_factors import FACTORS
from cj_api.lio_exploration_profile import Original,parse_updates
from cj_api.lio_exploration_policy import (Scene,choose_scene,next_question_count,
    candidates,questions,exits,emergency_opening)
from cj_api.local_lio_exploration import _bubbles


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

    def test_questions_apply_existing_display_redlines_and_option_meanings(self):
        selected=candidates({},4)
        for bad in ('message_id是什么？','我已记住你的偏好，接下来呢？'):
            proposed=model_groups(selected,'zh');proposed[0]['question']=bad
            result=questions(Scene.EXPLORATION,selected,proposed,'zh')
            self.assertTrue(result.used_question_bank)
            self.assertEqual(result.groups,tuple(factor.question('zh')for factor in selected))
        proposed=model_groups(selected,'zh')
        proposed[0]['options'][0]['display_text']='上海'
        self.assertTrue(questions(Scene.EXPLORATION,selected,proposed,'zh').used_question_bank)

    def test_context_option_variant_has_code_bound_display_and_matching_send_text(self):
        selected=(next(factor for factor in FACTORS if factor.key=='interests'),)
        proposed=model_groups(selected,'zh')
        proposed[0]['options'][2]['display_text']='熊猫与自然'
        variants={'interests.nature':{'熊猫与自然':'兴趣: 熊猫与自然'}}
        self.assertTrue(questions(Scene.EXPLORATION,selected,proposed,'zh').used_question_bank)
        result=questions(Scene.EXPLORATION,selected,proposed,'zh',option_variants=variants)
        self.assertFalse(result.used_question_bank)
        self.assertEqual(result.groups[0]['options'][2]['send_text'],'兴趣: 熊猫与自然')

    def test_every_nonemergency_bubble_respects_the_language_tier_without_losing_content(self):
        chinese='细化旅行安排'*40
        parts=_bubbles(chinese,'zh')
        self.assertEqual(''.join(parts),chinese)
        self.assertTrue(all(len(part)<=80 for part in parts))
        english=' '.join('word'+str(index)for index in range(130))
        parts=_bubbles(english,'en')
        self.assertEqual(' '.join(parts),english)
        self.assertTrue(all(len(part.split())<=50 for part in parts))


if __name__=='__main__':unittest.main()
