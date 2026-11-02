"""Explicit M3 local host, retaining the existing app and legacy entry points."""
from dataclasses import dataclass
import os
from pathlib import Path
import uuid

from cj_api.local_app import LocalDatabase, create_local_app, scope_for
from cj_api.local_worker_context import checker_for
from cj_api.message_source_routes import register_message_source_routes
from cj_memory.postgres import Repository
from cj_message.auth_boundary import Boundary
from .api import register_routes
from .service import Service


@dataclass(frozen=True)
class HistoryHost:
    database: LocalDatabase
    boundary: Boundary
    service: Service


def build_history_host(conninfo_path, auth_dir):
    database = LocalDatabase(conninfo_path)
    boundary = Boundary(checker_for(Path(auth_dir)),
        lambda principal: database.message_repository(scope_for(principal.issuer,principal.subject)),
        lambda: uuid.uuid4().hex)
    def resolve(principal, scope):
        return Repository(lambda:database.connect(scope),scope,
                          transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))
    return HistoryHost(database,boundary,Service(boundary,resolve))


def _install(app, host):
    register_routes(app,host.service)
    # End is an explicit user action; raw source reads have no default policy.
    # Queue processing installs its actual per-request C policy in the protected seam.
    register_message_source_routes(app,host.boundary,None)
    app.state.memory_history = host
    return app


def create_local_history_app(*,conninfo_path,auth_dir):
    return _install(create_local_app(conninfo_path=conninfo_path,auth_dir=auth_dir),
                    build_history_host(conninfo_path,auth_dir))


def app_from_environment():
    from cj_api.local_app import app_from_environment as existing_app
    app = existing_app()
    return _install(app,build_history_host(Path(os.environ['CJ_LOCAL_CONNINFO']),
                                          Path(os.environ['CJ_LOCAL_AUTH_DIR'])))
