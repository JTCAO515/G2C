from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
import sqlite3
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from cj_api.local_app import ISSUER, scope_for
from cj_api.runtime_authority import RuntimeAuthority
from cj_auth.interfaces import AdmissionStatus
from cj_usage.sublimits import scope_hash
from runtime_adapter.contract import Unavailable


class ActorAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.database = sqlite3.connect(':memory:')
        self.addCleanup(self.database.close)
        self.database.executescript('CREATE TABLE scope_sublimit(scope_hash TEXT,line TEXT);'
            'CREATE TABLE sublimit(line TEXT,policy TEXT);'
            'CREATE TABLE attempt(id TEXT,kind TEXT,state TEXT,receipt TEXT);'
            'CREATE TABLE attempt_sublimit(attempt_id TEXT,line TEXT);')
        subject = 'm4-synthetic-actor-authority';scope = scope_for(ISSUER,subject)
        self.database.execute('INSERT INTO scope_sublimit VALUES(?,?)',(scope_hash(scope),'C'))
        self.database.execute('INSERT INTO sublimit VALUES(?,?)',('C',
            '{"active_cap":10000000,"max_calls":1}'))
        self.database.execute('INSERT INTO attempt VALUES(?,?,?,?)',('original','model','INTENT',None))
        self.database.execute('INSERT INTO attempt_sublimit VALUES(?,?)',('original','C'))
        self.database.commit()
        self.now = datetime(2026,11,15,11,30,tzinfo=ZoneInfo('Asia/Shanghai'))
        self.monotonic = 10
        self.current = b'original-pins';self.allowed = True;self.hook = lambda: None
        @contextmanager
        def connect():
            try:yield self.database
            finally:self.database.rollback()
        budget = SimpleNamespace(connect=connect,require_producer=lambda db:None,
            check_date=lambda:self.hook(),ledger_id='original-journal',producer='original-producer')
        checker = SimpleNamespace(check=lambda token:SimpleNamespace(status=
            AdmissionStatus.ALLOWED if self.allowed else AdmissionStatus.DENIED,
            principal=SimpleNamespace(issuer=ISSUER,subject=subject)))
        pins = SimpleNamespace(key=sha256(self.current).hexdigest(),raw=self.current)
        self.authority = RuntimeAuthority(checker,lambda:'fixture-token',budget,pins,
            lambda:self.current,line='C',wall_clock=lambda:self.now,clock=lambda:self.monotonic)
        self.binding = self.authority.binding();self.pins = pins

    def current_operation(self):
        self.authority.require_current_operation(binding=self.binding,pins_sha256=self.pins.key,deadline=100)

    def test_original_reserved_hold_is_not_charged_again(self):
        with self.assertRaisesRegex(Unavailable,'ORIGINAL_LINE_ALLOWANCE_EXHAUSTED'):
            self.authority.require(binding=self.binding,pins_sha256=self.pins.key,purpose='actor',deadline=100,read_only=False)
        before = self.database.total_changes
        self.current_operation()
        self.assertEqual(self.database.total_changes,before)
        self.assertEqual(self.database.execute('SELECT count(*) FROM attempt').fetchone(),(1,))

    def test_current_pins_window_deadline_and_auth_remain_execution_guards(self):
        for fault in ('pins','window','deadline','auth'):
            with self.subTest(fault=fault):
                original = self.current,self.now,self.monotonic,self.allowed
                if fault == 'pins':self.current=b'changed'
                elif fault == 'window':self.now=self.now.replace(hour=23)
                elif fault == 'deadline':self.monotonic=100
                else:self.allowed=False
                with self.assertRaises(Unavailable):self.current_operation()
                self.current,self.now,self.monotonic,self.allowed=original

    def test_clock_and_pin_changes_inside_last_callback_are_not_missed(self):
        for fault in ('pins','window','deadline'):
            with self.subTest(fault=fault):
                original = self.current,self.now,self.monotonic
                def change():
                    if fault=='pins':self.current=b'changed'
                    elif fault=='window':self.now=self.now.replace(hour=23)
                    else:self.monotonic=100
                self.hook=change
                with self.assertRaises(Unavailable):self.current_operation()
                self.current,self.now,self.monotonic=original;self.hook=lambda:None

    def test_reconciliation_remains_read_only_after_window_and_pin_change(self):
        self.now=self.now.replace(hour=23);self.current=b'new-source'
        self.authority.require(binding=self.binding,pins_sha256=self.pins.key,purpose='query',deadline=100,read_only=True)


if __name__=='__main__':unittest.main()
