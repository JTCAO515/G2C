"""Existing local state plus a read-only observation is not automatic PASS."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from supabase_pool_gate import repeated_run_passed,reset_observation,digest


class GateStatus(unittest.TestCase):
    def test_sql_timestamp_hashes_compare_instants_without_adopting_changed_data(self):
        source={'table':[{'at':datetime(2026,11,4,18,tzinfo=timezone(timedelta(hours=8))),'value':'original'}]}
        cloud={'table':[{'at':datetime(2026,11,4,10,tzinfo=timezone.utc),'value':'original'}]}
        self.assertEqual(digest(source),digest(cloud))
        self.assertEqual(digest(source,legacy=True),digest(cloud,legacy=True))
        changed={'table':[{'at':datetime(2026,11,4,10,tzinfo=timezone.utc),'value':'changed'}]}
        self.assertNotEqual(digest(source),digest(changed))
        shifted={'table':[{'at':datetime(2026,11,4,11,tzinfo=timezone.utc),'value':'original'}]}
        self.assertNotEqual(digest(source),digest(shifted))
    def test_application_reset_never_claims_supplier_reset_was_observed(self):
        self.assertEqual(reset_observation(1,1),'UNKNOWN_application_reset_preceded_observation')
        self.assertEqual(reset_observation(1,2),'UNKNOWN_different_backend')
    def test_only_complete_and_currently_empty_original_can_pass(self):
        for state in ('PLANNED','SEED_INTENT','SEEDED','CLEANUP_INTENT','COMPLETE'):
            for observation in ('EMPTY_CONFIRMED','OWNED_SEED_MATCH','HOLD_CHANGED_OR_PARTIAL'):
                with self.subTest(state=state,observation=observation):
                    self.assertEqual(repeated_run_passed(dict(result={'state':state},cloud_observation={'status':observation})),
                                     state=='COMPLETE' and observation=='EMPTY_CONFIRMED')


if __name__=='__main__':unittest.main()
