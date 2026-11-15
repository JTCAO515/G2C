"""Offline native4 history snapshot controls; no storage or undo authority."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator,ValidationError
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from contracts.message.check_lio_trip_history_v4 import SCHEMA,validate
EXAMPLES=json.loads((ROOT/'contracts/message/lio-exploration-examples.4.json').read_bytes())


def fixture():
    current=deepcopy(EXAMPLES['structured4_undated']['messages'][0]['trip'])
    prior=deepcopy(EXAMPLES['legacy_card2']['messages'][0]['trip'])
    current.update(trip_version=3)
    prior.update(trip_id=current['trip_id'],trip_version=2)
    target=dict(trip_id=current['trip_id'],expected_version=3,original_hash=current['content_sha256'],
        content_version=current['content_version'],restore_version=2,restore_hash=prior['content_sha256'],
        restore_content_version=prior['content_version'])
    return dict(version='LIO-trip-history.4',conversation_id='lio-dialogue-'+'a'*32,
        current=current,history=[prior],undo_target=target,next_before='2')


class HistoryContract(unittest.TestCase):
    def test_additive_schema_and_mixed_original_content_preserve_exact_identity(self):
        Draft202012Validator.check_schema(SCHEMA)
        value=fixture();before=deepcopy(value)
        validate(value)
        self.assertEqual(value,before)
        self.assertIsNone(value['history'][0]['calendar'])
        self.assertEqual(value['current']['calendar']['state'],'undated')
        self.assertEqual([day['day_index']for day in value['current']['days']],[1,2,3])
        self.assertEqual(len(value['current']['days'][1]['items']),0)

    def test_current_and_previous_snapshot_hashes_are_both_bound(self):
        for field,changed in (('trip_id','another-trip'),('expected_version',4),('original_hash','0'*64),
                              ('content_version','structured.3'),('restore_version',1),
                              ('restore_hash','0'*64),('restore_content_version','structured.4')):
            value=fixture();value['undo_target'][field]=changed
            with self.subTest(field=field),self.assertRaises(ValueError):validate(value)

    def test_no_current_or_no_previous_cannot_supply_an_undo_target(self):
        for change in (lambda v:v.update(current=None),lambda v:v.update(history=[])):
            value=fixture();change(value)
            with self.assertRaises(ValueError):validate(value)
        value=fixture();value.update(current=None,undo_target=None)
        validate(value)
        value.update(history=[],next_before=None)
        validate(value)

    def test_history_is_one_trip_unique_descending_and_older_than_current(self):
        value=fixture();prior=value['history'][0]
        for rows in ([prior,deepcopy(prior)],
                     [dict(prior,trip_version=1),prior],
                     [dict(prior,trip_version=3)],
                     [dict(prior,trip_id='other-trip')]):
            changed=deepcopy(value);changed['history']=rows
            with self.subTest(rows=rows),self.assertRaises(ValueError):validate(changed)
        value=fixture();value.update(current=None,undo_target=None)
        value['history'].append(dict(value['history'][0],trip_id='foreign-trip',trip_version=1))
        with self.assertRaises(ValueError):validate(value)

    def test_cursor_is_exact_last_returned_version_and_has_no_control_suffix(self):
        for cursor in ('3','0','2\n','9223372036854775808'):
            value=fixture();value['next_before']=cursor
            with self.subTest(cursor=cursor),self.assertRaises((ValueError,ValidationError)):validate(value)
        value=fixture();value.update(history=[],undo_target=None)
        with self.assertRaises(ValueError):validate(value)

    def test_rich_cards_keep_frozen_calendar_and_date_check_semantics(self):
        for change in (lambda c:c['days'][1].update(day_index=3),
                       lambda c:c['date_checks'][0].update(state='clear'),
                       lambda c:c['date_checks'][0].update(day_indices=[4])):
            value=fixture();change(value['current'])
            with self.assertRaises((ValueError,ValidationError)):validate(value)
        value=fixture();dated=deepcopy(EXAMPLES['structured4_dated']['messages'][0]['trip'])
        dated.update(trip_id=value['current']['trip_id'],trip_version=3)
        value['current']=dated;value['undo_target']['original_hash']=dated['content_sha256']
        validate(value)
        value['current']['days'][1]['date']='2026-12-09'
        with self.assertRaises(ValueError):validate(value)

    def test_action_is_data_only_and_exactly_one_immediate_predecessor(self):
        history=fixture()
        action=dict(version='LIO-trip-undo.4',action_id='same-original-action',
                    conversation_id=history['conversation_id'],target=history['undo_target'])
        validate(action)
        for change in (dict(version='LIO-trip-undo.3'),dict(action_id='same-original-action\n'),
                       dict(conversation_id=history['conversation_id']+'\n'),dict(permission=True)):
            with self.subTest(change=change),self.assertRaises(ValidationError):validate(dict(action,**change))
        action['target']=dict(action['target'],restore_version=1)
        with self.assertRaises(ValueError):validate(action)

    def test_unknown_versions_and_fields_and_boolean_integers_fail(self):
        for change in (dict(version='LIO-trip-history.3'),dict(permission=True)):
            with self.assertRaises(ValidationError):validate(dict(fixture(),**change))
        for field in ('expected_version','restore_version'):
            value=fixture();value['undo_target'][field]=True
            with self.assertRaises(ValidationError):validate(value)
        receipt=dict(version='LIO-trip-undo-receipt.4',action_id='same-original-action',
                     conversation_id=fixture()['conversation_id'],committed=False)
        validate(receipt)
        with self.assertRaises(ValidationError):validate(dict(receipt,committed='unknown'))


if __name__=='__main__':unittest.main()
