"""Explicit native TRIP-structured-read.3; no producer or source write grant."""
from cj_api.app import create_app
from cj_api.local_app import LocalDatabase
from .local_calendar_read import _register_calendar_read_routes

VERSION = 'TRIP-structured-read.3'


def create_local_rich_read_app(*, conninfo_path, auth_dir, run_context, max_response_bytes=1_000_000):
    app = create_app()
    database = LocalDatabase(conninfo_path,run_context=run_context,travel_context=True,needs_context=True)
    register_local_rich_read_routes(app,database=database,auth_dir=auth_dir,
                                   max_response_bytes=max_response_bytes)
    return app


def register_local_rich_read_routes(app, *, database, auth_dir,
                                   max_response_bytes=1_000_000, selected_subjects=None):
    return _register_calendar_read_routes(app,database=database,auth_dir=auth_dir,
        max_response_bytes=max_response_bytes,selected_subjects=selected_subjects,rich=True)
