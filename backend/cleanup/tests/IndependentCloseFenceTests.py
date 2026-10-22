from cj_cleanup import core
from cj_cleanup.postgres import Repository, CommitUnknown, Unavailable

class CloseRevokes:
    def __init__(self, conn, current): self.conn, self.current = conn, current
    def __getattr__(self, name): return getattr(self.conn, name)
    def close(self):
        self.conn.close()
        self.current['allowed'] = False

def test_close_callback_revocation_withholds_committed_write(self):
    current = {'allowed': True}
    def guard(stage):
        if not current['allowed']: raise core.Denied('synthetic host revoked during close')
    fault = Repository(lambda: CloseRevokes(self.factory(),current), self.scope, guard)
    with self.assertRaises(CommitUnknown):
        fault.intent(self.op.operation_id,0,'auth_revocation','original-close-boundary')
    self.assertFalse(current['allowed'])
    self.assertEqual(self.repo.query(self.op.operation_id).steps[0].invocation,'original-close-boundary')

def test_close_callback_revocation_withholds_read(self):
    current = {'allowed': True}
    def guard(stage):
        if not current['allowed']: raise core.Denied('synthetic host revoked during close')
    fault = Repository(lambda: CloseRevokes(self.factory(),current), self.scope, guard)
    with self.assertRaises((core.Denied, Unavailable)):
        fault.query(self.op.operation_id)
    self.assertFalse(current['allowed'])

