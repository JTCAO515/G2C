"""Known partial days obey their time windows without lowering full-day pace."""
import unittest
from cj_api.lio_pipeline_preflight import recipes_for_edges
from cj_api.lio_pipeline_skeleton import recipes
from cj_api.lio_pipeline_skeleton import parse_skeleton
from cj_api.lio_pipeline_preflight import preflight_document
from cj_feasibility.rich_edges import activity_windows
from cj_trip.domain import packed
from cj_trip.calendar_conversion import source_window_conflicts
from test_lio_pipeline_skeleton import proposal
from test_lio_pipeline_preflight import fixed,projection


class EdgeRecipes(unittest.TestCase):
    def test_flight_and_train_departure_cutoffs_exclude_an_impossible_dinner(self):
        for mode,end in (('flight',15*3600),('train',16*3600+30*60)):
            edges=activity_windows(3,departure_clock=18*3600,departure_mode=mode,first_day_full=True)
            result=recipes_for_edges(3,'moderate',edges)
            self.assertEqual(edges.windows[-1][0].end,2*86400+end)
            self.assertEqual(result[-1].meals,('lunch',))
            self.assertEqual(result[-1].sights,3)
            self.assertEqual((result[1].sights,result[1].meals),(3,('lunch','dinner')))

    def test_unknown_edges_keep_the_approved_light_first_day_and_nearby_last_morning(self):
        result=recipes_for_edges(4,'packed',activity_windows(4))
        self.assertEqual(result,recipes(4,'packed',light_first=True,light_last=True))

    def test_arrival_buffer_removes_only_meals_that_cannot_fit_not_sights(self):
        edges=activity_windows(3,arrival_clock=12*3600)
        result=recipes_for_edges(3,'relaxed',edges)
        self.assertEqual((result[0].sights,result[0].meals),(2,('dinner',)))
        self.assertEqual((result[1].sights,result[1].meals),(2,('lunch','dinner')))

    def test_no_silent_density_reduction_when_a_day_is_too_short(self):
        edges=activity_windows(3,arrival_clock=17*3600)
        result=recipes_for_edges(3,'packed',edges)
        self.assertEqual(result[0].sights,4)
        self.assertEqual(result[0].meals,('dinner',))

    def test_explicit_fixed_dinner_is_preserved_and_conflicts_instead_of_being_filtered(self):
        edges=activity_windows(3,departure_clock=18*3600,departure_mode='flight',first_day_full=True)
        expected=recipes_for_edges(3,'relaxed',edges)
        item=fixed();item['description']='第三天固定晚餐'
        for edge,hour in (('start','20:00'),('end','21:00')):
            item[edge]['time']=dict(state='known',value=hour)
            item[edge]['timezone']=dict(state='known',value='Asia/Shanghai')
        fields=dict(fixed_items=[item],destination_timezone=dict(state='known',value='Asia/Shanghai'),
            departure=dict(date=dict(state='known',value='2026-12-03'),time=dict(state='known',value='18:00'),
                timezone=dict(state='known',value='Asia/Shanghai'),place=dict(state='missing')))
        skeleton=parse_skeleton(packed(proposal(expected)),expected,id_prefix='fixed-dinner')
        document=preflight_document(skeleton,projection(fields,'2026-12-01'),edges,
            id_prefix='fixed-dinner',locale='en')
        retained=next(row for row in document['items']if row['id']==item['item_id'])
        self.assertEqual(retained['schedule']['start']['time'],item['start']['time'])
        self.assertEqual(retained['fixed'],dict(state='known',value=True))
        self.assertTrue(source_window_conflicts(document,fields))
