"""Frozen-wire controls only; none of these observations is a real baseline."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from contracts.message.check_lio_v4 import merged_answer
from eval.lio_simulated_user.core import InputError, TRACE_VERSION, assess, load_profiles
from eval.lio_simulated_user.native4_observations import presentation_fields


ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = json.loads((ROOT/'contracts/message/lio-exploration-examples.4.json').read_bytes())


def packet(locale='zh'):
    return deepcopy(EXAMPLES[locale])


def normalize(value, **options):
    message = value['messages'][0]
    args = dict(conversation_id=value['conversation_id'], message_id=message['message_id'],
                user_text=message['text'], observation_ref='fixture:native4-original')
    args.update(options)
    return presentation_fields(json.dumps(value, ensure_ascii=False).encode(), **args)


class Native4Observations(unittest.TestCase):
    def test_bilingual_question_spans_use_frozen_projection_and_keep_profile_unavailable(self):
        for locale in ('zh', 'en'):
            with self.subTest(locale=locale):
                value = packet(locale)
                result = normalize(value)
                fields = result['turn_fields']
                message = value['messages'][0]
                for span, group in zip(fields['questions'], message['question_groups']):
                    self.assertEqual(fields['text'][span['start']:span['end']], group['question'])
                    self.assertEqual(span['factor'], group['factor_key'])
                self.assertEqual(result['wire_status'], 'completed')
                self.assertFalse(fields['questions_complete'])
                self.assertIsNone(fields['profile'])
                self.assertFalse(fields['profile_complete'])
                self.assertEqual(fields['profile_evidence'], 'unavailable')
                self.assertNotIn('run_outcome', fields)
                self.assertNotIn('exploration_complete', fields)
                self.assertNotIn('memory_observation', fields)

    def test_unicode_offsets_do_not_select_the_same_words_in_an_earlier_segment(self):
        value = packet()
        message = value['messages'][0]
        question = message['question_groups'][0]['question']
        message['segments'][0]['text'] = '😀 汉字 ' + question.replace('？', '')
        other = deepcopy(message['question_groups'][0])
        other.update(factor_key='pace', question='What pace suits you?')
        for index, option in enumerate(other['options']): option['id'] = 'pace.'+str(index)
        message['question_groups'].append(other)
        message['answer'] = merged_answer(message)
        fields = normalize(value, independent_question_census_complete=True)['turn_fields']
        self.assertTrue(fields['questions_complete'])
        for span, group in zip(fields['questions'], message['question_groups']):
            self.assertEqual(fields['text'][span['start']:span['end']], group['question'])
        self.assertGreater(fields['questions'][0]['start'], fields['text'].index(question[:-1]))
        self.assertNotEqual(fields['questions'][0]['start'], len(message['segments'][0]['text'].encode())+2)

    def test_public_labels_are_never_normalized_factor_truth(self):
        value = packet()
        value['messages'][0]['profile'] = [dict(factor_key='duration_days', display_text='三天 / 3 days', state='known')]
        fields = normalize(value, independent_question_census_complete=True)['turn_fields']
        self.assertIsNone(fields['profile'])
        self.assertFalse(fields['profile_complete'])

    def test_census_requires_independent_coverage_and_no_unannotated_prose_question(self):
        for punctuation in ('?', '？'):
            value = packet()
            message = value['messages'][0]
            message['segments'][0]['text'] = 'Which city'+punctuation
            message['answer'] = merged_answer(message)
            self.assertFalse(normalize(value, independent_question_census_complete=True)['turn_fields']['questions_complete'])
        value = packet()
        value['messages'][0]['question_groups'] = []
        value['messages'][0]['answer'] = merged_answer(value['messages'][0])
        self.assertFalse(normalize(value)['turn_fields']['questions_complete'])

    def test_nonterminal_or_failed_wire_never_proves_a_complete_census(self):
        for status, failure in (('answering', None), ('failed', 'unavailable'), ('completed', 'quota')):
            value = packet()
            value['messages'][0].update(status=status, failure=failure)
            self.assertFalse(normalize(value, independent_question_census_complete=True)['turn_fields']['questions_complete'])

    def test_original_cid_mid_and_text_must_match(self):
        for changes in (dict(conversation_id='lio-dialogue-'+'b'*32), dict(message_id='other-mid'), dict(user_text='different original')):
            with self.subTest(changes=changes), self.assertRaises(InputError): normalize(packet(), **changes)
        value = packet()
        value['conversation_id'] = None
        with self.assertRaises(InputError): normalize(value)

    def test_malformed_or_relabelled_presentation_is_refused(self):
        changes = [lambda v: v.update(version='LIO-timeline.3'),
                   lambda v: v['messages'][0].update(answer='a different answer'),
                   lambda v: v['messages'].append(deepcopy(v['messages'][0])),
                   lambda v: v['messages'][0]['profile'].append(dict(factor_key='pace', display_text='已知', state='known', profile_complete=True))]
        for change in changes:
            value = packet(); change(value)
            with self.assertRaises(InputError): normalize(value)

    def test_complete_body_is_required(self):
        value = packet()
        message = value['messages'][0]
        for key in ('segments', 'question_groups', 'notices', 'exits'): message[key] = []
        message['answer'] = ''
        with self.assertRaises(InputError): normalize(value)

    def test_strict_bounded_utf8_json_and_explicit_observer_reference(self):
        value = packet(); raw = json.dumps(value).encode()
        args = dict(conversation_id=value['conversation_id'], message_id=value['messages'][0]['message_id'],
                    user_text=value['messages'][0]['text'], observation_ref='fixture:original')
        for invalid in (b'', b'x'*1_000_001, raw.decode(), raw.decode().encode('utf-16'),
                        b'{"version":"LIO-timeline.4",'+raw[1:], raw[:-1]+b',"unexpected":NaN}'):
            with self.subTest(kind=type(invalid)), self.assertRaises(InputError): presentation_fields(invalid, **args)
        for changes in (dict(observation_ref=''), dict(independent_question_census_complete=1)):
            changed = dict(args, **changes)
            with self.assertRaises(InputError): presentation_fields(raw, **changed)

    def test_unchanged_scorer_keeps_g3_unknown_without_native_accepted_context(self):
        data, digest = load_profiles(); profile = data['profiles'][0]
        value = packet(); message = value['messages'][0]; message['text'] = profile['opening']
        group = message['question_groups'][0]
        group.update(factor_key='lodging_tier', question='想住哪类酒店？')
        for index, option in enumerate(group['options']): option['id'] = 'lodging_tier.'+str(index)
        message['answer'] = merged_answer(message)
        for independent in (False, True):
            fields = normalize(value, independent_question_census_complete=independent)['turn_fields']
            fields.update(speaker='assistant', exploration_complete=True, run_outcome='completed')
            trace = dict(version=TRACE_VERSION, dataset_sha256=digest, profile_id=profile['id'], attempt=1,
                candidate='fixture:not-real', evidence_layer='L0', outcome='completed',
                memory_observation=dict(origin='fixture', complete=True, text='', facts=[], ref='fixture:empty'),
                turns=[dict(speaker='user', text=profile['opening'], disclosures=profile['initial_disclosures']), fields])
            result = assess(profile, trace)
            self.assertEqual(result['G2']['status'], 'PASS' if independent else 'UNKNOWN')
            self.assertEqual(result['G3']['status'], 'UNKNOWN')
            self.assertEqual(result['G3']['matched'], 0)
            self.assertEqual(len(result['G3']['unavailable_factors']), 14)


if __name__ == '__main__': unittest.main()
