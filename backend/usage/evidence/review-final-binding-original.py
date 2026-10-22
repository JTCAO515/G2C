"""Late canonical AUTH callback cannot invalidate domain binding and publish old bytes."""
import unittest
from dataclasses import replace
import ProtectedStatusCheck as fixture
from cj_usage.read_status import ReadUnavailable
from cj_auth.read_context import ReadContextViolation

class FinalBindingTests(unittest.TestCase):
 def setUp(self):
  self.f=fixture.CompositionChecks();self.f.setUp()
 def check_change(self,kind):
  f=self.f;original=f.s.checker._access;reader=f.reader
  class LastAccess:
   after_close=0
   def evaluate(self,principal):
    if "connection_close" in f.s.log:
     self.after_close+=1
     if self.after_close==3:
      if kind=="scope":f.s.repo.scope="synthetic-replacement-scope"
      else:reader.configuration=replace(f.config,environment="synthetic-replacement-environment")
    return original.evaluate(principal)
  access=LastAccess();f.s.checker._access=access
  try:
   with self.assertRaises((ReadUnavailable,ReadContextViolation)):
    value=f.read()
    print("UNSAFE returned original status after final AUTH callback changed",kind,"bytes",len(value),"final-check-number",access.after_close)
  finally:
   self.assertEqual(access.after_close,3)
 def test_final_auth_callback_scope_replacement_withholds_original_status(self):self.check_change("scope")
 def test_final_auth_callback_configuration_replacement_withholds_original_status(self):self.check_change("configuration")

if __name__=="__main__":unittest.main()
