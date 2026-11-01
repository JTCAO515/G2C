"""Explicit local operator activation of publisher2; no request grants this mode."""
import psycopg
from .local_app import LocalDatabase,local_conninfo,scope_for,ISSUER
from cj_message.edit_reference import configured
from cj_message.edit_result_protocol import EditResultConfiguration,PROFILE
from cj_message.travel_reference import check_context


def profile(cur,scope):
    cur.execute('SELECT version FROM cj_message_edit_result_profile WHERE scope=%s',(scope,))
    row=cur.fetchone()
    if row is not None and row!=(PROFILE,):raise ValueError('unsupported scoped result profile')
    return row is not None


def activate(conninfo,subject,context,configuration,namespace):
    configured(configuration)
    if type(configuration) is not EditResultConfiguration:raise ValueError('publisher2 configuration required')
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,edit_configuration=configuration)
    scope=scope_for(ISSUER,subject);database.require_budget_account(scope)
    with database.message_repository(scope).transaction() as tx:
        tx.lock_scope();check_context(tx.cur,scope,namespace)
    with psycopg.connect(**local_conninfo(conninfo)) as connection:
        connection.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
        if connection.execute('SELECT version FROM cj_message_edit_profile WHERE scope=%s',(scope,)).fetchone()!=('message-trip.2',):
            raise ValueError('original edit profile required before result activation')
        if profile(connection.cursor(),scope):return 'existing'
        connection.execute('INSERT INTO cj_message_edit_result_profile VALUES(%s,%s)',(scope,PROFILE))
    return 'activated'
