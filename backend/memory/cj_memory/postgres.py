"""DB-API adapter. Factory supplies fresh non-autocommit connections; no DSN defaults."""
from contextlib import contextmanager
from .domain import Command, Receipt, Item, Conflict, Unavailable, CommitUnknown

class Repository:
    def __init__(self, connect, scope):
        if type(scope) is not str or not scope.strip(): raise ValueError('trusted scope required')
        self.connect, self.scope = connect, scope

    @contextmanager
    def transaction(self):
        conn, cur = self.connect(), None
        try:
            if conn.autocommit: raise ValueError('autocommit forbidden')
            cur = conn.cursor()
            cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            try: yield Transaction(cur, self.scope)
            except BaseException:
                try: conn.rollback()
                except BaseException: pass
                raise
            else:
                try: conn.commit()
                except Exception: raise CommitUnknown('query original operation') from None
        finally:
            # Cleanup cannot turn a durable commit into a failed save or mask unknown ACK.
            for resource in (cur, conn):
                if resource is not None:
                    try: resource.close()
                    except BaseException: pass

class Transaction:
    def __init__(self, cur, scope): self.cur, self.scope = cur, scope
    def lock_scope(self):
        self.cur.execute('SELECT epoch FROM cj_memory_scope WHERE scope=%s AND active FOR UPDATE', (self.scope,))
        row = self.cur.fetchone()
        if row is None: raise Unavailable('scope unavailable')
        return row[0]
    def operation(self, oid):
        self.cur.execute('SELECT original_input,operation_id,item_id,version,status FROM cj_memory_operation WHERE scope=%s AND operation_id=%s', (self.scope,oid))
        row = self.cur.fetchone()
        return (bytes(row[0]),Receipt(*row[1:])) if row else None
    def source(self, c):
        self.cur.execute('SELECT approved_input,confirmed,semantic_resolved FROM cj_memory_source WHERE scope=%s AND source_id=%s AND version=%s AND authorized AND active AND expires_at>clock_timestamp() FOR UPDATE', (self.scope,c.source_id,c.source_version))
        row = self.cur.fetchone()
        if row is None or bytes(row[0]) != c.raw: raise Unavailable('source not authorized')
        return row[1] and row[2]
    def insert(self, c, status):
        self.cur.execute('SELECT 1 FROM cj_memory_item WHERE scope=%s AND (item_id=%s OR (subject=%s AND slot=%s AND extent=%s AND context_id=%s AND status=\'active\' AND %s=\'active\'))', (self.scope,c.item_id,c.subject,c.slot,c.extent,c.context_id or '',status))
        if self.cur.fetchone(): raise Conflict('item or canonical slot exists; review current version')
        self.cur.execute('INSERT INTO cj_memory_item(scope,item_id,version,status,subject,slot,extent,context_id,source_id,source_version,original_input) VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s)', (self.scope,c.item_id,status,c.subject,c.slot,c.extent,c.context_id or '',c.source_id,c.source_version,c.raw))
        self.cur.execute('INSERT INTO cj_memory_operation VALUES (%s,%s,%s,%s,1,%s)', (self.scope,c.operation_id,c.raw,c.item_id,status))
        self.cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s', (self.scope,))
        return Receipt(c.operation_id,c.item_id,1,status)
    def detail(self, iid):
        self.cur.execute('SELECT original_input,version,status,recorded_at FROM cj_memory_item WHERE scope=%s AND item_id=%s', (self.scope,iid))
        row = self.cur.fetchone()
        return Item(Command.parse(bytes(row[0])),*row[1:]) if row else None
    def groups(self):
        self.cur.execute('SELECT subject,status,count(*) FROM cj_memory_item WHERE scope=%s GROUP BY subject,status ORDER BY subject,status', (self.scope,))
        return self.cur.fetchall()
    def list_items(self, after, limit):
        self.cur.execute('SELECT original_input,version,status,recorded_at FROM cj_memory_item WHERE scope=%s AND (%s::text IS NULL OR item_id COLLATE "C">%s COLLATE "C") ORDER BY item_id COLLATE "C" ASC LIMIT %s', (self.scope,after,after,limit))
        return [Item(Command.parse(bytes(r[0])),*r[1:]) for r in self.cur.fetchall()]

    def require_current(self, context, subject, context_id=None):
        # Caller retains this transaction/lock through RUN publication. Expiry must
        # be checked as well as epochs: wall-clock passage does not bump an epoch.
        if self.lock_scope() != context.epoch: raise Conflict("context changed")
        rows = self.effective(subject, context_id)
        selected = {i.command.slot: i for i in rows if i.command.extent == "long_term"}
        selected.update({i.command.slot: i for i in rows if i.command.extent == "current"})
        if tuple(selected[k] for k in sorted(selected)) != context.items:
            raise Conflict("source validity changed")

    def effective(self, subject, context_id):
        self.cur.execute('''SELECT i.original_input,i.version,i.status,i.recorded_at
        FROM cj_memory_item i JOIN cj_memory_source s ON (s.scope,s.source_id,s.version)=(i.scope,i.source_id,i.source_version)
        WHERE i.scope=%s AND i.subject=%s AND i.status='active' AND s.authorized AND s.confirmed AND s.semantic_resolved AND s.active
        AND s.expires_at>clock_timestamp() AND (i.extent='long_term' OR (i.extent='current' AND i.context_id=%s)) ORDER BY i.item_id''', (self.scope,subject,context_id))
        return [Item(Command.parse(bytes(r[0])),*r[1:]) for r in self.cur.fetchall()]
