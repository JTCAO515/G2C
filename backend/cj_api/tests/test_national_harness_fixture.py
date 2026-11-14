"""Supplier fixtures follow the selected profile without changing product guards."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from jsonschema import Draft202012Validator
from cj_draft.grouped_plan import DATED_FIRST,response_format
from cj_draft.rich_schema import Pace,PROFILES
from scripts.hk_lio_national_local_check import first_plan_fixture


class SelectedGenerationFixture(unittest.TestCase):
    def items(self):
        return [dict(id='visit-'+str(n),text='上海国家博物馆',date=stamp,
            start_time='14:00',end_time='15:00')for n,stamp in enumerate(('2026-12-01','2026-12-02'))]

    def test_all_six_selected_rich_profiles_keep_requested_richness_and_calendar_kind(self):
        for ordinal in(False,True):
            for pace,sights in((Pace.RELAXED,2),(Pace.MODERATE,3),(Pace.PACKED,4)):
                profile=PROFILES[ordinal,pace];schema=response_format(profile)['json_schema']['schema']
                with self.subTest(profile=profile):
                    value,total=first_plan_fixture(schema,self.items(),title='上海旅行',subjects=['party'])
                    Draft202012Validator(schema).validate(value)
                    self.assertEqual(value['version'],profile);self.assertEqual(total,2*(sights+2))
                    self.assertEqual([day[0]for day in value['days']],[1,2]if ordinal else['2026-12-01','2026-12-02'])
                    for day in value['days']:
                        self.assertEqual((len(day[1]),len(day[2])),(sights,2))
                        rows=sorted(day[1]+day[2],key=lambda row:row[2])
                        self.assertEqual(len({row[0]for row in rows}),sights+2)
                        self.assertTrue(all(a[3]<=b[2]for a,b in zip(rows,rows[1:])))
                        self.assertTrue(all(row[4]==['party']for row in rows))

    def test_selected_legacy_shape_preserves_original_time_and_subject_negative_data(self):
        schema=response_format(DATED_FIRST)['json_schema']['schema']
        value,total=first_plan_fixture(schema,self.items(),title='trip',subjects=['party'])
        Draft202012Validator(schema).validate(value)
        self.assertEqual(total,2);self.assertEqual(value['days'][0][1][0][2:4],['14:00','15:00'])
        for profile in(DATED_FIRST,PROFILES[False,Pace.MODERATE]):
            for subjects in([],['all'],['companion:1']):
                with self.subTest(profile=profile,subjects=subjects):
                    value,_=first_plan_fixture(response_format(profile)['json_schema']['schema'],self.items(),
                        title='trip',subjects=subjects,long_id=True)
                    self.assertEqual(value['days'][0][1][0][0],'x'*97)
                    self.assertEqual(value['days'][0][1][0][4],subjects)


if __name__=='__main__':unittest.main()
