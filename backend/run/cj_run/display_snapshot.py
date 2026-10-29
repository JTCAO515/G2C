"""Protected original-message RUN display read; no route, dispatch or write API.

Consumes MESSAGE bf79's real synchronous context and a trusted host RUN resolver.
No caller run ID/scope, cached admission boolean or second principal is accepted.
"""
from dataclasses import dataclass
import inspect
import json
from cj_message.auth_boundary import Boundary, HistoryReadContext
from .core import Binding


class SnapshotUnavailable(Exception):
    pass


class SnapshotChanged(SnapshotUnavailable):
    pass


class SnapshotTooLarge(SnapshotUnavailable):
    pass


@dataclass(frozen=True)
class DisplaySnapshotConfiguration:
    max_text_bytes: int
    max_response_bytes: int

    def __post_init__(self):
        if any(type(n) is not int or n < 1 for n in (self.max_text_bytes, self.max_response_bytes)):
            raise ValueError('explicit positive display byte limits required')


def _checked_recovery(repository, binding):
    result = repository.recover(binding)
    state, cursor = result.state, result.cursor
    if state.binding != binding or cursor.binding != binding:
        raise SnapshotUnavailable('invalid RUN snapshot boundary')
    # Transaction.get reconstructs text from events and checks stored status/sequence.
    # Keep source binding here; trust the repository's validated projection.
    return result


def _encode_snapshot(state, configuration):
    if len(state.text.encode('utf-8')) > configuration.max_text_bytes:
        raise SnapshotTooLarge('stored display text exceeds configured bound')
    b = state.binding
    payload = {
        'conversation_id': b.conversation_id, 'generation': b.generation,
        'message_id': b.message_id, 'run_id': b.run_id, 'message_sequence': b.message_sequence,
        'status': state.status, 'event_highwater': state.sequence,
        'text': state.text, 'text_state': 'complete' if state.status == 'completed' else 'partial',
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(encoded) > configuration.max_response_bytes:
        raise SnapshotTooLarge('encoded display snapshot exceeds configured bound')
    return encoded


class DisplaySnapshotReader:
    def __init__(self, message_boundary, resolve_run_repository, *, configuration):
        if (type(message_boundary) is not Boundary or not callable(resolve_run_repository)
                or type(configuration) is not DisplaySnapshotConfiguration):
            raise ValueError('fixed MESSAGE boundary, trusted resolver and explicit configuration required')
        self.message_boundary = message_boundary
        self.resolve_run_repository = resolve_run_repository
        self.configuration = configuration

    def read(self, token: str, message_id: str) -> bytes:
        """Return bounded UTF-8 JSON only after protected owner callback succeeds.

        The host resolver signature is (trusted_principal, trusted_scope). Its
        environment is server configuration, never a request argument. Return a
        repository exposing the existing scope/recover(binding) interface.
        """
        return self.read_projected(token, message_id, lambda encoded: encoded)

    def read_projected(self, token: str, message_id: str, project) -> bytes:
        """Run a trusted synchronous bytes-to-bytes wire projection under the owner guard.

        project receives only the verified nine-field JSON bytes, never context,
        State, repository or USAGE. It must validate/encode the final host envelope
        before returning. No envelope construction is permitted after this method.
        """
        if type(message_id) is not str or not message_id.strip():
            raise ValueError('original message ID required')
        if not callable(project):
            raise ValueError('trusted synchronous projection required')
        configuration = self.configuration
        return self._read_materialized(token, message_id,
            lambda state, original: project(_encode_snapshot(state, configuration)))

    def read_draft_status(self, token, message_id, request_id):
        """Versioned independent draft outcome, encoded before all final guards."""
        def encode(state, original):
            command = json.loads(original.raw)
            requested = command['creation_intent'] == 'consider_trip'
            published = any(effect.startswith('trip_proposal:') for effect in state.effects)
            if not requested and (published or state.draft_outcome is not None):
                raise SnapshotUnavailable('draft evidence contradicts original message')
            outcome = ('not_requested' if not requested else
                       state.draft_outcome if state.draft_outcome is not None else
                       'published' if published else 'not_recorded')
            b = state.binding
            return json.dumps(dict(request_id=request_id, version='RUN-draft-status.1',
                conversation_id=b.conversation_id, generation=b.generation,
                message_id=b.message_id, run_id=b.run_id, message_sequence=b.message_sequence,
                run_status=state.status, event_highwater=state.sequence, draft_outcome=outcome),
                ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        return self._read_materialized(token, message_id, encode)

    def _read_materialized(self, token, message_id, encode):
        if type(message_id) is not str or not message_id.strip():
            raise ValueError('original message ID required')
        configuration = self.configuration  # Freeze bounds for this read.

        def operation(ctx):
            if type(ctx) is not HistoryReadContext:
                raise SnapshotUnavailable('MESSAGE context unavailable')
            principal, scope = ctx.principal, ctx.scope
            original = ctx.query_message(message_id)
            if original is None:
                raise SnapshotUnavailable('original message unavailable')
            r = original.receipt
            binding = Binding(scope, r.conversation_id, r.generation, r.message_id, r.run_id, r.sequence)
            repository = self.resolve_run_repository(principal, scope)

            def source_guard():
                if (ctx.principal != principal or ctx.scope != scope or repository.scope != scope
                        or ctx.query_message(message_id) != original):
                    raise SnapshotChanged('original source changed')

            source_guard()  # Resolver callbacks cannot replace the original source.
            first = _checked_recovery(repository, binding)
            encoded = encode(first.state, original)
            if type(encoded) is not bytes:
                if inspect.iscoroutine(encoded):
                    encoded.close()
                raise SnapshotUnavailable('projection must return materialized bytes')
            if len(encoded) > configuration.max_response_bytes:
                raise SnapshotTooLarge('projected envelope exceeds configured bound')
            # Projection, encoding and final envelope bound precede every final guard.
            final = _checked_recovery(repository, binding)
            if final.state != first.state or final.cursor != first.cursor:
                raise SnapshotChanged('RUN changed during snapshot projection')
            source_guard()
            return encoded

        # MESSAGE rejects deferred/cross-thread contexts and rechecks the same
        # principal/scope after the callback. Any exception/cancellation withholds bytes.
        return self.message_boundary.with_history_context(token, operation)
