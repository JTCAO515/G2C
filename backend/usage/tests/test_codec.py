import json
import unittest
from copy import deepcopy
from dataclasses import asdict
from cj_usage.codec import decode, encode, CorruptLedger
from cj_usage.core import Config, Ledger, Meter, Command, Receipt
from test_core import TransactionFake


class CodecTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config('synthetic-unit',10,0,1000,20,3,20,50)
        self.repo = TransactionFake()
        self.meter = Meter(self.repo,self.cfg,lambda:100)
        self.meter.reserve(Command('a','op','run','model','a'*64,6,2))

    def test_all_lifecycle_roundtrips(self):
        for transition in (lambda:None,lambda:self.meter.claim('a'),
                           lambda:self.meter.cancel('run'),
                           lambda:self.meter.settle(Receipt('a','r','synthetic-unit',3,1))):
            transition()
            self.assertEqual(decode(json.loads(encode(self.repo.ledger))), self.repo.ledger)
        self.assertEqual(decode(json.loads(encode(Ledger(self.cfg)))), Ledger(self.cfg))

    def test_corruption_rejected(self):
        original = asdict(self.repo.ledger)
        cases=[]
        for field,value in [('state','settled'),('cancelled',True),('exceeded',True)]:
            d=deepcopy(original);d['attempts']['a'][field]=value;cases.append(d)
        for field,value in [('steps',0),('tools',1),('cancelled',1),('started',101)]:
            d=deepcopy(original);d['runs']['run'][field]=value;cases.append(d)
        for value in (None,float('nan'),True,99):
            d=deepcopy(original);d['last_clock']=value;cases.append(d)
        d=deepcopy(original);d['attempts']['a']['command']['attempt_id']='b';cases.append(d)
        d=deepcopy(original);d['extra']='unknown';cases.append(d)
        for d in cases:
            with self.subTest(data=d), self.assertRaises(CorruptLedger): decode(d)

    def test_receipt_and_unit_binding(self):
        self.meter.claim('a');self.meter.settle(Receipt('a','r','synthetic-unit',3,1))
        for field,value in [('attempt_id','other'),('unit','USD'),('actual',True)]:
            d=asdict(self.repo.ledger);d['attempts']['a']['receipt'][field]=value
            with self.assertRaises(CorruptLedger): decode(d)

    def test_prewrite_validation(self):
        self.repo.ledger.runs['run'].steps=0
        with self.assertRaises(CorruptLedger): encode(self.repo.ledger)
