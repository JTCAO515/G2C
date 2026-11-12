"""Saved itinerary orientation uses the China calendar and keeps unknowns explicit."""
from datetime import datetime,timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cj_api.lio_scene import scene_prompt


def fields(first='2026-11-13',last='2026-11-15'):
    return dict(arrival=dict(place=dict(state='known',value='成都市'),date=dict(state='known',value=first)),
                departure=dict(date=dict(state='known',value=last)))


class SavedItineraryScene(unittest.TestCase):
    def test_reads_only_original_selected_trip_and_propagates_read_failure(self):
        from cj_api.local_lio_planning import LioPlanSave
        from cj_message.lio_plan_needs import lio_needs_id
        from cj_message.needs_binding import needs_scope_for
        from cj_trip.domain import Denied
        binding=SimpleNamespace(scope='owner',conversation_id='chat')
        repository=object();save=LioPlanSave(None,SimpleNamespace(repository=repository),None)
        now=datetime(2026,11,12,tzinfo=timezone.utc)
        current=SimpleNamespace(proposed=json.dumps(fields()).encode(),
            trip=SimpleNamespace(content=json.dumps(dict(content_version='structured.2')).encode()))
        with patch('cj_trip.planning_context.read_current',return_value=current)as read:
            self.assertIn('starts in 1 day',save.scene_context(binding,now))
            read.assert_called_once_with(repository,needs_scope_for('owner'),lio_needs_id('owner','chat'))
        with patch('cj_trip.planning_context.read_current',side_effect=Denied('original source unavailable')):
            with self.assertRaises(Denied):save.scene_context(binding,now)

    def test_scene_is_system_orientation_not_indexed_user_facts(self):
        from cj_api.local_lio_national import intake_prompt
        from cj_api.lio_planning_grounding import PlanningTurn
        from datetime import date
        turns=(PlanningTurn('去成都玩三天',date(2026,11,12)),)
        scene=scene_prompt(fields(),datetime(2026,11,12,tzinfo=timezone.utc))
        result=intake_prompt('zh',turns,scene=scene)
        self.assertIn('indices 0 through 0',result)
        self.assertIn('2026-11-12\n',result)
        self.assertTrue(result.endswith(scene))
        self.assertIn('not treat it as an indexed user source',result)

    def test_no_itinerary_upcoming_current_and_past(self):
        now=datetime(2026,11,12,4,tzinfo=timezone.utc)
        self.assertIn('No saved itinerary',scene_prompt(None,now))
        self.assertIn('starts in 1 day',scene_prompt(fields(),now))
        self.assertIn('day 2 in "成都市"',scene_prompt(fields('2026-11-11','2026-11-13'),now))
        self.assertIn('ended on 2026-11-11',scene_prompt(fields('2026-11-09','2026-11-11'),now))

    def test_shanghai_midnight_and_trip_end_are_inclusive(self):
        before=datetime(2026,11,12,15,59,59,tzinfo=timezone.utc)
        after=datetime(2026,11,12,16,0,0,tzinfo=timezone.utc)
        self.assertIn('starts in 1 day',scene_prompt(fields(),before))
        self.assertIn('day 1 in',scene_prompt(fields(),after))
        self.assertIn('day 3 in',scene_prompt(fields(),datetime(2026,11,15,15,59,59,tzinfo=timezone.utc)))
        self.assertIn('ended on',scene_prompt(fields(),datetime(2026,11,15,16,tzinfo=timezone.utc)))

    def test_unknown_dates_or_destination_never_imply_current_city(self):
        now=datetime(2026,11,12,tzinfo=timezone.utc)
        for field,part in (('arrival','date'),('departure','date'),('arrival','place')):
            value=fields();value[field][part]=dict(state='unknown')
            result=scene_prompt(value,now)
            self.assertIn('no confirmed destination/date range',result)
            self.assertNotIn('starts in',result);self.assertNotIn('today is day',result)
        self.assertIn('not the traveler\'s actual location',scene_prompt(fields(),now))
        self.assertIn('not traveler instructions',scene_prompt(None,now))
        self.assertIn('not treat it as an indexed user source',scene_prompt(fields(),now))

    def test_explicit_undated_calendar_never_uses_known_arrival_as_trip_start(self):
        now=datetime(2026,11,12,tzinfo=timezone.utc)
        document=dict(content_version='structured.3',calendar=dict(state='undated'),
                      days=[dict(day_index=i)for i in range(1,4)])
        result=scene_prompt(fields('2026-11-11','2026-11-13'),now,document=document)
        self.assertIn('no confirmed destination/date range',result)
        self.assertNotIn('today is day',result)
        document['calendar']=dict(state='dated',start_date='2026-11-11')
        result=scene_prompt(fields('2026-12-01','2026-12-03'),now,document=document)
        self.assertIn('day 2 in',result)


if __name__=='__main__':unittest.main(verbosity=2)
