"""#182: real PG backend reuse through simulated client checkout/return leases."""
import base64
import secrets
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from fastapi.testclient import TestClient

from e2e_local import Harness, DraftToTrip, SignedTripConfirmation, CONNINFO
from cj_api.local_app import create_local_app, scope_for, ISSUER
from cj_api.composition import CompositionUnavailable
from cj_agent.draft import trip_scope_for
from cj_message.domain import Service as MessageService
from cj_trip.confirmation import ConfirmationSigner

TABLES = ('cj_message_scope', 'cj_message_chat', 'cj_message_receipt',
          'cj_message_delivery', 'cj_message_draft', 'cj_run_scope',
          'cj_run_record', 'cj_run_event', 'cj_trip_scope',
          'cj_trip_proposal', 'cj_trip_record', 'cj_trip_receipt')


class Lease:
    """Only checkout/close is simulated. Every SQL operation hits the same real PG backend."""
    def __init__(self, physical, *, autocommit):
        self.physical = physical
        self.closed = False
        physical.autocommit = autocommit
    def __getattr__(self, name): return getattr(self.physical, name)
    @property
    def autocommit(self): return self.physical.autocommit
    @autocommit.setter
    def autocommit(self, value): self.physical.autocommit = value
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self, kind, value, traceback):
        try:
            if kind is None: self.physical.commit()
            else: self.physical.rollback()
        finally: self.close()


class TransactionScopeChecks(Harness):
    draft = DraftToTrip.draft
    prepare = SignedTripConfirmation.prepare
    post_action = SignedTripConfirmation.post_action

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = create_local_app(conninfo_path=CONNINFO, auth_dir=cls.auth,
                                   confirmation_signer=ConfirmationSigner(secrets.token_bytes(32)))

    def seed(self):
        with TestClient(self.app) as client:
            for subject in ('alice', 'bob'):
                _, outcome = self.draft(client, subject, 'Synthetic scoped connection plan')
                service = MessageService(self.database.message_repository(scope_for(ISSUER, subject)), new_run_id=lambda: None)
                receipt = service.query(outcome.message_id).receipt
                service.save_draft(receipt.conversation_id, receipt.generation, b'synthetic draft', 0)
                proposal = client.get('/v1/trip-proposals', params={'proposal_id': outcome.proposal_id}, headers=self.headers(subject)).json()['proposal']
                prepared = self.prepare(client, proposal, subject=subject)
                self.assertEqual(prepared.status_code, 200)
                raw = base64.b64decode(prepared.json()['action_utf8_base64'], validate=True)
                self.assertEqual(self.post_action(client, raw, subject).status_code, 200)

    def matrix(self, rollback):
        self.seed()
        for first, second in (('alice', 'bob'), ('bob', 'alice')):
            with self.subTest(first=first, second=second, rollback=rollback):
                physical = psycopg.connect(**self.database.conninfo, autocommit=True)
                pid = physical.info.backend_pid
                leases = []
                def checkout(**kwargs):
                    lease = Lease(physical, autocommit=kwargs['autocommit']); leases.append(lease); return lease
                class Rollback(Exception): pass
                try:
                    templates = {}
                    with patch('cj_api.local_app.psycopg.connect', side_effect=checkout):
                        connection = self.database.connect(scope_for(ISSUER, first))
                    self.assertEqual(connection.info.transaction_status, TransactionStatus.IDLE)
                    try:
                        with connection as current:
                            for table in TABLES:
                                cursor = current.execute(sql.SQL('SELECT * FROM {} LIMIT 1').format(sql.Identifier(table)))
                                row = cursor.fetchone()
                                self.assertIsNotNone(row, table)  # positive data, never vacuous denial
                                columns = [column.name for column in cursor.description]
                                values = dict(zip(columns, row))
                                expected = scope_for(ISSUER, first)
                                if table.startswith('cj_trip_'): expected = trip_scope_for(expected)
                                self.assertEqual(values['scope'], expected)
                                values.pop('list_sequence', None)  # GENERATED ALWAYS; let PG allocate its default
                                templates[table] = values
                            if rollback: raise Rollback()
                    except Rollback: pass
                    self.assertTrue(leases[0].closed)
                    self.assertFalse(physical.closed)
                    self.assertEqual(physical.info.backend_pid, pid)
                    self.assertEqual(physical.info.transaction_status, TransactionStatus.IDLE)
                    gucs = physical.execute("SELECT current_setting('cj.message_scope',true),current_setting('cj.trip_scope',true)").fetchone()
                    self.assertTrue(all(value in (None, '') for value in gucs))
                    # A later borrower deliberately issues SQL WITHOUT binding B.
                    for table in TABLES:
                        with self.subTest(table=table):
                            relation = sql.Identifier(table)
                            self.assertEqual(physical.execute(sql.SQL('SELECT count(*) FROM {}').format(relation)).fetchone()[0], 0)
                            self.assertEqual(physical.execute(sql.SQL('UPDATE {} SET scope=scope RETURNING scope').format(relation)).fetchall(), [])
                            values = templates[table]
                            statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(relation,
                                sql.SQL(',').join(map(sql.Identifier, values)),
                                sql.SQL(',').join(sql.Placeholder() for _ in values))
                            # Expect RLS specifically, not a duplicate/FK failure masking missing isolation.
                            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                                with physical.transaction(): physical.execute(statement, tuple(values.values()))
                    physical.rollback()
                    with patch('cj_api.local_app.psycopg.connect', side_effect=checkout):
                        following = self.database.connect(scope_for(ISSUER, second))
                    self.assertEqual(following.info.transaction_status, TransactionStatus.IDLE)
                    self.assertEqual(following.info.backend_pid, pid)
                    with following as current:
                        for table in TABLES:
                            expected = scope_for(ISSUER, second)
                            if table.startswith('cj_trip_'): expected = trip_scope_for(expected)
                            self.assertEqual(current.execute(sql.SQL('SELECT DISTINCT scope FROM {}').format(sql.Identifier(table))).fetchall(), [(expected,)])
                finally: physical.close()

    def test_commit_then_unbound_reuse_all_twelve_tables(self): self.matrix(False)
    def test_rollback_then_unbound_reuse_all_twelve_tables(self): self.matrix(True)

    def test_dirty_checkout_and_transaction_entry_close_without_overwrite(self):
        for setting in ('cj.message_scope', 'cj.trip_scope'):
            for stage in ('checkout', 'transaction'):
                with self.subTest(setting=setting, stage=stage):
                    physical = psycopg.connect(**self.database.conninfo, autocommit=True)
                    try:
                        if stage == 'transaction':
                            with patch('cj_api.local_app.psycopg.connect', return_value=physical):
                                connection = self.database.connect(scope_for(ISSUER, 'alice'))
                            physical.autocommit = True
                        physical.execute('SELECT set_config(%s,%s,false)', (setting, 'prior-scope'))
                        if stage == 'checkout':
                            with patch('cj_api.local_app.psycopg.connect', return_value=physical), self.assertRaises(CompositionUnavailable):
                                self.database.connect(scope_for(ISSUER, 'bob'))
                        else:
                            physical.autocommit = False
                            with self.assertRaises(CompositionUnavailable):
                                with connection: self.fail('dirty connection must not reach business SQL')
                        self.assertTrue(physical.closed)
                    finally: physical.close()
