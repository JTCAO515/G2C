"""Original C capacity is read, never topped up to make a gate pass."""
from contextlib import contextmanager
import json

from deploy.hk import app_smoke_budget as probe


def test_current_C_remaining_uses_existing_lower_ceiling_and_all_holds(monkeypatch):
    calls=[]
    class DB:
        def execute(self,sql):
            if sql=='BEGIN':calls.append('one-read-transaction');return None
            assert sql=="SELECT policy FROM sublimit WHERE line='C'"
            return self
        def fetchone(self):return(json.dumps(dict(cap=1000000000,active_cap=800000000)),)
    class Budget:
        ledger_id='original-ledger';producer='original-producer'
        @contextmanager
        def connect(self):yield DB()
        def require_producer(self,db):calls.append('producer-read')
    monkeypatch.setattr(probe,'load_secret_environment',lambda role:calls.append(('role',role)))
    monkeypatch.setattr(probe,'authorization',lambda:calls.append('authority-read'))
    monkeypatch.setattr(probe,'AuthorizationBudget',lambda *args,**kwargs:Budget())
    monkeypatch.setattr(probe,'sublimit_snapshot',lambda db:'existing-allocation')
    monkeypatch.setattr(probe,'usage',lambda db,line:dict(total=80472741,calls=32))
    monkeypatch.setattr(probe,'journal_state',lambda db:(1232,'a'*64))
    value=probe.snapshot()
    assert value['available_cny']=='71.9527259'
    assert value['quota_change']is False and value['new_charge_attempts']==0
    assert calls==[('role','worker'),'authority-read','one-read-transaction','producer-read']
