"""Separately authorized cleanup login for the specified synthetic test project.

The ordinary local cleanup profile cannot substitute a role in a runtime URI.
This profile requires the independently issued cleanup credential, verified TLS
and reset, and the deployment transaction barrier before any cleanup authority.
"""
from dataclasses import dataclass
from contextlib import nullcontext
from pathlib import Path

import psycopg

from cj_cleanup.store import Store
from .local_cleanup import Configuration,Runtime
from .supabase_test_database import (
    decode_cleanup_uri,decode_hk_socket_uri,pin_ca,prepare_hk_socket_session,prepare_owned_session,
)


@dataclass(frozen=True,repr=False)
class SupabaseCleanupConfiguration:
    configuration:Configuration
    uri:str
    ca_file:Path
    transaction_guard:object
    local_socket:bool=False

    def __post_init__(self):
        if type(self.configuration) is not Configuration or self.transaction_guard is None:
            raise ValueError('explicit_synthetic_cleanup_inventory_required')


class SupabaseCleanupRuntime(Runtime):
    def __init__(self,database,configuration,scope_for):
        super().__init__(database,configuration.configuration,scope_for)
        self.local_socket=configuration.local_socket
        self.connection_options=(decode_hk_socket_uri(configuration.uri,'cj_local_cleanup')
            if self.local_socket else decode_cleanup_uri(configuration.uri))
        self.ca_file=configuration.ca_file
        self.transaction_guard=configuration.transaction_guard

    def connect(self):
        with (nullcontext() if self.local_socket else pin_ca(self.ca_file)) as ca:
            options=self.connection_options if self.local_socket else dict(self.connection_options,sslrootcert=ca.name)
            connection=psycopg.connect(**options,autocommit=True,prepare_threshold=None)
            try:
                prepare=prepare_hk_socket_session if self.local_socket else prepare_owned_session
                prepare(connection,'cj_local_cleanup')
                properties=connection.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolinherit,"
                    "EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=r.oid),"
                    "EXISTS(SELECT 1 FROM pg_catalog.pg_class WHERE relowner=r.oid) FROM pg_catalog.pg_roles r WHERE rolname=current_user").fetchone()
                if properties!=(False,)*8:
                    raise ValueError('restricted_cleanup_login_required')
                connection.autocommit=False
                return connection
            except BaseException:
                connection.close()
                raise

    def store(self,subject):
        return Store(self.connect,subject,lambda stage:None,before_transaction=self.transaction_guard)
