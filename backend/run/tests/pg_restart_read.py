"""Read original committed fixture after explicit private-cluster clean restart."""
from pg_checks import connect, repository
from cj_run.core import Binding
scope='__main__.PgTests.test_persisted_rebuild_duplicate_and_cancel'
binding=Binding(scope,'chat','gen','m1','r1',1)
with connect() as c:
    assert c.execute('SHOW listen_addresses').fetchone()[0] == ''
r=repository(scope).recover(binding)
assert (r.state.status,r.state.sequence,r.state.text,r.state.effects,r.action)==(
    'cancelled',4,'partial',('fixture-receipt',),'terminal')
print('PASS: original binding, cancelled terminal, partial text and committed receipt after clean PostgreSQL restart')
print('UNRUN: worker crash, abrupt database crash, machine power loss, real provider or AUTH')
