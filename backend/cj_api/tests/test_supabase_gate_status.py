"""Existing local state plus a read-only observation is not automatic PASS."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from supabase_pool_gate import repeated_run_passed


class GateStatus(unittest.TestCase):
    def test_only_complete_and_currently_empty_original_can_pass(self):
        for state in ('PLANNED','SEED_INTENT','SEEDED','CLEANUP_INTENT','COMPLETE'):
            for observation in ('EMPTY_CONFIRMED','OWNED_SEED_MATCH','HOLD_CHANGED_OR_PARTIAL'):
                with self.subTest(state=state,observation=observation):
                    self.assertEqual(repeated_run_passed(dict(result={'state':state},cloud_observation={'status':observation})),
                                     state=='COMPLETE' and observation=='EMPTY_CONFIRMED')


if __name__=='__main__':unittest.main()
