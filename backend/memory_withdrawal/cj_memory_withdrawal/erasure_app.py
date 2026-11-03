"""Candidate explicit local host; missing B item hooks does not install deletion."""
from cj_memory_jobs.collection_app import create_decision_collection_app
from cj_api.local_cleanup import Runtime
from cj_api.local_app import scope_for
from .erasure_service import ErasureService
from .erasure_api import register


def create_erasure_app(*,conninfo_path,auth_dir,resolve_collection,cleanup_configuration,resolve_backend_hooks,run_context=None):
    return _create(conninfo_path,auth_dir,resolve_collection,cleanup_configuration,resolve_backend_hooks,run_context,ErasureService,{})


def create_erasure_app_v2(*,conninfo_path,auth_dir,resolve_collection,cleanup_configuration,resolve_backend_hooks,hold_payloads,run_context=None):
    from .erasure_driver_v2 import ErasureServiceV2
    return _create(conninfo_path,auth_dir,resolve_collection,cleanup_configuration,resolve_backend_hooks,run_context,
                   ErasureServiceV2,dict(hold_payloads=hold_payloads))


def _create(conninfo_path,auth_dir,resolve_collection,cleanup_configuration,resolve_backend_hooks,run_context,service_type,options):
    if resolve_backend_hooks is None:raise ValueError('explicit real B item-cleanup hooks required')
    app=create_decision_collection_app(conninfo_path=conninfo_path,auth_dir=auth_dir,resolve_collection=resolve_collection,run_context=run_context)
    host=app.state.memory_history
    runtime=Runtime(host.database,cleanup_configuration,scope_for)
    service=service_type(host.service,runtime,resolve_backend_hooks,max_sources=1000,max_jobs=1000,max_association_bytes=1_000_000,**options)
    register(app,service);app.state.memory_erasure=service
    return app
