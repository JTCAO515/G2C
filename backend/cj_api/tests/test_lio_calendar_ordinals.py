"""Ordinals require explicit source evidence, never a default first day."""
import unittest

from cj_api.lio_calendar_ordinals import fixed_ordinals
from cj_needs.domain import InvalidInput


class CalendarOrdinals(unittest.TestCase):
    def test_original_same_day_and_explicit_ranges(self):
        for quote, expected in (
            ('第一天9:00酒店集合', (1, 1)), ('第3天博物馆集合', (3, 3)),
            ('Hotel meetup on day 2', (2, 2)), ('On the first day, meet at the hotel', (1, 1)),
            ('第1天到第3天住这家酒店', (1, 3)), ('Hotel stay day 1 through day 3', (1, 3)),
        ):
            with self.subTest(quote=quote):
                self.assertEqual(fixed_ordinals(quote, 3), expected)

    def test_missing_ambiguous_reversed_and_out_of_range_are_not_repaired(self):
        for quote in ('酒店集合', '第4天酒店集合', 'Day 0 meetup', '第0天集合',
                      '第一天和第三天集合', 'day 1 or day 2', '不是第1天而是第2天',
                      'day 3 to day 1', '第1天酒店集合，第2天另外集合', '第3天后集合',
                      'day 1 to day 2 to day 3', '第11天集合'):
            with self.subTest(quote=quote), self.assertRaises(InvalidInput):
                fixed_ordinals(quote, 3)


if __name__ == '__main__':
    unittest.main()
