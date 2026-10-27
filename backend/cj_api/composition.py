"""Explicit local-only composition of AUTH and MESSAGE internal modules.

No public routes, environment credentials, identity defaults, policy cache, database
provisioning, implicit repository partition or paid/provider dispatch is created here.
"""
import importlib


class CompositionUnavailable(RuntimeError):
    pass


# Internal modules each composition consumes. Plain imports from this repository:
# the Git commit is the pin; CI verifies the combination (ADR-0004).
MODULE_SETS = {
    'cleanup_progress': (
        'cj_auth',
        'cj_auth.interfaces',
        'cj_auth.admission',
        'cj_auth.jwt_adapter',
        'cj_auth.read_context',
        'cj_cleanup',
        'cj_cleanup.core',
        'cj_cleanup.postgres',
        'cj_cleanup.protected_progress',
    ),
    'composition': (
        'cj_auth',
        'cj_auth.admission',
        'cj_auth.interfaces',
        'cj_auth.jwt_adapter',
        'cj_message',
        'cj_message.auth_boundary',
        'cj_message.domain',
        'cj_message.postgres',
    ),
    'feasibility': (
        'cj_auth',
        'cj_auth.interfaces',
        'cj_auth.admission',
        'cj_auth.jwt_adapter',
        'cj_auth.read_context',
        'cj_needs',
        'cj_needs.boundary',
        'cj_needs.domain',
        'cj_needs.postgres',
        'cj_needs.protected_read',
        'cj_feasibility',
        'cj_feasibility.current_read',
        'cj_feasibility.protected_current',
        'cj_feasibility.validator',
    ),
    'feedback': (
        'cj_auth',
        'cj_auth.admission',
        'cj_auth.interfaces',
        'cj_auth.jwt_adapter',
        'cj_message',
        'cj_message.auth_boundary',
        'cj_message.domain',
        'cj_message.postgres',
        'cj_run',
        'cj_run.usage_binding',
        'cj_run.core',
        'cj_run.postgres',
        'cj_run.diagnostics',
        'cj_feedback.domain',
        'cj_feedback.postgres',
        'cj_feedback.sources',
        'cj_feedback.boundary',
        'cj_feedback',
    ),
    'manual_preview': (
        'cj_auth',
        'cj_auth.admission',
        'cj_auth.interfaces',
        'cj_auth.jwt_adapter',
        'cj_trip',
        'cj_trip.domain',
        'cj_trip.auth_boundary',
        'cj_trip.postgres',
        'cj_trip.operation',
        'cj_manual_edit',
        'cj_manual_edit.core',
    ),
    'memory_management': (
        'cj_auth',
        'cj_auth.interfaces',
        'cj_auth.admission',
        'cj_auth.jwt_adapter',
        'cj_auth.read_context',
        'cj_memory',
        'cj_memory.consumption',
        'cj_memory.domain',
        'cj_memory.lifecycle',
        'cj_memory.manual',
        'cj_memory.operation',
        'cj_memory.postgres',
        'cj_memory_management',
        'cj_memory_management.domain',
        'cj_memory_management.guarded',
        'cj_memory_management.postgres',
        'cj_memory_management.service',
    ),
    'memory': (
        'cj_auth',
        'cj_auth.admission',
        'cj_auth.interfaces',
        'cj_auth.jwt_adapter',
        'cj_memory',
        'cj_memory.consumption',
        'cj_memory.domain',
        'cj_memory.lifecycle',
        'cj_memory.manual',
        'cj_memory.operation',
        'cj_memory.postgres',
    ),
    'needs': (
        'cj_auth',
        'cj_auth.interfaces',
        'cj_auth.admission',
        'cj_auth.jwt_adapter',
        'cj_auth.read_context',
        'cj_needs',
        'cj_needs.boundary',
        'cj_needs.domain',
        'cj_needs.postgres',
        'cj_needs.protected_read',
    ),
    'original_usage': (
        'cj_auth',
        'cj_auth.admission',
        'cj_auth.interfaces',
        'cj_auth.jwt_adapter',
        'cj_message',
        'cj_message.auth_boundary',
        'cj_message.domain',
        'cj_message.postgres',
        'cj_run',
        'cj_run.usage_binding',
        'cj_run.core',
        'cj_run.postgres',
        'cj_run.diagnostics',
        'cj_run.display_snapshot',
        'cj_run.original_usage_read',
    ),
    'run_display': (
        'cj_auth',
        'cj_auth.admission',
        'cj_auth.interfaces',
        'cj_auth.jwt_adapter',
        'cj_message',
        'cj_message.auth_boundary',
        'cj_message.domain',
        'cj_message.postgres',
        'cj_run',
        'cj_run.usage_binding',
        'cj_run.core',
        'cj_run.postgres',
        'cj_run.diagnostics',
        'cj_run.display_snapshot',
    ),
    'session_auth': (
        'cj_auth',
        'cj_auth.interfaces',
        'cj_auth.admission',
        'cj_auth.jwt_adapter',
        'cj_auth.composition',
        'cj_auth.read_context',
        'cj_auth.session_binding',
        'cj_auth.session_admission',
    ),
    'trip': (
        'cj_auth',
        'cj_auth.admission',
        'cj_auth.interfaces',
        'cj_auth.jwt_adapter',
        'cj_trip',
        'cj_trip.domain',
        'cj_trip.auth_boundary',
        'cj_trip.postgres',
        'cj_trip.operation',
    ),
    'usage_status': (
        'cj_auth',
        'cj_auth.interfaces',
        'cj_auth.admission',
        'cj_auth.jwt_adapter',
        'cj_auth.read_context',
        'cj_usage',
        'cj_usage.core',
        'cj_usage.codec',
        'cj_usage.postgres',
        'cj_usage.read_status',
        'cj_usage.protected_status',
    ),
}


