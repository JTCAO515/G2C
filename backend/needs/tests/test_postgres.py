from concurrent.futures import ThreadPoolExecutor
import json
import threading
import pytest
from cj_needs import Command, Conflict, Denied, InvalidInput, OperationWithheld
from helpers import call, command, event, host, known, Identity


def test_bilingual_exact_bytes_replay_and_conflict(pg, scope):
    b, _ = host(pg, scope)
    c = command(text='三人，预算未定 / three people, budget unknown')
    first = call(b, 'act', c)
    assert first == call(b, 'act', c)
    assert first == call(b, 'query_action', c.action_id)
    rev = call(b, 'revision', 'n1', 1)
    assert rev['original_input'].encode() == c.raw
    assert rev['source_kind'] == 'user_provided'
    altered = Command(json.dumps(c.data, ensure_ascii=True, separators=(',', ':')).encode())
    with pytest.raises(Conflict): call(b, 'act', altered)
    assert call(b, 'detail', 'n1')['version'] == 1


def test_corrections_partial_budget_and_history(pg, scope):
    b, _ = host(pg, scope)
    call(b, 'act', command(changes={'arrival':event(None,None,None),
         'budget_currency':{'state':'uncertain','note':'USD or CNY?'}, 'budget_total':known('1800.25'),
         'budget_paid':{'state':'unknown'}, 'budget_basis':known('total'),
         'budget_includes':known(['hotel', 'excludes international airfare'])}))
    call(b, 'act', command('correction',1,{'budget_currency':known('USD'),'party_size':known(2)}))
    current = call(b, 'detail', 'n1')
    assert current['content']['arrival']['date'] == {'state':'unknown'}
    assert current['content']['budget_total'] == known('1800.25')
    assert current['content']['budget_paid'] == {'state':'unknown'}
    assert 'budget_per_person' not in current['content']
    assert call(b, 'revision', 'n1', 1)['content']['budget_currency']['state'] == 'uncertain'
    with pytest.raises(Conflict): call(b,'act',command('late-context',1,{'party_size':known(9)}))
    assert call(b,'query_action','late-context') is None


def test_user_and_local_companion_isolation(pg, scope):
    a, _ = host(pg, scope)
    other_scope = scope + '-b'
    with pg.connect() as conn: conn.execute('INSERT INTO cj_needs_scope VALUES (%s)', (other_scope,))
    identity = Identity(); identity.subject = 'synthetic-b'
    b, _ = host(pg, other_scope, identity)
    items = [{'item_id':'hotel1','kind':'hotel','description':'用户称已订 / user reports booking',
              'applies_to':['companion:mother'],'locked':known(True),'start':event(),'end':event(),
              'booking_status':known('booked')}]
    fields = {'companions':{'mother':'母亲 / mother'},'fixed_items':items,
              'temporary_conditions':[{'condition_id':'leg','applies_to':['companion:mother'],'description':'本次腿伤 / injury this trip'}]}
    call(a,'act',command(changes=fields))
    assert call(b,'detail','n1') is None
    assert call(b,'revision','n1',1) is None
    assert call(b,'query_action','a1') is None
    with pytest.raises(InvalidInput): call(b,'act',command(changes={'fixed_items':items}))
    assert call(b,'detail','n1') is None
    # Companion IDs are local descriptive identities, not another account's identity.
    call(b,'act',command(changes={'companions':{'mother':'different mother'}}))
    assert call(a,'detail','n1')['content'] == fields
    with pytest.raises(InvalidInput): call(a,'act',command('remove-ref',1,{'companions':{}}))
    assert call(a,'revision','n1',1)['source_kind'] == 'user_provided'
    assert call(a,'detail','n1')['content']['fixed_items'][0]['locked'] == known(True)


def test_cas_concurrent_one_winner_and_duplicate_replay(pg, scope):
    b, _ = host(pg, scope)
    barrier = threading.Barrier(2)
    def save(aid):
        barrier.wait()
        try: return call(b,'act',command(aid))
        except Conflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['left','right']))
    assert sum(isinstance(r,dict) for r in results) == 1
    assert results.count('conflict') == 1
    assert call(b,'detail','n1')['version'] == 1
    winner = next(r['action_id'] for r in results if isinstance(r,dict))
    with ThreadPoolExecutor(max_workers=2) as pool:
        replays = list(pool.map(lambda _: call(b,'act',command(winner)), range(2)))
    assert replays[0] == replays[1]


class ConnectionFault:
    def __init__(self, conn, commit='ok', close=False): self.conn, self.mode, self.close_fault = conn, commit, close
    def __getattr__(self, name): return getattr(self.conn,name)
    def commit(self):
        if self.mode == 'before': raise OSError('synthetic before commit')
        self.conn.commit()
        if self.mode == 'ack': raise OSError('synthetic lost commit ACK')
        if self.mode == 'cancel': raise KeyboardInterrupt()
    def close(self):
        self.conn.close()
        if self.close_fault: raise KeyboardInterrupt()


@pytest.mark.parametrize('mode,exists', [('before',False),('ack',True),('cancel',True)])
def test_commit_failure_cancel_unknown_original_action(pg, scope, mode, exists):
    broken, _ = host(pg,scope,connect=lambda: ConnectionFault(pg.connect(),mode))
    original = command('original')
    with pytest.raises(OperationWithheld) as err: call(broken,'act',original)
    assert err.value.action_id == 'original'
    assert err.value.commit_possible is True
    assert err.value.recovery == 'reconcile_original'
    restored, _ = host(pg,scope)
    assert (call(restored,'query_action','original') is not None) == exists
    assert (call(restored,'detail','n1') is not None) == exists
    if exists: assert call(restored,'act',original)['version'] == 1


