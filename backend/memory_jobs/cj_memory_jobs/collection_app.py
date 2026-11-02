"""Explicit collection host; policies are trusted objects, never request JSON."""
from pathlib import Path
import uuid

from cj_api.local_app import LocalDatabase,create_local_app,scope_for
from cj_api.local_worker_context import checker_for
from cj_api.message_source_routes import register_message_source_routes
from cj_memory.postgres import Repository
from cj_message.auth_boundary import Boundary
from .api import register_routes
from .collection import CollectionService
from .local_app import HistoryHost


def create_collection_app(*,conninfo_path,auth_dir,resolve_collection):
    database=LocalDatabase(conninfo_path,travel_context=True)
    boundary=Boundary(checker_for(Path(auth_dir)),
        lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),
        lambda:uuid.uuid4().hex)
    def resolve(principal,scope):
        return Repository(lambda:database.connect(scope),scope,typed_context=True,
            transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))
    service=CollectionService(boundary,resolve,resolve_collection)
    app=create_local_app(conninfo_path=conninfo_path,auth_dir=auth_dir)
    register_routes(app,service,collection=True)
    register_message_source_routes(app,boundary,None)
    app.state.memory_history=HistoryHost(database,boundary,service)
    return app
