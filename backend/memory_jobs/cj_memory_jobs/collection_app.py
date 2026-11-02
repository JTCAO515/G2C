"""Explicit collection host; policies are trusted objects, never request JSON."""
from pathlib import Path
import uuid

from cj_api.local_app import LocalDatabase,create_local_app,scope_for
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.message_source_routes import register_message_source_routes
from cj_memory.postgres import Repository
from cj_message.auth_boundary import Boundary
from .api import register_routes
from .collection import CollectionService
from .local_app import HistoryHost


def create_collection_app(*,conninfo_path,auth_dir,resolve_collection,run_context=None):
    return _collection_app(conninfo_path,auth_dir,resolve_collection,run_context,decisions=False)


def create_decision_collection_app(*,conninfo_path,auth_dir,resolve_collection,run_context=None):
    return _collection_app(conninfo_path,auth_dir,resolve_collection,run_context,decisions=True)


def _collection_app(conninfo_path,auth_dir,resolve_collection,run_context,*,decisions):
    database=LocalDatabase(conninfo_path,run_context=run_context,travel_context=True)
    boundary=Boundary(account_checker_for(Path(auth_dir),database),
        lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),
        lambda:uuid.uuid4().hex)
    def resolve(principal,scope):
        return Repository(lambda:database.connect(scope),scope,typed_context=True,
            transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))
    if decisions:
        from cj_trip.auth_boundary import Boundary as TripBoundary
        from cj_trip.decision_lease import DecisionAuthority
        from cj_agent.draft import trip_scope_for
        from .decision_service import DecisionCollectionService
        def trip_resolve(principal):
            owner=scope_for(principal.issuer,principal.subject)
            return lambda:database.connect(owner),trip_scope_for(owner)
        trip=TripBoundary(boundary.checker,trip_resolve,structured=True)
        service=DecisionCollectionService(boundary,resolve,resolve_collection,
            resolve_decision_authority=lambda token:DecisionAuthority(trip,token))
    else:service=CollectionService(boundary,resolve,resolve_collection)
    app=create_local_app(conninfo_path=conninfo_path,auth_dir=auth_dir,run_context=run_context,
                         travel_context=run_context is not None)
    register_routes(app,service,collection=True)
    if decisions:
        from .decision_api import register
        register(app,service)
    register_message_source_routes(app,boundary,None)
    app.state.memory_history=HistoryHost(database,boundary,service)
    return app
