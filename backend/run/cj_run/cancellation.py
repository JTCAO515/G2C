"""RUN-CANCEL@1: original MESSAGE ownership plus a guarded RUN mutation.

The MESSAGE context supplies only current source/identity. Its read result is not
cached write permission: source ownership is checked again inside the RUN fence
before mutation/commit, and after response projection before publication.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
from .core import Binding, Service

MAX_CANCEL_BYTES = 4096


class CancellationUnavailable(Exception):
    pass


class CancellationUnknown(Exception):
    """The original RUN may already be terminal; reconcile it, never dispatch again."""


class CancellationInputTooLarge(ValueError):
    pass


def _unique(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError('duplicate field')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('non-JSON constant')


@dataclass(frozen=True)
class CancelCommand:
    message_id: str

    def __post_init__(self):
        if (type(self.message_id) is not str or not self.message_id.strip()
                or '\x00' in self.message_id or len(self.message_id.encode('utf-8')) > 256):
            raise ValueError('bounded original message ID required')

    @classmethod
    def parse(cls, raw):
        if type(raw) is not bytes: raise ValueError('immutable JSON bytes required')
        if len(raw) > MAX_CANCEL_BYTES: raise CancellationInputTooLarge()
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_constant)
        if type(obj) is not dict or set(obj) != {'version', 'message_id'} or obj['version'] != 'RUN-cancel.1':
            raise ValueError('unsupported cancellation')
        return cls(obj['message_id'])


class CancellationHandler:
    def __init__(self, message_boundary, resolve_run_repository):
        self.message_boundary = message_boundary
        self.resolve_run_repository = resolve_run_repository

    def cancel_projected(self, token, command, project):
        attempted = False

        def operation(context):
            nonlocal attempted
            principal, scope = context.principal, context.scope
            original = context.query_message(command.message_id)
            if original is None: raise CancellationUnavailable()
            repository = self.resolve_run_repository(principal, scope)
            receipt = original.receipt
            binding = Binding(scope, receipt.conversation_id, receipt.generation,
                              receipt.message_id, receipt.run_id, receipt.sequence)

            def guard():
                if (context.principal != principal or context.scope != scope or repository.scope != scope
                        or context.query_message(command.message_id) != original):
                    raise CancellationUnavailable()

            class GuardedRun:
                @contextmanager
                def transaction(self):
                    with repository.transaction(require_clean_close=True) as tx:
                        guard()
                        yield tx
                        guard()

            guard()
            attempted = True
            state = Service(GuardedRun()).cancel(binding)
            encoded = project(state)
            guard()
            return encoded

        try:
            return self.message_boundary.with_history_context(token, operation)
        except Exception:
            if attempted: raise CancellationUnknown() from None
            raise
