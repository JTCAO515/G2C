"""DB-API adapter. Factory supplies fresh non-autocommit connections; no DSN defaults."""
from contextlib import contextmanager
import hashlib
from .domain import Command, Receipt, Item, Conflict, Unavailable, CommitUnknown, current_context

class Repository:
    def __init__(self, connect, scope, *, transaction_binder=None, typed_context=False):
        if type(scope) is not str or not scope.strip(): raise ValueError('trusted scope required')
        self.connect, self.scope = connect, scope
        self.transaction_binder = transaction_binder
        self.typed_context = typed_context

    @contextmanager
    def transaction(self):
        conn, cur = self.connect(), None
        try:
            if conn.autocommit: raise ValueError('autocommit forbidden')
            cur = conn.cursor()
            cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            if self.transaction_binder is not None:
                self.transaction_binder(conn, cur)
            try: yield Transaction(cur, self.scope, typed_context=self.typed_context)
            except BaseException:
                try: conn.rollback()
                except BaseException: pass
                raise
            else:
                try: conn.commit()
                except BaseException: raise CommitUnknown('query original operation') from None
        finally:
            # Cleanup cannot turn a durable commit into a failed save or mask unknown ACK.
            for resource in (cur, conn):
                if resource is not None:
                    try: resource.close()
                    except BaseException: pass

