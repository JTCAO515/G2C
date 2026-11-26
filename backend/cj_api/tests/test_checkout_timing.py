"""Pool checkout timing is summarized per window; LIO_ lines are untouched (#1828)."""
import logging
import unittest

from cj_api import supabase_test_database as db


class CheckoutTimingTests(unittest.TestCase):
    def test_summary_per_window_and_single_lines_only_for_slow_checkouts(self):
        now=[0.0];timing=db._CheckoutTiming(clock=lambda:now[0])
        with self.assertLogs('cj_usage.audit','INFO') as logs:
            for index in range(100):
                now[0]=index*0.5
                timing.record(7,True,float(index%10))
            timing.record(8,False,750.0)
            now[0]=61.0
            timing.record(9,True,1.0)
            logging.getLogger('cj_usage.audit').info('LIO_TIMING first_text_ms=900')
        lines=logs.output
        self.assertFalse(any('M4_DB_CHECKOUT_TIMING' in line for line in lines))
        slow=[line for line in lines if 'M4_DB_CHECKOUT_SLOW' in line]
        summaries=[line for line in lines if 'M4_DB_CHECKOUT_SUMMARY' in line]
        self.assertEqual(len(slow),1);self.assertIn('pooled=false elapsed_ms=750.000',slow[0])
        self.assertEqual(len(summaries),2)
        self.assertIn('pooled=true count=101 p50_ms=4.000 p95_ms=9.000',summaries[0])
        self.assertIn('max_ms=9.000',summaries[0])
        self.assertIn('pooled=false count=1',summaries[1])
        self.assertTrue(any(line.endswith('LIO_TIMING first_text_ms=900') for line in lines))

    def test_quiet_window_emits_nothing(self):
        timing=db._CheckoutTiming(clock=lambda:0.0)
        with self.assertNoLogs('cj_usage.audit','INFO'):
            timing.record(1,True,3.0)


if __name__=='__main__':unittest.main()
