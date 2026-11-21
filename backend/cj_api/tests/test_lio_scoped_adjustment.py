"""Only a supported original request can select one unlocked native4 change."""
from copy import deepcopy
from dataclasses import replace
from datetime import date,datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from cj_api.lio_exploration_policy import Scene, exits
from cj_agent.draft import DraftRejected
from cj_message.lio_exploration_schema import RESPONSE
from cj_message.domain import Receipt, Stored
from cj_run.core import Binding
from cj_trip.domain import Trip, packed
from cj_trip.lio_history import TripHead


ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']
DAY = date(2026, 11, 21)


def trip(case='matched'):
    return Trip('existing-rich-trip', 3, packed(CASES[case]['content']))


class ScopedAdjustment(unittest.TestCase):
    def test_button_and_freeform_issue_the_same_single_current_scope(self):
        from cj_api.lio_exploration_policy import select_adjustment
        current = trip()
        for locale, lighter, food in (('zh', '请安排得轻松一点。', '能多安排点美食吗？'),
                                      ('en', 'Please make the trip more relaxed.', 'Could you add more local food?')):
            buttons = {value['id']: value['send_text'] for value in exits(Scene.ADJUSTMENT, locale)}
            for action, phrasing, operation in (('less_walking', lighter, 'remove'),
                                                ('more_food', food, 'replace')):
                with self.subTest(locale=locale, action=action):
                    selected = select_adjustment(current, buttons[action], DAY)
                    self.assertIsNotNone(selected)
                    self.assertEqual(selected, select_adjustment(current, phrasing, DAY))
                    self.assertEqual(selected.scope.head, TripHead.from_trip(current))
                    self.assertEqual(selected.scope.operation, operation)
                    row, = (item for item in json.loads(current.content)['items']
                            if item['id'] == selected.scope.item_id)
                    self.assertEqual(row['fixed'], dict(state='known', value=False))
                    self.assertIn(row['kind'], ('sight', 'free_time'))

    def test_explicit_target_and_protected_or_unissued_sources(self):
        from cj_api.lio_exploration_policy import select_adjustment
        for locale, removal, replacement in (
                ('zh', '去掉「演示地点1 / demonstration stop 1」。',
                 '把「演示地点1 / demonstration stop 1」换成「颐和园」。'),
                ('en', 'Remove “演示地点1 / demonstration stop 1”.',
                 'Replace “演示地点1 / demonstration stop 1” with Summer Palace.')):
            with self.subTest(locale=locale):
                for text, op in ((removal, 'remove'), (replacement, 'replace')):
                    selection = select_adjustment(trip(), text, DAY)
                    self.assertEqual((selection.scope.item_id, selection.scope.operation), ('item-1', op))
                    self.assertIsNone(select_adjustment(trip('protected_fixed'), text, DAY))

    def test_denial_mixed_request_duplicate_name_and_started_trip_do_not_select(self):
        from cj_api.lio_exploration_policy import select_adjustment
        for locale, text in (('zh', '再轻松点，但先别保存。'), ('zh', '如果可以，再轻松点。'),
                             ('en', 'Make it more relaxed, but do not edit it.'),
                             ('en', 'Translate “Add more local food”.'),
                             ('en', 'Start each day later.')):
            self.assertIsNone(select_adjustment(trip(), text, DAY))
        duplicate = deepcopy(CASES['matched']['content'])
        duplicate['items'][2]['text'] = duplicate['items'][0]['text']
        duplicated = Trip('same-id', 3, packed(duplicate))
        self.assertIsNone(select_adjustment(duplicated, 'Remove “演示地点1 / demonstration stop 1”.', DAY))
        self.assertIsNone(select_adjustment(trip('dated'), 'Make it more relaxed', date(2026, 12, 20)))

    def test_completed_dated_trip_does_not_present_pretrip_controls(self):
        from cj_api.lio_exploration_policy import choose_scene
        from cj_api.local_lio_exploration import ExplorationPlanning
        class CompletedTripClock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime(2026,12,20,tzinfo=tz)
        host=SimpleNamespace(current=lambda _:SimpleNamespace(trip=trip('dated')))
        with patch('cj_api.local_lio_exploration.datetime',CompletedTripClock):
            phase=ExplorationPlanning._phase(host,None)
        self.assertEqual(phase,'after_trip')
        self.assertIsNot(choose_scene('adjust',phase),Scene.ADJUSTMENT)

    def test_older_saved_content_leaves_the_original_edit_path_available(self):
        from cj_api.lio_exploration_policy import select_adjustment
        legacy=Trip('legacy-trip',1,packed({'title':'Older plan','days':[]}))
        self.assertIsNone(select_adjustment(legacy,'Make it more relaxed',DAY))

    def test_named_questions_and_conditional_text_do_not_issue_write_scope(self):
        from cj_api.lio_exploration_policy import select_adjustment
        current=trip()
        for text in ('Remove “演示地点1 / demonstration stop 1”?',
                     '把「演示地点1 / demonstration stop 1」换成「颐和园」？'):
            self.assertIsNone(select_adjustment(current,text,DAY))
        self.assertIsNotNone(select_adjustment(current,
            'Could you replace “演示地点1 / demonstration stop 1” with Summer Palace?',DAY))
        document=json.loads(current.content)
        document['items'][0]['text']='Lunch only if open'
        current=Trip(current.trip_id,current.version,packed(document))
        self.assertIsNone(select_adjustment(current,'Remove Lunch only if open.',DAY))
        self.assertIsNotNone(select_adjustment(current,'Remove “Lunch only if open”.',DAY))

    def test_pending_approval_in_an_unquoted_name_does_not_issue_scope(self):
        from cj_api.lio_exploration_policy import select_adjustment
        for name,command,literal in (
                ('午餐确认后再改','去掉午餐确认后再改。','去掉「午餐确认后再改」。'),
                ('Lunch after I approve','Remove Lunch after I approve.','Remove “Lunch after I approve”.')):
            with self.subTest(command=command):
                doc=deepcopy(CASES['matched']['content'])
                doc['items'][0]['text']=name
                current=Trip('proposed-trip',4,packed(doc))
                self.assertIsNone(select_adjustment(current,command,DAY))
                self.assertEqual(select_adjustment(current,literal,DAY).scope.item_id,doc['items'][0]['id'])
        self.assertIsNone(select_adjustment(trip(),'把「演示地点1 / demonstration stop 1」换成甜品确认后再改。',DAY))

    def test_authority_binds_the_exact_message_run_trip_head_and_operation(self):
        from cj_api.lio_exploration_policy import AdjustmentAuthorization, select_adjustment
        binding=Binding('owner','chat','generation','message','run',9)
        stored=Stored(b'{"text":"Make it more relaxed"}',Receipt('message','chat','generation',9,'run','a'*64))
        selected=select_adjustment(trip(),'Make it more relaxed',DAY)
        authority=AdjustmentAuthorization(binding,stored,DAY,selected)
        self.assertTrue(authority.matches(binding,stored,selected.scope))
        for changed in (replace(binding,scope='different-owner'),replace(binding,run_id='other-run'),
                        replace(binding,conversation_id='other-chat')):
            self.assertFalse(authority.matches(changed,stored,selected.scope))
        self.assertFalse(authority.matches(binding,replace(stored,raw=b'{"text":"Do not edit"}'),selected.scope))
        self.assertFalse(authority.matches(binding,stored,replace(selected.scope,operation='replace')))
        self.assertFalse(authority.matches(binding,stored,replace(selected.scope,head=replace(selected.scope.head,version=4))))

    def test_candidate_changes_one_slot_and_only_reuses_untouched_route_sources(self):
        from cj_api.lio_exploration_policy import adjustment_document, select_adjustment
        from cj_trip.structured_v4 import validate_document
        current=trip()
        before=json.loads(current.content)
        incoming={leg['to_item_id'] for leg in before['legs']}
        outgoing={leg['from_item_id'] for leg in before['legs']}
        original=next(item for item in before['items'] if item['id'] in incoming & outgoing)
        name=original['text']
        affected=original['id']
        retained={(leg['from_item_id'],leg['to_item_id']):leg for leg in before['legs']
                  if affected not in (leg['from_item_id'],leg['to_item_id'])}
        for input in (f'Remove “{name}”.',f'Replace “{name}” with Summer Palace.'):
            with self.subTest(input=input):
                selection=select_adjustment(current,input,DAY)
                result=adjustment_document(current,selection,replacement=selection.replacement)
                validate_document(result)
                items={item['id']:item for item in result['items']}
                for row in before['items']:
                    if row['id']!=affected:self.assertEqual(items[row['id']],row)
                if selection.scope.operation=='replace':
                    new=items[affected]
                    self.assertEqual(new['schedule'],original['schedule'])
                    self.assertEqual(new['place']['state'],'unconfirmed')
                    self.assertIsNone(new['place']['source'])
                    self.assertEqual(new['text'],'Summer Palace')
                else:
                    self.assertNotIn(affected,items)
                for leg in result['legs']:
                    pair=(leg['from_item_id'],leg['to_item_id'])
                    if pair in retained:
                        self.assertEqual(leg,retained[pair])
                    else:
                        self.assertEqual(leg['state'],'unconfirmed')
                        self.assertIsNone(leg['source'])
                self.assertEqual(result['calendar'],before['calendar'])

    def test_food_wording_cannot_persist_booking_or_verification_claims(self):
        from cj_api.local_lio_exploration import _food_suggestion
        for locale,good,bad in (('zh','当地小吃体验','已预订当地小吃体验'),
                                ('en','Local snack tasting','Confirmed local snack booking')):
            def suggest(name):
                host=SimpleNamespace(_model=lambda *args:json.dumps(dict(version=RESPONSE,body=name,groups=[])))
                return _food_suggestion(host,None,None,None,locale,{'text':'Suggested sight'})
            with self.subTest(locale=locale):
                self.assertEqual(suggest(good),good)
                with self.assertRaises(DraftRejected):suggest(bad)