class Transaction:
    def __init__(self, cur, scope, *, typed_context=False):
        self.cur, self.scope, self.typed_context = cur, scope, typed_context

    def _context(self, context):
        from .typed import ContextRef
        if context is None:
            return None, None
        if type(context) is str:
            return 'legacy', context
        if self.typed_context and type(context) is ContextRef:
            return context.kind, context.id
        raise Unavailable('explicit typed storage/context required')

    def _item(self, row):
        if not self.typed_context:
            return Item(Command.parse(bytes(row[0])),*row[1:])
        from .typed import parse_stored
        command = parse_stored(bytes(row[0]))
        expected = (command.context_kind,command.item_id,command.subject,command.slot,
                    command.extent,command.context_id or '',command.source_id,command.source_version)
        if row[4:] != expected:
            raise Unavailable('stored memory projection mismatch')
        return Item(command,*row[1:4])

    def _columns(self, prefix=''):
        names = ['original_input','version','status','recorded_at']
        if self.typed_context:
            names += ['context_kind','item_id','subject','slot','extent','context_id','source_id','source_version']
        return ','.join(prefix+name for name in names)
    def lock_scope(self):
        self.cur.execute('SELECT epoch FROM cj_memory_scope WHERE scope=%s AND active FOR UPDATE', (self.scope,))
        row = self.cur.fetchone()
        if row is None: raise Unavailable('scope unavailable')
        return row[0]
    def operation(self, oid):
        self.cur.execute('SELECT original_input,operation_id,item_id,version,status FROM cj_memory_operation WHERE scope=%s AND operation_id=%s', (self.scope,oid))
        row = self.cur.fetchone()
        return (bytes(row[0]),Receipt(*row[1:], hashlib.sha256(bytes(row[0])).hexdigest())) if row else None
    def source(self, c):
        self.cur.execute('SELECT approved_input,confirmed,semantic_resolved FROM cj_memory_source WHERE scope=%s AND source_id=%s AND version=%s AND authorized AND active AND expires_at>clock_timestamp() FOR UPDATE', (self.scope,c.source_id,c.source_version))
        row = self.cur.fetchone()
        if row is None or bytes(row[0]) != c.raw: raise Unavailable('source not authorized')
        return row[1] and row[2]
    def create_manual_source(self, c, resolved, expires_at):
        # Service-generated source only. Never reactivate/overwrite a pre-existing row.
        self.cur.execute("INSERT INTO cj_memory_source(scope,source_id,version,approved_input,authorized,confirmed,semantic_resolved,active,expires_at) VALUES (%s,%s,1,%s,true,%s,%s,true,%s) ON CONFLICT(scope,source_id) DO NOTHING", (self.scope,c.source_id,c.raw,c.kind != 'inference',resolved,expires_at))
        if self.cur.rowcount != 1:
            raise Conflict('manual source already exists without original receipt')

    def insert(self, c, status, *, operation_raw=None):
        if c.schema_version == 2 and not self.typed_context:
            raise Unavailable('typed storage not enabled')
        context_filter = ' AND context_kind=%s' if self.typed_context else ''
        args = (self.scope,c.item_id,c.subject,c.slot,c.extent,c.context_id or '',status)
        if self.typed_context:
            args += (c.context_kind,)
        self.cur.execute('SELECT 1 FROM cj_memory_item WHERE scope=%s AND (item_id=%s OR (subject=%s AND slot=%s AND extent=%s AND context_id=%s AND status=\'active\' AND %s=\'active\''+context_filter+'))', args)
        if self.cur.fetchone(): raise Conflict('item or canonical slot exists; review current version')
        columns='scope,item_id,version,status,subject,slot,extent,context_id,source_id,source_version,original_input'
        placeholders='%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s'
        values=(self.scope,c.item_id,status,c.subject,c.slot,c.extent,c.context_id or '',c.source_id,c.source_version,c.raw)
        if self.typed_context:
            columns+=',context_kind'; placeholders+=',%s'; values+=(c.context_kind,)
        self.cur.execute('INSERT INTO cj_memory_item('+columns+') VALUES ('+placeholders+')',values)
        self.cur.execute('INSERT INTO cj_memory_operation VALUES (%s,%s,%s,%s,1,%s)', (self.scope,c.operation_id,c.raw if operation_raw is None else operation_raw,c.item_id,status))
        self.cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s', (self.scope,))
        # Read back the actual operation ledger bytes, not the request or derived item.
        stored = self.operation(c.operation_id)
        if stored is None: raise Unavailable("operation receipt missing")
        return stored[1]
    def detail(self, iid):
        self.cur.execute('SELECT '+self._columns()+' FROM cj_memory_item WHERE scope=%s AND item_id=%s', (self.scope,iid))
        row = self.cur.fetchone()
        return self._item(row) if row else None
    def groups(self):
        self.cur.execute('SELECT subject,status,count(*) FROM cj_memory_item WHERE scope=%s GROUP BY subject,status ORDER BY subject,status', (self.scope,))
        return self.cur.fetchall()
    def list_items(self, after, limit):
        self.cur.execute('SELECT '+self._columns()+' FROM cj_memory_item WHERE scope=%s AND (%s::text IS NULL OR item_id COLLATE "C">%s COLLATE "C") ORDER BY item_id COLLATE "C" ASC LIMIT %s', (self.scope,after,after,limit))
        return [self._item(row) for row in self.cur.fetchall()]

    def require_current(self, context, subject, context_id=None):
        # Caller retains this transaction/lock through RUN publication. Expiry must
        # be checked as well as epochs: wall-clock passage does not bump an epoch.
        if current_context(self, subject, context_id) != context:
            raise Conflict("context or source validity changed")

    def effective(self, subject, context_id):
        kind, identifier = self._context(context_id)
        context_filter = ' AND i.context_kind=%s' if self.typed_context else ''
        args = (self.scope,subject,identifier)
        if self.typed_context:
            args += (kind,)
        self.cur.execute('SELECT '+self._columns('i.')+'''
        FROM cj_memory_item i JOIN cj_memory_source s ON (s.scope,s.source_id,s.version)=(i.scope,i.source_id,i.source_version)
        WHERE i.scope=%s AND i.subject=%s AND i.status='active' AND s.authorized AND s.confirmed AND s.semantic_resolved AND s.active
        AND s.expires_at>clock_timestamp() AND (i.extent='long_term' OR (i.extent='current' AND i.context_id=%s'''+context_filter+')) ORDER BY i.item_id',args)
        return [self._item(row) for row in self.cur.fetchall()]
