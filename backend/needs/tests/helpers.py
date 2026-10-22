import json
from dataclasses import asdict
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import (CJAccessFacts, Fact, TrustedPrincipal,
                                VerificationResult, VerificationStatus)
from cj_needs import Boundary, Command


def known(value): return {'state': 'known', 'value': value}
def unknown(): return {'state': 'unknown'}
def event(date='2026-11-02', time='09:30', zone='Asia/Shanghai'):
    return {'date': known(date) if date else unknown(), 'time': known(time) if time else unknown(),
            'timezone': known(zone) if zone else unknown(), 'place': unknown()}


def command(aid='a1', version=0, changes=None, text='我们三人 / three travellers', needs_id='n1'):
    return Command(json.dumps(dict(action_id=aid, needs_id=needs_id, expected_version=version,
                                   source={'kind': 'manual', 'text': text},
                                   changes=changes if changes is not None else {'party_size': known(3)}),
                              ensure_ascii=False).encode())


class Identity:
    def __init__(self): self.subject, self.allowed = 'synthetic-a', True
    def verify(self, token):
        return VerificationResult(VerificationStatus.VALID,
                                  TrustedPrincipal('synthetic-only', self.subject, 'cj013-test', 1, 1, 9999999999))
    def evaluate(self, principal):
        return CJAccessFacts(principal, Fact.YES if self.allowed else Fact.NO, Fact.YES, Fact.YES)


def host(pg, scope, identity=None, connect=None):
    identity = identity or Identity()
    checker = AdmissionChecker(identity, identity)
    boundary = Boundary(checker, lambda principal: (connect or pg.connect, scope))
    return boundary, identity


def call(boundary, method, *args):
    def encode(op):
        value = getattr(op, method)(*args)
        if value is None: return b'null'
        if hasattr(value, 'content'):
            out = asdict(value)
            out['content'] = json.loads(out['content'])
            if 'original_input' in out: out['original_input'] = out['original_input'].decode()
        else: out = asdict(value)
        return json.dumps(out, ensure_ascii=False).encode()
    return json.loads(boundary.with_operation('synthetic-test-token', encode))
