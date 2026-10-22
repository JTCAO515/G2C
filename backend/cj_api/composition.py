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
                        access_provider, resolve_repository, new_run_id, max_body_bytes, history_configuration=None):
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
    from .app import create_app
    return create_app(_message_boundary=boundary, _max_body_bytes=max_body_bytes,
                      _history_configuration=history_configuration, _history_environment=environment)
