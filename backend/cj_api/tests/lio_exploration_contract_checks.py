"""Offline v4 consumer contract checks; not model, server-admission or device proof."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from contracts.message.check_lio_v4 import SCHEMA, LEGACY, validate, merged_answer, joint_reply
EXAMPLES = json.loads((ROOT/'contracts/message/lio-exploration-examples.4.json').read_bytes())


class ExplorationContract(unittest.TestCase):
    def test_schema_and_bilingual_progress_examples(self):
        Draft202012Validator.check_schema(SCHEMA)
        for name, value in EXAMPLES.items():
            with self.subTest(name=name):validate(value)

    def test_version_is_additive_and_old_envelope_unchanged(self):
        old = dict(version='LIO-message.3',message_id='original',text='Plan Chengdu',locale='en')
        prior = Draft202012Validator({'$defs':LEGACY['$defs'],'$ref':'#/$defs/LioMessage3'})
        prior.validate(old)
        with self.assertRaises(ValidationError):validate(old)
        new = dict(old,version='LIO-message.4')
        validate(new)
        with self.assertRaises(ValidationError):prior.validate(new)
        for fields in ({'new_conversation':False},{'new_conversation':True,'conversation_id':'lio-dialogue-'+'a'*32},{'selected_options':['city.beijing']},{'calendar':True}):
            with self.subTest(fields=fields),self.assertRaises(ValidationError):validate(dict(new,**fields))

    def test_unknown_enums_and_fifth_option_reject(self):
        for path, change in (('purpose','internal_tool'),('factor_key','nationality'),('options',5)):
            value=deepcopy(EXAMPLES['en']);m=value['messages'][0]
            if path=='purpose':m['segments'][0][path]=change
            elif path=='factor_key':m['question_groups'][0][path]=change
            else:m['question_groups'][0]['options']+=deepcopy(m['question_groups'][0]['options'][:2])
            with self.subTest(path=path),self.assertRaises(ValidationError):validate(value)

    def test_stable_identifiers_are_unique_and_scoped(self):
        value=deepcopy(EXAMPLES['en']);m=value['messages'][0]
        m['question_groups'][0]['options'][1]['id']=m['question_groups'][0]['options'][0]['id']
        with self.assertRaisesRegex(ValueError,'duplicate'):validate(value)
        value=deepcopy(EXAMPLES['en']);value['messages'][0]['question_groups'][0]['options'][0]['id']='pace.relaxed'
        with self.assertRaisesRegex(ValueError,'scoped'):validate(value)
        value=deepcopy(EXAMPLES['en']);m=value['messages'][0];m['profile']=[dict(factor_key='pace',display_text='Relaxed',state='known'),dict(factor_key='pace',display_text='Moderate',state='memory')]
        with self.assertRaisesRegex(ValueError,'duplicate'):validate(value)

    def test_progress_is_closed_and_never_invents_duration(self):
        for progress in (dict(kind='tool_debug',text='private'),dict(kind='planning_started',text='Starting'),dict(kind='planning_started',text='Starting',duration_days=True),dict(kind='planning_started',text='Starting',duration_days=0),dict(kind='waiting',text='Wait',duration_days=3)):
            value=deepcopy(EXAMPLES['waiting']);value['messages'][0]['progress']=progress
            with self.subTest(progress=progress),self.assertRaises(ValidationError):validate(value)
        value=deepcopy(EXAMPLES['planning_started']);value['messages'][0]['status']='completed'
        with self.assertRaisesRegex(ValueError,'terminal'):validate(value)

    def test_joint_choices_follow_wire_order_allow_partial_and_emit_one_text(self):
        groups=deepcopy(EXAMPLES['en']['messages'][0]['question_groups'])
        self.assertEqual(joint_reply(groups,{'interests':['interests.nature','interests.history']}),'Interests: History\nInterests: Nature')
        self.assertEqual(joint_reply(groups,{}),'')
        self.assertEqual(joint_reply(groups,{'interests':['interests.food']}),'Interests: Food')
        for chosen in ({'interests':['invented']},{'other':['x']},{'interests':['interests.food','interests.food']}):
            with self.subTest(chosen=chosen),self.assertRaises(ValueError):joint_reply(groups,chosen)
        groups[0]['multiple']=False
        with self.assertRaises(ValueError):joint_reply(groups,{'interests':['interests.food','interests.nature']})

    def test_option_and_exit_text_cannot_inject_joint_reply_lines(self):
        for section in ('option','exit'):
            for text in ('History\n','History\r','History\r\n','History\nFood',
                         'History\u0085Food','History\u2028Food','History\u2029Food','   ','\t'):
                value=deepcopy(EXAMPLES['en']);message=value['messages'][0]
                target=(message['question_groups'][0]['options'][0] if section=='option'
                        else message['exits'][0])
                target['send_text']=text
                with self.subTest(section=section,text=repr(text)),self.assertRaises(ValidationError):validate(value)

    def test_plain_text_projection_has_one_order_and_is_not_a_second_bubble(self):
        for locale in ('zh','en'):
            message=EXAMPLES[locale]['messages'][0]
            self.assertEqual(message['answer'],merged_answer(message))
            value=deepcopy(EXAMPLES[locale]);value['messages'][0]['answer']='wrong projection'
            with self.assertRaisesRegex(ValueError,'projection'):validate(value)


if __name__=='__main__':unittest.main()
