"""Run exact retained Review assertions against root's fixed public source/DB fixture.

Only the fixture import is supplied here; original assertion file remains unchanged.
No resource, old snapshot import, source patch or extra authority callback is used.
"""
import runpy
import sys
import types
from pathlib import Path
from usage_status_wire_checks import UsageStatusChecks,Conn
from cj_auth.read_context import ProtectedReadBoundary
from cj_usage.protected_status import AttemptStatusReader,StatusReadConfiguration
from cj_usage.postgres import PostgresRepository
from cj_api.usage_status_composition import build_usage_status_dependencies

class CompositionChecks:
    def setUp(self):
        self.s=UsageStatusChecks();self.s.setUp();self.s.log=[]
        checker,_,host,_=build_usage_status_dependencies(configuration=self.s.options,**self.s.args)
        self.s.checker=checker
        owner=self.s
        class LoggedConn(Conn):
            def close(self):
                super().close();owner.log.append('connection_close')
        self.s.repo=PostgresRepository(lambda:LoggedConn(owner),'owner-period-scope')
        self.config=host
        self.reader=AttemptStatusReader(ProtectedReadBoundary(checker,max_response_bytes=host.max_response_bytes),
            lambda *args:self.s.repo,configuration=host)
    def read(self):return self.reader.read(self.s.token,'attempt')

fixture=types.ModuleType('ProtectedStatusCheck');fixture.CompositionChecks=CompositionChecks
sys.modules['ProtectedStatusCheck']=fixture
original=Path(__file__).with_name('evidence')/'usage-status/review-final-binding-tests.py'
sys.argv=[str(original)]
runpy.run_path(str(original),run_name='__main__')
