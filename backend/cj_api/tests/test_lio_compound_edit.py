"""#818: frozen public consumer templates constrain one original item."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import unittest

from cj_api.lio_edit_selection import select_lio_edit
from cj_trip.domain import Trip,packed
from test_lio_edit_selection import itinerary,known,stop

ROOT=Path(__file__).resolve().parents[3]


class CompoundEdit(unittest.TestCase):
    def example(self,locale,*,fixed=False,duplicate=False):
        trip,_=itinerary()
        doc=json.loads(trip.content)
        name='成都人民公园' if locale=='zh' else "Chengdu People's Park"
        item=next(x for x in doc['items'] if x['id']=='afternoon');item['text']=name
        if fixed:item['fixed']=known(True)
        if duplicate:doc['items'].append(dict(item,id='another'))
        raw=(ROOT/'eval/lio_national_cases.v1.json').read_bytes()
        self.assertEqual(sha256(raw).hexdigest(),'478f772d6b78817c8a88b9d48448f3f05c0bb5c0f31661ade3f6edec5fddce7f')
        text=json.loads(raw)['common_flow'][2][locale].format(actual_item_name=name,
            actual_time_range='13:00–14:00',replacement_query='杜甫草堂' if locale=='zh' else 'Du Fu Thatched Cottage')
        return Trip(trip.trip_id,trip.version,packed(doc)),text

    def select(self,trip,text,locale='en',**kwargs):
        return select_lio_edit(trip,text,locale,'compound',starts_on=date(2026,11,11),
                               ends_on=date(2026,11,13),national_names=True,**kwargs)

    def test_exact_frozen_bilingual_name_day_clock_templates(self):
        for locale in ('zh','en'):
            with self.subTest(locale=locale):
                trip,text=self.example(locale);result=self.select(trip,text,locale)
                self.assertEqual(result.status,'preview')
                self.assertEqual(result.candidate.affected_ids,('afternoon',))
                before=json.loads(trip.content);after=json.loads(result.candidate.candidate.content)
                expected=[dict(item,text='杜甫草堂' if locale=='zh' else 'Du Fu Thatched Cottage')
                          if item['id']=='afternoon' else item for item in before['items']]
                self.assertEqual(after['items'],expected)
                self.assertEqual(after['title'],before['title'])

    def test_mismatched_name_day_or_clock_never_chooses_one_constraint(self):
        for locale in ('zh','en'):
            trip,text=self.example(locale)
            variants=[text.replace('13:00–14:00','14:00–15:00'),text.replace('13:00–14:00','24:00–25:00'),
                      text.replace('成都人民公园','另一个公园') if locale=='zh' else text.replace("Chengdu People's Park",'Another Park'),
                      text.replace('第二天','第三天') if locale=='zh' else text.replace('day 2','day 3')]
            for request in variants:
                with self.subTest(locale=locale,request=request):self.assertEqual(self.select(trip,request,locale).status,'clarify')

    def test_duplicate_fixed_and_unknown_targets_keep_original_guards(self):
        for locale in ('zh','en'):
            trip,text=self.example(locale,duplicate=True)
            self.assertEqual(self.select(trip,text,locale).status,'clarify')
            trip,text=self.example(locale,fixed=True)
            self.assertEqual(self.select(trip,text,locale).status,'protected')
            doc=json.loads(trip.content);next(x for x in doc['items'] if x['id']=='afternoon')['fixed']={'state':'unknown'}
            self.assertEqual(self.select(Trip(trip.trip_id,trip.version,packed(doc)),text,locale).status,'protected')

    def test_to_and_apostrophe_in_full_names_are_not_edit_separators(self):
        trip,text=self.example('en');doc=json.loads(trip.content)
        next(x for x in doc['items'] if x['id']=='afternoon')['text']="Road to Chengdu People's Park"
        text=text.replace("Chengdu People's Park","Road to Chengdu People's Park")
        self.assertEqual(self.select(Trip(trip.trip_id,trip.version,packed(doc)),text).status,'preview')

    def test_conditions_after_keep_clause_and_selected_keep_conflict_are_rejected(self):
        trip,text=self.example('en')
        for tail in (" but don't apply.",' only if it is open.',' after my approval.'):
            with self.subTest(tail=tail):self.assertEqual(self.select(trip,text.rstrip('.')+tail).status,'clarify')
        trip,text=self.example('zh')
        for tail in ('不过先别改。','如果开放才执行。'):
            with self.subTest(tail=tail):self.assertEqual(self.select(trip,text.rstrip('。')+tail,'zh').status,'clarify')
        trip,text=self.example('en');doc=json.loads(trip.content)
        next(x for x in doc['items'] if x['id']=='afternoon')['text']='hotel meetup'
        text=text.replace("Chengdu People's Park",'hotel meetup')
        self.assertEqual(self.select(Trip(trip.trip_id,trip.version,packed(doc)),text).status,'clarify')

    def test_legacy_profile_is_not_widened(self):
        trip,text=self.example('en')
        old=select_lio_edit(trip,text,'en','legacy',starts_on=date(2026,11,11),ends_on=date(2026,11,13))
        self.assertEqual(old.status,'clarify')

    def test_exact_r11_stop_ignores_a_different_stop_that_crosses_noon(self):
        starts_on, ends_on = date(2026, 11, 22), date(2026, 11, 24)
        for locale, name, replacement, text, broad in (
            ('zh', '春熙路步行街', '成都博物馆',
             '把第二天下午「春熙路步行街」（14:00–17:00）换成成都博物馆，其他安排和酒店集合不变。',
             '把第二天下午换成成都博物馆。'),
            ('en', 'Chunxi Road Pedestrian Street', 'Chengdu Museum',
             'Replace “Chunxi Road Pedestrian Street” on day 2 afternoon (14:00–17:00) with Chengdu Museum; keep everything else and the hotel meetup unchanged.',
             'Replace the afternoon of day 2 with Chengdu Museum.'),
        ):
            title = '成都三日游' if locale == 'zh' else 'Three days in Chengdu'
            hotel = '酒店集合' if locale == 'zh' else 'hotel meetup'
            pandas = '成都大熊猫繁育研究基地' if locale == 'zh' else 'Chengdu Research Base of Giant Panda Breeding'
            items = [
                stop('fixed-meetup', hotel, '2026-11-22', '09:00', '10:00', known(True)),
                stop('d2a', pandas, '2026-11-23', '09:00', '12:30', known(False)),
                stop('d2b', name, '2026-11-23', '14:00', '17:00', known(False)),
                stop('d3', '杜甫草堂' if locale == 'zh' else 'Du Fu Thatched Cottage',
                     '2026-11-24', '14:00', '16:00', known(False)),
            ]
            doc = dict(content_version='structured.2', title=title, items=items, sources=[])
            trip = Trip('r11-current', 1, packed(doc))

            def select(request):
                return select_lio_edit(trip, request, locale, 'r11-exact', starts_on=starts_on,
                                       ends_on=ends_on, national_names=True)

            with self.subTest(locale=locale):
                result = select(text)
                self.assertEqual(result.status, 'preview')
                self.assertEqual(result.candidate.affected_ids, ('d2b',))
                self.assertFalse(result.candidate.can_publish)
                self.assertEqual(json.loads(result.candidate.candidate.content)['items'],
                                 [dict(item, text=replacement) if item['id'] == 'd2b' else item for item in items])
                self.assertEqual(select(broad).status, 'clarify')
                self.assertEqual(select(text.replace(name, pandas).replace('14:00–17:00', '09:00–12:30')).status,
                                 'clarify')