def _internal_modules(set_name='composition'):
    loaded = {}
    for module in MODULE_SETS[set_name]:
        try:
            loaded[module] = importlib.import_module(module)
        except ImportError:
            raise CompositionUnavailable('Internal dependencies are required') from None
    return loaded


def build_message_boundary(*, environment, jwt_configuration, verification_keys,
                           access_provider, resolve_repository, new_run_id):
    """Host-provided dependencies only; caller request fields cannot configure this.

    Repository resolution must bind approved environment/profile and verified
    issuer/subject to stable storage. Token timestamps are not a storage partition.
    Gate rechecks do not implement a DB-linked atomic revocation fence.
    """
    if (environment != 'local' or jwt_configuration is None or verification_keys is None
            or access_provider is None or not callable(getattr(verification_keys, 'resolve', None))
            or not callable(getattr(access_provider, 'evaluate', None))
            or not callable(resolve_repository) or not callable(new_run_id)):
        raise CompositionUnavailable('Explicit local JWT, policy and repository configuration required')
    try:
        modules = _internal_modules()
    except CompositionUnavailable:
        raise
    except (ImportError, OSError, ValueError):
        raise CompositionUnavailable('Internal dependencies are unavailable') from None
    auth = modules['cj_auth.jwt_adapter']
    if not isinstance(jwt_configuration, auth.JWTConfiguration):
        raise CompositionUnavailable('Fixed AUTH JWTConfiguration required')
    if jwt_configuration.profile is not auth.JWTProfile.STRICT_V1:
        raise CompositionUnavailable('This composition slice requires the strict JWT profile')
    verifier = auth.PyJWTVerifier(jwt_configuration, verification_keys)
    checker = modules['cj_auth.admission'].AdmissionChecker(verifier, access_provider)
    return modules['cj_message.auth_boundary'].Boundary(checker, resolve_repository, new_run_id)


