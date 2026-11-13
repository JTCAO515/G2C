"""Date completion is a narrow operation on an existing undated itinerary."""
import unittest

from cj_api.local_lio_calendar import date_completion


class CalendarDates(unittest.TestCase):
    def test_bilingual_explicit_date_completion_forms(self):
        for text in ('明天开始','从后天出发。','2026-12-01开始','出发日期定在下周二',
                     'Start tomorrow','From 2026-12-01','Set the start date to next Tuesday.',
                     '2026年12月1日出发','26.12.01开始','26年12月1日出发',
                     'From 26.12.01','Start 26/12/01','从2026/12/01出发'):
            with self.subTest(text=text):self.assertTrue(date_completion(text))

    def test_consultation_translation_uncertainty_and_clock_changes_are_not_date_conversion(self):
        for text in ('明天天气怎么样？','请翻译“明天开始”','明天开始可以吗？',
                     '日期还没定','下周','明天11点开始','不要明天开始',
                     'What is the weather tomorrow?','Translate "Start tomorrow"',
                     'Start tomorrow if the museum is open.','Not tomorrow','next week',
                     'Start tomorrow at 11:00','26.12.01开始可以吗？',
                     '请翻译“26年12月1日出发”','Start 26.12.01 if it is open.'):
            with self.subTest(text=text):self.assertFalse(date_completion(text))


if __name__=='__main__':unittest.main()
