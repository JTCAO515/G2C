"""Pure skeleton/solver projection, not a publisher/source authority test."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest

from cj_api.lio_pipeline_document import compile_document,lodging_anchors,representation_size
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton,CapacityExceeded,SkeletonUnavailable
from cj_feasibility.rich_assembly import assemble
from cj_feasibility.rich_edges import activity_windows
from cj_feasibility.rich_solver import Limits
from cj_trip.domain import packed
from cj_trip.rich_source import capture
from cj_trip.structured_v4 import validate_candidate,adjacent_pairs
from test_lio_pipeline_skeleton import proposal

ROOT=Path(__file__).resolve().parents[3]
BASE=json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']['unconfirmed']['source']


def checks(days,*,dated=False):
    return [dict(kind=kind,state='unknown'if dated else'not_checked',day_indices=list(range(1,days+1)),item_ids=[],
        reason='date_evidence_not_collected'if dated else'date_not_set',evidence_refs=[])for kind in ('weather','day_opening')]


def source_for(rows):
    value=deepcopy(BASE);value['profile_states']={}
    records=[dict(provider='checks',kind=row['kind'],reference='code-'+row['kind'],sha256=sha256(packed(row)).hexdigest(),payload=row)for row in rows]
    value['records']=records
    return capture(packed(value),expected_original=value['original'],expected_plan_now=value['plan_now'],
        expected_policy=value['policy'],accepted_profile_states={},eligible_records=records)


def build(days=3,start=None,*,edge=False):
    expected=recipes(days,'moderate',light_first=edge,light_last=edge)
    skeleton=parse_skeleton(packed(proposal(expected)),expected,id_prefix='actual-code')
    rows=checks(days,dated=start is not None)
    document,activities,subjects=compile_document(skeleton,SimpleNamespace(start_date=start),locale='en',subjects=('self',),
        timezone='Asia/Shanghai',code_checks=rows,places={s.item_id:None for s in skeleton.stops},
        hotel_places=(None,None),protected_items=(),protected_activities=(),legacy_sources=())
    return document,activities,subjects,rows


class PipelineDocument(unittest.TestCase):
    def anchored(self):
        expected=recipes(3,'moderate',light_first=False,light_last=False)
        skeleton=parse_skeleton(packed(proposal(expected)),expected,id_prefix='actual-code')
        rows=checks(3);edges=activity_windows(3,arrival_clock=0,departure_clock=23*3600,departure_mode='train')
        place=build()[0]['lodging']['recommendations'][0]['place']
        nodes,order,schedule=lodging_anchors(place,edges,id_prefix='actual-code',timezone='Asia/Shanghai',locale='en')
        value,activities,subjects=compile_document(skeleton,SimpleNamespace(start_date=None),locale='en',subjects=('self',),
            timezone='Asia/Shanghai',code_checks=rows,places={s.item_id:None for s in skeleton.stops},
            hotel_places=(None,None),protected_items=(),protected_activities=(),legacy_sources=(),
            additional_items=nodes,additional_activities=order)
        return value,activities,subjects,rows,edges,nodes,schedule

    def test_full_proposed_document_is_valid_but_never_claims_sources_bookings_or_dates(self):
        for days in (3,4,5):
            document,activities,subjects,rows=build(days)
            validate_candidate(document,source_for(rows))
            self.assertEqual(len(document['days']),days)
            self.assertEqual(len(document['items']),days*5)
            self.assertEqual(len(document['legs']),days*4)
            self.assertEqual(document['calendar'],dict(state='undated'))
            self.assertEqual(len(activities),len(document['items']))
            self.assertTrue(all(value==['self']for value in subjects.values()))
            self.assertTrue(all(item['place']['source']is None and item['verification']=='pending'for item in document['items']))
            self.assertTrue(all('date'not in item['schedule']['start']for item in document['items']))

    def test_calendar_dates_come_only_from_explicit_basis_and_checks_are_not_relabelled_clear(self):
        document,_,_,rows=build(3,'2026-12-01')
        validate_candidate(document,source_for(rows))
        self.assertEqual([d['date']for d in document['days']],['2026-12-01','2026-12-02','2026-12-03'])
        self.assertEqual(document['date_checks'],rows)
        self.assertTrue(all(row['state']=='unknown'for row in rows))

    def test_existing_assembly_consumes_the_actual_compiled_document_without_a_new_object(self):
        document,activities,_,rows=build()
        source=source_for(rows)
        result=assemble(document,source=source,facts=(),activities=activities,
            edges=activity_windows(3,arrival_clock=0,departure_clock=23*3600,departure_mode='train'),
            phase='order',locale='en',limits=Limits(max_seconds=2),stop=Event())
        self.assertEqual(result.status,'CONDITIONAL_SCHEDULE')
        value=json.loads(result.content);validate_candidate(value,source)
        self.assertEqual(adjacent_pairs(value),[(leg['day_index'],leg['from_item_id'],leg['to_item_id'])for leg in value['legs']])
        self.assertTrue(result.unknown_transfers)

    def test_unknown_edge_proximity_is_not_invented_from_matching_area_names(self):
        document,activities,_,rows=build(edge=True)
        result=assemble(document,source=source_for(rows),facts=(),activities=activities,
            edges=activity_windows(3),phase='order',locale='en',limits=Limits(max_seconds=2),stop=Event())
        self.assertEqual(result.status,'UNKNOWN')
        self.assertIsNone(result.content)
        self.assertTrue(all(activity.nearby is None for activity in activities))

    def test_complete_graph_counts_hotel_legs_and_keeps_estimate_not_booking_semantics(self):
        document,activities,subjects,rows,_,nodes,_=self.anchored()
        validate_candidate(document,source_for(rows))
        self.assertEqual(representation_size(document)[:2],(21,18))
        self.assertEqual(len(nodes),6)
        self.assertEqual(len(activities),len(subjects))
        for node in nodes:
            self.assertEqual(node['kind'],'hotel')
            self.assertEqual(node['fixed'],dict(state='known',value=False))
            self.assertEqual(node['source_category'],'unknown')
            self.assertIn('unconfirmed',node['text'])
            self.assertIn('no stay or booking is confirmed',node['note'])
            self.assertEqual(node['schedule']['start'],node['schedule']['end'])

    def test_order_points_then_original_schedule_windows_preserve_pairs_without_late_return_default(self):
        document,activities,_,rows,edges,nodes,schedule=self.anchored();original=deepcopy(document)
        source=source_for(rows)
        ordered=assemble(document,source=source,facts=(),activities=activities,edges=edges,phase='order',locale='en',
            limits=Limits(max_seconds=2),stop=Event())
        self.assertEqual(ordered.status,'CONDITIONAL_SCHEDULE')
        value=json.loads(ordered.content);pairs=adjacent_pairs(value)
        ids={node['id']for node in nodes}
        for day in range(1,4):
            items=[item for item in value['items']if item['schedule']['start']['day_index']==day]
            self.assertEqual(items[0]['id'],f'actual-code-lodging-d{day}-out')
            self.assertEqual(items[-1]['id'],f'actual-code-lodging-d{day}-back')
        active=tuple(activity for activity in activities if activity.item_id not in ids)+schedule
        final=assemble(value,source=source,facts=(),activities=active,edges=edges,phase='schedule',locale='en',
            limits=Limits(max_seconds=2),stop=Event())
        self.assertEqual(final.status,'CONDITIONAL_SCHEDULE')
        result=json.loads(final.content);self.assertEqual(adjacent_pairs(result),pairs)
        first_return=next(item for item in result['items']if item['id']=='actual-code-lodging-d1-back')
        self.assertNotEqual(first_return['schedule']['start']['time']['value'],'23:59')
        self.assertEqual(document,original)

    def test_anchor_points_are_inside_original_minute_windows_and_unresolved_edges_do_not_gain_times(self):
        place=build()[0]['lodging']['recommendations'][0]['place']
        edges=activity_windows(1,arrival_clock=61,departure_clock=23*3600,departure_mode='flight')
        nodes,order,schedule=lodging_anchors(place,edges,id_prefix='code',timezone='Asia/Shanghai',locale='zh')
        self.assertEqual(edges.windows[0][0].start,7261)
        self.assertEqual(order[0].windows[0].start,7320)
        self.assertEqual(order[-1].windows[0].start,20*3600)
        self.assertTrue(all(activity.windows==edges.windows[0]for activity in schedule))
        for unresolved in (activity_windows(1,arrival_clock=23*3600,departure_clock=1*3600,departure_mode='flight'),
                           activity_windows(3,departure_clock=23*3600,departure_mode=None)):
            with self.assertRaises(SkeletonUnavailable):
                lodging_anchors(place,unresolved,id_prefix='code',timezone='Asia/Shanghai',locale='zh')

    def test_full_representation_capacity_checks_each_limit_without_trimming(self):
        original,_,_,_=build()
        for field in ('items','legs'):
            value=deepcopy(original);value[field]=value[field]*61
            before=deepcopy(value)
            with self.subTest(field=field),self.assertRaises(CapacityExceeded):representation_size(value)
            self.assertEqual(value,before)
        value=deepcopy(original);value['sources']=[dict(original_utf8='京'*334000)]
        self.assertLess(len(str(value)),1_000_000)
        with self.assertRaises(CapacityExceeded):representation_size(value)

    def test_hotels_are_counted_before_lookup_even_when_tourist_stops_alone_fit(self):
        expected=recipes(12,'moderate',light_first=False,light_last=False)
        skeleton=parse_skeleton(packed(proposal(expected)),expected,id_prefix='complete')
        self.assertEqual(len(skeleton.stops),60)
        edges=activity_windows(12,arrival_clock=0,departure_clock=23*3600,departure_mode='train')
        place=build()[0]['lodging']['recommendations'][0]['place']
        nodes,order,_=lodging_anchors(place,edges,id_prefix='complete',timezone='Asia/Shanghai',locale='zh')
        with self.assertRaises(CapacityExceeded):
            compile_document(skeleton,SimpleNamespace(start_date=None),locale='zh',subjects=('self',),
                timezone='Asia/Shanghai',code_checks=checks(12),places={s.item_id:None for s in skeleton.stops},
                hotel_places=(None,None),protected_items=(),protected_activities=(),legacy_sources=(),
                additional_items=nodes,additional_activities=order)
        self.assertEqual(len(skeleton.stops),60)
        self.assertEqual(len(nodes),24)


if __name__=='__main__':unittest.main()
