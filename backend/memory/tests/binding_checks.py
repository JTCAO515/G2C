"""No database started: public binding rejection, before any connection or output."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'auth')]
from cj_auth.interfaces import TrustedPrincipal
from cj_memory.domain import Service
from cj_memory.operation import OperationWithheld
from cj_memory.postgres import Repository
P=TrustedPrincipal('issuer','subject','audience',1,1,9999999999)

def no_connect():
    raise AssertionError('binding rejection must not connect')

class Checks(unittest.TestCase):
    def test_wrong_service_scope_before_callback_or_connection(self):
        service=Service(Repository(no_connect,'B'))
        def callback(_):raise AssertionError('must not run callback')
        with self.assertRaises(OperationWithheld) as caught:
            service.with_operation(lambda _:(P,'A'),callback)
        self.assertEqual(caught.exception.stage,'entry')
        self.assertFalse(caught.exception.commit_possible)

    def test_repository_replacement_same_scope_rejected(self):
        for stage in ('entry','return'):
            service=Service(Repository(no_connect,'A'))
            def guard(current):
                if current==stage:service.repository=Repository(no_connect,'A')
                return P,'A'
            with self.assertRaises(OperationWithheld) as caught:
                service.with_operation(guard,lambda _:b'{}')
            self.assertEqual(caught.exception.stage,stage)

    def test_coordinated_scope_change_cannot_rebind(self):
        service=Service(Repository(no_connect,'A'))
        def guard(stage):
            if stage=='return':
                service.repository.scope='B'
                return P,'B'
            return P,'A'
        with self.assertRaises(OperationWithheld) as caught:
            service.with_operation(guard,lambda _:b'{}')
        self.assertEqual(caught.exception.stage,'return')

if __name__=='__main__':unittest.main(verbosity=2)
