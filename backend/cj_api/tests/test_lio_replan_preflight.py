"""Incompatible retained content is detected before a new NEEDS/model effect."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cj_api.local_lio_planning import LioPlanSave
from cj_message.lio_plan_needs import lio_needs_id
from cj_message.needs_binding import needs_scope_for
from cj_trip.structured_v2 import validate_document as validate_document2


def known(value):return dict(state='known',value=value)


def fixture():
    def endpoint(clock):return dict(date=known('2026-11-11'),time=known(clock),timezone=known('Asia/Shanghai'),utc_offset=dict(state='unknown'))
    document=dict(content_version='structured.2',title='Synthetic saved trip',sources=[],items=[dict(
        id='meeting',text='Synthetic fixed meetup',schedule=dict(start=endpoint('09:00'),end=endpoint('10:00')),
        fixed=known(True),source_category='user_provided',verification='pending',evidence=[],source_refs=[])])
    validate_document2(document)
    def bound(day,clock):return dict(date=known(day),time=known(clock),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
    fields=dict(arrival=bound('2026-11-11','08:00'),departure=bound('2026-11-13','22:00'),destination_timezone=known('Asia/Shanghai'))
    return document,fields


class ReplanPreflight(unittest.TestCase):
    def test_current_accepted_head_same_window_and_no_trip(self):
        document,fields=fixture();repository=object()
        save=LioPlanSave(None,SimpleNamespace(repository=repository),None)
        binding=SimpleNamespace(scope='owner',conversation_id='chat')
        current=SimpleNamespace(trip=SimpleNamespace(content=json.dumps(document).encode()))
        with patch('cj_trip.planning_context.read_current',return_value=current)as read:
            self.assertFalse(save.planning_window_conflict(binding,fields))
            read.assert_called_once_with(repository,needs_scope_for('owner'),lio_needs_id('owner','chat'))
        with patch('cj_trip.planning_context.read_current',return_value=None):
            self.assertFalse(save.planning_window_conflict(binding,fields))

    def test_retained_dates_and_times_are_not_moved_to_fit_new_bounds(self):
        document,fields=fixture();before=deepcopy(document)
        save=LioPlanSave(None,SimpleNamespace(repository=object()),None)
        binding=SimpleNamespace(scope='owner',conversation_id='chat')
        current=SimpleNamespace(trip=SimpleNamespace(content=json.dumps(document).encode()))
        for mode in ('next-week','late-arrival','early-departure','different-zone'):
            changed=deepcopy(fields)
            if mode=='next-week':
                changed['arrival']['date']=known('2026-11-19');changed['departure']['date']=known('2026-11-21')
            elif mode=='late-arrival':changed['arrival']['time']=known('11:00')
            elif mode=='early-departure':
                changed['departure']['date']=known('2026-11-11');changed['departure']['time']=known('09:30')
            else:changed['destination_timezone']=known('Asia/Tokyo')
            with self.subTest(mode=mode),patch('cj_trip.planning_context.read_current',return_value=current):
                self.assertTrue(save.planning_window_conflict(binding,changed))
            self.assertEqual(document,before)

    def test_source_read_failure_propagates_instead_of_claiming_no_trip(self):
        from cj_trip.domain import Denied
        _,fields=fixture();save=LioPlanSave(None,SimpleNamespace(repository=object()),None)
        with patch('cj_trip.planning_context.read_current',side_effect=Denied('original source unavailable')):
            with self.assertRaises(Denied):save.planning_window_conflict(SimpleNamespace(scope='owner',conversation_id='chat'),fields)


if __name__=='__main__':unittest.main(verbosity=2)
