"""Read only persisted original usage references under MESSAGE bf79's context.

No Meter dependency or mutation; stored association is not proof of dispatch,
reservation, execution, fees, or current USAGE status.
"""
from dataclasses import dataclass
import inspect
import json
from cj_message.auth_boundary import Boundary, HistoryReadContext
from .core import Binding, Cursor, State
from .postgres import Repository, Recovery
from .usage_binding import UsageBinding


class UsageAssociationUnavailable(Exception):
    pass


class UsageAssociationChanged(UsageAssociationUnavailable):
    pass


class UsageAssociationTooLarge(UsageAssociationUnavailable):
    pass


@dataclass(frozen=True)
class UsageAssociationReadConfiguration:
    max_response_bytes: int

    def __post_init__(self):
        if type(self.max_response_bytes) is not int or self.max_response_bytes < 1:
            raise ValueError('explicit positive response byte limit required')


# Only direct attributes of the exact canonical class; no resolver/descriptor/IO
# is invoked by the final binding check after the last external AUTH callback.
_REPOSITORY_FIELDS = ('scope', 'connect', 'expires_at', 'statement_timeout_ms', 'lock_timeout_ms')


def _repository_fields(repository):
    if type(repository) is not Repository:
        raise UsageAssociationUnavailable('canonical RUN repository required')
    attributes = vars(repository)
    return tuple(attributes.get(name) for name in _REPOSITORY_FIELDS)


def _association(repository, binding):
    # Use the canonical public recovery implementation with explicit strict close.
    # The default legacy recovery behavior remains compatible for old consumers.
    result = Repository.recover(repository, binding, require_clean_close=True)
    if (type(result) is not Recovery or type(result.state) is not State or type(result.cursor) is not Cursor
            or result.state.binding != binding or result.cursor.binding != binding
            or type(result.cursor.epoch) is not str or not result.cursor.epoch
            or type(result.cursor.after) is not int or result.cursor.after != 0
            or type(result.cursor.through) is not int or result.cursor.through != result.state.sequence):
        raise UsageAssociationUnavailable('original RUN recovery unavailable')
    usage = result.state.usage
    if type(usage) is not UsageBinding:
        raise UsageAssociationUnavailable('original usage association unavailable')
    # Validate even a corrupted in-memory object; preserve original bytes/digest.
    try:
        checked = UsageBinding(usage.command_bytes, usage.input_bytes)
        checked.check_run(binding.run_id)
        values = checked.values()
    except (TypeError, ValueError) as exc:
        raise UsageAssociationUnavailable('invalid original usage association') from exc
    return result, checked, values


class OriginalUsageAssociationReader:
    def __init__(self, message_boundary, resolve_run_repository, *, configuration):
        if (type(message_boundary) is not Boundary or not callable(resolve_run_repository)
                or type(configuration) is not UsageAssociationReadConfiguration):
            raise ValueError('fixed MESSAGE boundary, trusted RUN resolver and explicit configuration required')
        self.message_boundary, self.resolve_run_repository = message_boundary, resolve_run_repository
        self.configuration = configuration

    def read(self, token: str, message_id: str) -> bytes:
        return self.read_projected(token, message_id, lambda body: body)

    def read_projected(self, token: str, message_id: str, project) -> bytes:
        """Trusted project receives only seven reference fields encoded as bytes.

        Host resolver is (current_trusted_principal, current_trusted_scope) -> the
        canonical RUN Repository. Approved environment is host configuration.
        project validates/encodes the final generated envelope inside this lifetime.
        """
        if type(message_id) is not str or not message_id.strip() or not callable(project):
            raise ValueError('original message ID and synchronous host projection required')
        boundary, resolver, configuration = self.message_boundary, self.resolve_run_repository, self.configuration
        if type(boundary) is not Boundary or type(configuration) is not UsageAssociationReadConfiguration:
            raise UsageAssociationUnavailable('original read configuration unavailable')
        limit = configuration.max_response_bytes
        if type(limit) is not int or limit < 1:
            raise UsageAssociationUnavailable('original read byte bound unavailable')
        completed_repository = None
        captured_fields = None

        def frozen():
            attributes = vars(self)
            if (attributes.get('message_boundary') is not boundary
                    or attributes.get('resolve_run_repository') is not resolver
                    or attributes.get('configuration') is not configuration
                    or vars(configuration).get('max_response_bytes') is not limit):
                raise UsageAssociationChanged('original reader configuration changed')
            if completed_repository is not None:
                current = _repository_fields(completed_repository)
                if any(now is not old for now, old in zip(current, captured_fields)):
                    raise UsageAssociationChanged('original RUN repository changed')

        def operation(ctx):
            nonlocal completed_repository, captured_fields
            if type(ctx) is not HistoryReadContext:
                raise UsageAssociationUnavailable('original MESSAGE context unavailable')
            frozen()
            principal, scope = ctx.principal, ctx.scope
            original = ctx.query_message(message_id)
            if original is None:
                raise UsageAssociationUnavailable('original message unavailable')
            receipt = original.receipt
            binding = Binding(scope, receipt.conversation_id, receipt.generation,
                              receipt.message_id, receipt.run_id, receipt.sequence)
            # Immutable primitive source fingerprint; never retain an escaped ctx.
            source = (original.raw, receipt.conversation_id, receipt.generation,
                      receipt.message_id, receipt.run_id, receipt.sequence, receipt.input_sha256)
            repository = resolver(principal, scope)
            if type(repository) is not Repository:
                if inspect.iscoroutine(repository):
                    repository.close()
                raise UsageAssociationUnavailable('canonical RUN repository required')
            completed_repository, captured_fields = repository, _repository_fields(repository)
            if captured_fields[0] != scope:
                raise UsageAssociationChanged('original RUN scope unavailable')

            def current_source():
                frozen()
                if ctx.principal is not principal or ctx.scope != scope:
                    raise UsageAssociationChanged('original MESSAGE binding changed')
                current = ctx.query_message(message_id)
                frozen()  # MESSAGE storage/provider/close callbacks have just finished.
                if current is None:
                    raise UsageAssociationChanged('original message changed')
                r = current.receipt
                if (current.raw, r.conversation_id, r.generation, r.message_id,
                        r.run_id, r.sequence, r.input_sha256) != source:
                    raise UsageAssociationChanged('original message changed')

            current_source()
            first, usage, values = _association(repository, binding)
            frozen()  # Canonical recovery has committed and closed before publication.
            body = json.dumps({
                'conversation_id': binding.conversation_id, 'generation': binding.generation,
                'message_id': binding.message_id, 'message_sequence': binding.message_sequence,
                'run_id': binding.run_id, 'attempt_id': values['attempt_id'], 'operation_id': values['operation_id'],
            }, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
            if len(body) > limit:
                raise UsageAssociationTooLarge('original references exceed configured byte bound')
            encoded = project(body)
            if type(encoded) is not bytes:
                if inspect.iscoroutine(encoded):
                    encoded.close()
                raise UsageAssociationUnavailable('projection must return materialized bytes')
            if len(encoded) > limit:
                raise UsageAssociationTooLarge('projected references exceed configured byte bound')
            frozen()
            final, final_usage, _ = _association(repository, binding)
            frozen()
            if final != first or final_usage != usage:
                raise UsageAssociationChanged('original RUN association changed')
            current_source()
            return encoded

        result = boundary.with_history_context(token, operation)
        if completed_repository is None:
            raise UsageAssociationUnavailable('original RUN binding unavailable')
        # The last AUTH callback and original context closure are now finished.
        # Direct canonical fields only: no checker/resolver/storage/project/context call.
        frozen()
        return result
