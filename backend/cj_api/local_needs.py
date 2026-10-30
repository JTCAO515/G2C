"""Canonical local NEEDS read factory; caller supplies only token and record selector."""
from cj_auth.read_context import ProtectedReadBoundary
from cj_needs.protected_read import ProtectedReader, ReadConfiguration
from cj_needs.runtime import ReadOnlyRuntimeRepository
from cj_message.needs_binding import needs_scope_for
from .local_app import AUDIENCE, ISSUER, scope_for
from .composition import CompositionUnavailable


def protected_reader(database, checker):
    def resolve(principal, environment):
        if environment!='local':raise CompositionUnavailable('local NEEDS read environment required')
        scope=scope_for(principal.issuer,principal.subject)
        return lambda:database.connect(scope),needs_scope_for(scope)
    return ProtectedReader(ProtectedReadBoundary(checker,max_response_bytes=524288),resolve,
        configuration=ReadConfiguration('local',ISSUER,AUDIENCE,524288),
        repository_factory=ReadOnlyRuntimeRepository)
