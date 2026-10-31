"""Local operator API: explicit actual consumer and independent current namespace."""
import psycopg
from cj_api.local_app import LocalDatabase,local_conninfo,scope_for,ISSUER
from cj_message.edit_reference import configured
from cj_message.edit_protocol import PROFILE
from cj_message.travel_reference import check_context


def activate(conninfo,subject,context,configuration,namespace):
    configured(configuration)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,edit_configuration=configuration)
    scope=scope_for(ISSUER,subject);database.require_budget_account(scope)
    with database.message_repository(scope).transaction() as tx:
        tx.lock_scope();check_context(tx.cur,scope,namespace)
    with psycopg.connect(**local_conninfo(conninfo)) as connection:
        connection.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
        if connection.execute('SELECT version FROM cj_message_context_profile WHERE scope=%s',(scope,)).fetchone()!=('message-travel.1',):
            raise ValueError('compatible original namespace profile required')
        existing=connection.execute('SELECT version FROM cj_message_edit_profile WHERE scope=%s',(scope,)).fetchone()
        if existing is not None:
            if existing!=(PROFILE,):raise ValueError('unknown edit profile')
            return 'existing'
        connection.execute('INSERT INTO cj_message_edit_profile(scope,version) VALUES(%s,%s)',(scope,PROFILE))
    return 'activated'
