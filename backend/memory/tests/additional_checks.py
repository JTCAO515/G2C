import unittest
from pg_checks import Checks
# Preserve the initial database and its first-run evidence; only run added cases.
suite=unittest.TestSuite(Checks(n) for n in ('test_10_list_and_disabled','test_11_expiry_publication_fence'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
