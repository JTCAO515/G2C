"""MESSAGE-SOURCE@2: same-principal MESSAGE → TRAVEL → C MEMORY lease."""
from .domain import Unavailable
from .source import _with_locked_source
from .travel_reference import MessageContextAuthority

VERSION='MESSAGE-SOURCE@2'


def with_source_and_travel(service,principal,query,policy,selection,admit,project):
    if policy is None:raise Unavailable('source unavailable')
    authority=MessageContextAuthority(service.repository,admit)
    with service.repository.transaction() as tx:
        tx.lock_scope()
        with authority._hold_current_locked(tx,principal,selection) as travel:
            result=_with_locked_source(tx,principal,query,policy,lambda source:project(source,travel))
    return result