def test_restart_persisted_snapshot_source_receipt(pg, scope):
    b, _ = host(pg,scope)
    c = command('restart',changes={'arrival':event(),'budget_currency':known('EUR')})
    receipt = call(b,'act',c)
    before = call(b,'detail','n1')
    pg.restart()
    after, _ = host(pg,scope)
    assert call(after,'detail','n1') == before
    assert call(after,'query_action','restart') == receipt
    assert call(after,'revision','n1',1)['original_input'].encode() == c.raw


def test_auth_flip_before_commit_rolls_back(pg, scope):
    identity = Identity()
    class Flip:
        def __init__(self): self.count=0
        def check(self,token):
            self.count += 1
            if self.count == 4: identity.allowed=False
            return checker.check(token)
    from cj_auth.admission import AdmissionChecker
    checker=AdmissionChecker(identity,identity)
    b, _ = host(pg,scope,identity); b.checker=Flip()
    with pytest.raises(Denied): call(b,'act',command())
    good, _ = host(pg,scope)
    assert call(good,'query_action','a1') is None
    assert call(good,'detail','n1') is None


def test_serialization_account_change_withholds_committed_result(pg, scope):
    b, identity = host(pg,scope)
    def callback(op):
        op.act(command('serialization'))
        identity.subject='new-account'
        return b'private result'
    with pytest.raises(OperationWithheld) as err: b.with_operation('synthetic',callback)
    assert err.value.commit_possible and err.value.action_id == 'serialization'
    good, _ = host(pg,scope)
    assert call(good,'query_action','serialization')['version'] == 1


def test_lifetime_caught_failure_and_async_rejected(pg, scope):
    b, _ = host(pg,scope)
    escaped=[]
    b.with_operation('synthetic',lambda op: escaped.append(op) or b'{}')
    with pytest.raises(OperationWithheld): escaped[0].detail('n1')
    def caught(op):
        try: op.act(command(version=99))
        except Conflict: pass
        return b'pretend success'
    with pytest.raises(Denied): b.with_operation('synthetic',caught)
    async def later(op): return b'{}'
    with pytest.raises(TypeError): b.with_operation('synthetic',later)


def test_cancellation_after_commit_and_late_close_preserve_receipt(pg, scope):
    b, _ = host(pg,scope,connect=lambda: ConnectionFault(pg.connect(),close=True))
    with pytest.raises(OperationWithheld) as err: call(b,'act',command('close-cancel'))
    assert err.value.commit_possible
    good, _ = host(pg,scope)
    assert call(good,'query_action','close-cancel')['version'] == 1


def test_reject_caller_active_transaction_without_rollback(pg, scope):
    conn=pg.connect(); conn.execute('SELECT 1')
    class Borrowed:
        closed_by_adapter=False
        def __getattr__(self,name): return getattr(conn,name)
        def rollback(self): raise AssertionError('must not roll back caller work')
        def close(self): self.closed_by_adapter=True
    borrowed=Borrowed()
    b,_=host(pg,scope,connect=lambda:borrowed)
    try:
        with pytest.raises(Denied): call(b,'detail','n1')
        assert conn.info.transaction_status != 0
        assert borrowed.closed_by_adapter
    finally: conn.rollback(); conn.close()


def test_query_cancellation_preserves_original_id(pg, scope):
    good,_=host(pg,scope)
    call(good,'act',command('recover-original'))
    broken,_=host(pg,scope,connect=lambda: ConnectionFault(pg.connect(),'cancel'))
    with pytest.raises(OperationWithheld) as err: call(broken,'query_action','recover-original')
    assert err.value.action_id == 'recover-original'
    assert err.value.recovery == 'reconcile_original'
    assert call(good,'query_action','recover-original')['version'] == 1


def test_changed_binding_after_resolve_and_serialized_read_denied(pg, scope):
    b,identity=host(pg,scope)
    original_resolve=b.resolve
    def changing(principal):
        b.resolve=lambda _: (pg.connect,scope)
        return original_resolve(principal)
    b.resolve=changing
    with pytest.raises(Denied): call(b,'act',command())
    good,identity=host(pg,scope)
    call(good,'act',command())
    def encode(op):
        op.detail('n1')
        identity.allowed=False
        return b'private content'
    with pytest.raises(Denied): good.with_operation('synthetic',encode)


def test_cancel_during_transaction_rolls_back_atomically(pg, scope):
    good,_=host(pg,scope)
    c=command('precommit-cancel')
    from cj_auth.admission import AdmissionChecker
    identity=Identity(); checker=AdmissionChecker(identity,identity)
    class Cancel:
        count=0
        def check(self,token):
            self.count+=1
            if self.count==4: raise KeyboardInterrupt()
            return checker.check(token)
    broken,_=host(pg,scope); broken.checker=Cancel()
    with pytest.raises(OperationWithheld) as err: call(broken,'act',c)
    assert err.value.action_id == c.action_id
    assert err.value.commit_possible is False
    assert err.value.recovery == 'reconcile_original'
    assert call(good,'detail','n1') is None
    assert call(good,'query_action',c.action_id) is None


def test_unknown_identity_and_unconfigured_boundary_fail_closed(pg, scope):
    from cj_auth.interfaces import VerificationResult, VerificationStatus
    from cj_needs import Boundary
    class Unknown(Identity):
        def verify(self,token): return VerificationResult(VerificationStatus.UNKNOWN)
    b,_=host(pg,scope,Unknown())
    with pytest.raises(Denied): call(b,'detail','n1')
    with pytest.raises(Denied): call(Boundary(),'detail','n1')
