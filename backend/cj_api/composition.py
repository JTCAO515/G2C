"""Explicit local-only composition of pinned AUTH and MESSAGE internal modules.

No public routes, environment credentials, identity defaults, policy cache, database
provisioning, implicit repository partition or paid/provider dispatch is created here.
"""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path


class CompositionUnavailable(RuntimeError):
    pass


def _pinned_modules(*, manifest_name='composition_pins.json'):
    manifest = json.loads(Path(__file__).with_name(manifest_name).read_text())
    loaded = {}
    for source in manifest['sources']:
        prefix = Path(source['prefix'])
        package = prefix.name
        spec = importlib.util.find_spec(package)
        if spec is None or spec.origin is None:
            raise CompositionUnavailable('Pinned internal dependencies are required')
        package_root = Path(spec.origin).parent
        for filename, expected in source['files'].items():
            relative = Path(filename).relative_to(prefix)
            try:
                data = (package_root / relative).read_bytes()
            except OSError:
                raise CompositionUnavailable('Pinned internal dependencies are required') from None
            if hashlib.sha256(data).hexdigest() != expected:
                raise CompositionUnavailable('Pinned internal dependency content mismatch')
        for filename in source['files']:
            relative = Path(filename).relative_to(prefix)
            module = package if relative.name == '__init__.py' else package + '.' + relative.stem
            loaded[module] = importlib.import_module(module)
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
        modules = _pinned_modules()
    except CompositionUnavailable:
        raise
    except (ImportError, OSError, ValueError):
        raise CompositionUnavailable('Pinned internal dependencies are unavailable') from None
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
                        usage_status_configuration=None,resolve_usage_status=None):
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
    from .app import create_app
    return create_app(_message_boundary=boundary, _max_body_bytes=max_body_bytes,
                      _history_configuration=history_configuration, _history_environment=environment,
                      _memory_boundary=memory_boundary, _memory_configuration=memory_configuration,
                      _trip_boundary=trip_boundary, _trip_configuration=trip_configuration, _trip_modules=trip_modules,
                      _needs_boundary=needs_boundary, _needs_configuration=needs_configuration, _needs_modules=needs_modules,
                      _feedback_boundary=feedback_boundary, _feedback_configuration=feedback_configuration, _feedback_modules=feedback_modules,
                      _run_display_reader=run_display_reader, _run_display_configuration=run_display_configuration, _run_display_modules=run_display_modules,
                      _manual_preview_boundary=preview_boundary,_manual_preview_configuration=manual_preview_configuration,_manual_preview_modules=preview_modules,
                      _usage_status_configuration=usage_status_configuration,_usage_status_dependencies=usage_status_dependencies)