def create_composed_app(*, environment, jwt_configuration, verification_keys,
                        access_provider, resolve_repository, new_run_id, max_body_bytes, history_configuration=None,
                        memory_configuration=None, resolve_memory_binding=None, memory_source_policy=None,
                        trip_configuration=None, resolve_trip=None, trip_confirmation_validator=None,
                        needs_configuration=None, resolve_needs=None,
                        feedback_configuration=None, resolve_feedback=None, resolve_feedback_run=None,
                        run_display_configuration=None, resolve_run_display=None,manual_preview_configuration=None,
                        usage_status_configuration=None,resolve_usage_status=None,
                        original_usage_configuration=None,resolve_original_usage_run=None,
                        cleanup_progress_configuration=None,resolve_cleanup_progress=None):
    """No zero-argument/public production configuration exists."""
    if type(max_body_bytes) is not int or max_body_bytes <= 0:
        raise CompositionUnavailable('Explicit positive body byte limit required')

    def checked_run_id():
        value = new_run_id()
        if not isinstance(value, str) or not value.strip():
            raise CompositionUnavailable('Host run ID factory returned invalid value')
        return value  # no trim/normalization of valid opaque IDs

    if not callable(new_run_id):
        raise CompositionUnavailable('Explicit run ID factory required')
    boundary = build_message_boundary(environment=environment, jwt_configuration=jwt_configuration,
        verification_keys=verification_keys, access_provider=access_provider,
        resolve_repository=resolve_repository, new_run_id=checked_run_id)
    from .history_config import HistoryWireConfiguration
    if history_configuration is not None and not isinstance(history_configuration,HistoryWireConfiguration):
        raise CompositionUnavailable('Explicit history configuration required')
    memory_boundary = None
    if any(value is not None for value in (memory_configuration,resolve_memory_binding,memory_source_policy)):
        from .memory_boundary import MemoryWireConfiguration, build_memory_boundary
        if type(memory_configuration) is not MemoryWireConfiguration:
            raise CompositionUnavailable('Explicit memory configuration/binding/domain policy required')
        memory_boundary = build_memory_boundary(environment=environment,jwt_configuration=jwt_configuration,
            verification_keys=verification_keys,access_provider=access_provider,
            resolve_binding=resolve_memory_binding,source_policy=memory_source_policy)
    trip_boundary = trip_modules = None
    if any(value is not None for value in (trip_configuration,resolve_trip,trip_confirmation_validator)):
        from .trip_composition import TripWireConfiguration, build_trip_boundary
        if type(trip_configuration) is not TripWireConfiguration:
            raise CompositionUnavailable('Explicit TRIP configuration/resolver required')
        trip_boundary,trip_modules = build_trip_boundary(environment=environment,jwt_configuration=jwt_configuration,
            verification_keys=verification_keys,access_provider=access_provider,
            resolve=resolve_trip,confirmation_validator=trip_confirmation_validator)
    needs_boundary = needs_modules = None
    if needs_configuration is not None or resolve_needs is not None:
        from .needs_composition import NeedsWireConfiguration, build_needs_boundary
        if type(needs_configuration) is not NeedsWireConfiguration:
            raise CompositionUnavailable('Explicit NEEDS configuration/resolver required')
        needs_boundary,needs_modules = build_needs_boundary(environment=environment,jwt_configuration=jwt_configuration,
            verification_keys=verification_keys,access_provider=access_provider,resolve=resolve_needs)
    feedback_boundary = feedback_modules = None
    if any(value is not None for value in (feedback_configuration,resolve_feedback,resolve_feedback_run)):
        from .feedback_composition import FeedbackWireConfiguration, _feedback_with_shared_message
        if type(feedback_configuration) is not FeedbackWireConfiguration:
            raise CompositionUnavailable('Explicit FEEDBACK configuration/resolver required')
        feedback_boundary,feedback_modules = _feedback_with_shared_message(boundary,resolve_feedback,resolve_feedback_run)
    run_display_reader = run_display_modules = None
    if run_display_configuration is not None or resolve_run_display is not None:
        from .run_display_composition import _attach_run_display
        run_display_reader,run_display_modules = _attach_run_display(boundary,resolve_run_display,run_display_configuration)
    preview_boundary = preview_modules = None
    if manual_preview_configuration is not None:
        if trip_boundary is None:raise CompositionUnavailable('Manual preview requires the existing configured TRIP boundary')
        from .manual_preview_composition import _attach_manual_preview
        preview_boundary,preview_modules = _attach_manual_preview(trip_boundary,manual_preview_configuration)
    usage_status_dependencies = None
    if usage_status_configuration is not None or resolve_usage_status is not None:
        from .usage_status_composition import _usage_status_from_checker
        usage_status_dependencies = _usage_status_from_checker(boundary.checker,resolve_usage_status,usage_status_configuration,
            environment=environment,issuer=jwt_configuration.issuer,audience=jwt_configuration.audience)
    original_usage_reader = original_usage_modules = None
    if original_usage_configuration is not None or resolve_original_usage_run is not None:
        from .original_usage_composition import _attach_original_usage
        original_usage_reader,original_usage_modules = _attach_original_usage(boundary,resolve_original_usage_run,original_usage_configuration)
    cleanup_progress_dependencies = None
    if cleanup_progress_configuration is not None or resolve_cleanup_progress is not None:
        from .cleanup_progress_composition import _cleanup_progress_from_checker
        cleanup_progress_dependencies = _cleanup_progress_from_checker(boundary.checker,resolve_cleanup_progress,cleanup_progress_configuration,
            environment=environment,issuer=jwt_configuration.issuer,audience=jwt_configuration.audience)
    from .app import create_app
    return create_app(_message_boundary=boundary, _max_body_bytes=max_body_bytes,
                      _history_configuration=history_configuration, _history_environment=environment,
                      _memory_boundary=memory_boundary, _memory_configuration=memory_configuration,
                      _trip_boundary=trip_boundary, _trip_configuration=trip_configuration, _trip_modules=trip_modules,
                      _needs_boundary=needs_boundary, _needs_configuration=needs_configuration, _needs_modules=needs_modules,
                      _feedback_boundary=feedback_boundary, _feedback_configuration=feedback_configuration, _feedback_modules=feedback_modules,
                      _run_display_reader=run_display_reader, _run_display_configuration=run_display_configuration, _run_display_modules=run_display_modules,
                      _manual_preview_boundary=preview_boundary,_manual_preview_configuration=manual_preview_configuration,_manual_preview_modules=preview_modules,
                      _usage_status_configuration=usage_status_configuration,_usage_status_dependencies=usage_status_dependencies,
                      _original_usage_reader=original_usage_reader,_original_usage_configuration=original_usage_configuration,_original_usage_modules=original_usage_modules,
                      _cleanup_progress_configuration=cleanup_progress_configuration,_cleanup_progress_dependencies=cleanup_progress_dependencies)


