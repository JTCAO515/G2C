"""The compatibility worker cannot start an original from a newer wire."""
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
import unittest

from cj_agent.worker import RunWorker
from cj_message.domain import Unavailable
from cj_message.lio_context import original_for


class Database:
    def __init__(self, protocol):self.protocol=protocol
    @contextmanager
    def connect(self, scope):yield self
    def execute(self, statement, values):return self
    def fetchone(self):return ('zh',date(2026,11,13),self.protocol)


class OriginCompatibility(unittest.TestCase):
    def test_existing_wire_stays_on_original_consumer(self):
        binding=SimpleNamespace(scope='owner',conversation_id='chat',generation='g',message_id='m',run_id='r')
        original=original_for(Database(None),binding)
        self.assertEqual((original.locale,original.question_day),('zh',date(2026,11,13)))

    def test_new_wire_is_rejected_before_run_start_memory_or_meter(self):
        binding=SimpleNamespace(scope='owner',conversation_id='chat',generation='g',message_id='m',run_id='r')
        class Worker:
            def lio_original(self, current):return original_for(Database('LIO-message.3'),current)
        # Any downstream dependency access would fail: no RUN accept, memory,
        # budget exit, model or tool exists on this deliberately minimal host.
        with self.assertRaises(Unavailable):RunWorker._execute(Worker(),None,binding)


if __name__=='__main__':unittest.main()
