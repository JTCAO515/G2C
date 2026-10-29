"""Concrete consumption of pinned MESSAGE/RUN public read seams; no raw SQL."""
from cj_message.auth_boundary import Boundary as MessageBoundary
from cj_run.core import Binding
from cj_run.postgres import Repository as RunRepository
from cj_run.diagnostics import read_diagnostic
from .domain import SourceReference, ReferenceUnavailable


class Sources:
    def __init__(self, message, resolve_run):
        if not isinstance(message, MessageBoundary) or resolve_run is None:
            raise ReferenceUnavailable()
        self.message, self.resolve_run = message, resolve_run

    def _read(self, token, principal, scope, references, expected=None, encoded=None):
        message, resolve = self.message, self.resolve_run
        checker, mapping = message.checker, message.resolve_repository
        def unchanged():
            if (self.message is not message or self.resolve_run is not resolve
                    or message.checker is not checker or message.resolve_repository is not mapping):
                raise ReferenceUnavailable()
        def operation(ctx):
            unchanged()
            if ctx.principal != principal or ctx.scope != scope: raise ReferenceUnavailable()
            ids = {r['kind']: r['id'] for r in references}
            stored = ctx.query_message(ids['message'])
            if stored is None: raise ReferenceUnavailable()
            receipt = stored.receipt
            if 'run' in ids and ids['run'] != receipt.run_id: raise ReferenceUnavailable()
            binding = Binding(ctx.scope, receipt.conversation_id, receipt.generation,
                              receipt.message_id, receipt.run_id, receipt.sequence)
            repository = resolve(ctx.principal, ctx.scope)
            if not isinstance(repository, RunRepository) or repository.scope != ctx.scope:
                raise ReferenceUnavailable()
            connect = repository.connect
            diagnostic = read_diagnostic(repository, binding)
            # A slow RUN read must not let a changed MESSAGE association through.
            current = ctx.query_message(receipt.message_id)
            if (current is None or current.receipt != receipt or repository.scope != scope
                    or repository.connect is not connect or diagnostic.binding != binding):
                raise ReferenceUnavailable()
            unchanged()
            if ctx.principal != principal or ctx.scope != scope: raise ReferenceUnavailable()
            result = SourceReference(receipt.message_id, receipt.conversation_id,
                                     receipt.generation, receipt.sequence, receipt.run_id,
                                     receipt.input_sha256, diagnostic.status, diagnostic.event_highwater)
            if expected is not None and result != expected: raise ReferenceUnavailable()
            return result if encoded is None else encoded
        try:
            # Both read-time projection and final encoded publication leave through
            # MESSAGE's original-principal guard. No context is retained or copied.
            result = message.with_history_context(token, operation)
            unchanged()
            return result
        except Exception:
            # Identical error for missing, foreign, changed, expired and unknown.
            raise ReferenceUnavailable() from None

    def read(self, token, principal, scope, references):
        return self._read(token, principal, scope, references)

    def verify(self, token, principal, scope, references, expected):
        return self._read(token, principal, scope, references, expected=expected)

    def publish(self, token, principal, scope, references, expected, encoded):
        return self._read(token, principal, scope, references, expected=expected, encoded=encoded)