def build_verified_session_checker(*, environment, jwt_configuration, verification_keys,
                                   session_access_provider):
    """Explicit local opt-in; no real authority/target/provider is supplied by root.

    None keys/provider stays canonical UNKNOWN. A principal-only access provider
    is not a session provider and cannot be silently adapted into one.
    """
    modules = _internal_modules('session_auth')
    auth = modules['cj_auth.jwt_adapter']
    if (environment != 'local' or not isinstance(jwt_configuration, auth.JWTConfiguration)
            or jwt_configuration.profile is not auth.JWTProfile.SUPABASE_ACCESS_RC1
            or verification_keys is not None and not callable(getattr(verification_keys, 'resolve', None))
            or session_access_provider is not None and not callable(getattr(session_access_provider, 'evaluate_session', None))):
        raise CompositionUnavailable('Explicit canonical Supabase session profile/keys/session provider required')
    return modules['cj_auth.session_admission'].SessionAdmissionChecker(
        auth.PyJWTVerifier(jwt_configuration, verification_keys), session_access_provider)


def with_verified_session_read(*, checker, token, max_response_bytes, project):
    """Trusted host read only: encode final bytes in the canonical original lifetime.

    This adds no route, scope, token or authority. Existing business factories and
    legacy checker defaults are not changed. Never use it as a write/retry permit.
    """
    modules = _internal_modules('session_auth')
    if (type(checker) is not modules['cj_auth.session_admission'].SessionAdmissionChecker
            or type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 1048576):
        raise CompositionUnavailable('Explicit canonical session checker and bounded read required')
    return modules['cj_auth.read_context'].ProtectedReadBoundary(
        checker, max_response_bytes=max_response_bytes).with_read_context(token, project)
