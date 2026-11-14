"""Private actor originals, explicitly sourced from a typed actor RUN.

Reuse the accepted operation/Meter/vendor/artifact verification. The source
selector is different: it never fabricates a MESSAGE or calls its reader as a
fallback. Raw input/artifacts retain the original DUT M lifetime. Fee/status
metadata remains readable under original actor AUTH after DUT deletion.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
import json

from runtime_adapter.contract import Unavailable
from cj_message.auth_boundary import AccessBlocked, IdentityChanged

from .runtime_originals import RuntimeOriginals
from .runtime_actor import OPERATION, REGISTRATION


@dataclass(frozen=True)
class ActorReceipt:
    conversation_id: str
    generation: str
    message_id: str
    run_id: str
    sequence: int
    input_sha256: str


@dataclass(frozen=True)
class ActorOriginal:
    receipt: ActorReceipt
    raw: bytes


class ActorOriginals(RuntimeOriginals):
    def __init__(self, host, artifact_directory):
        super().__init__(host.source.boundary, host.database,
            host.tools.services.model.authorization, artifact_directory)
        self.host = host
        self.metadata = ContextVar('actor_original_metadata', default=False)

    def _original(self, token, actor_id, project):
        self.host._guard(read_only=True, purpose='query')
        if sha256(token.encode()).hexdigest() != self.host.owner.auth_session_id:
            raise Unavailable('ACTOR_ORIGINAL_SESSION_CHANGED')
        found = [item for item in self.host.originals if item.argument.binding.message_id == actor_id]
        if len(found) != 1:
            raise Unavailable('ACTOR_ORIGINAL_UNAVAILABLE')
        run = found[0];argument = run.argument;binding = argument.binding
        run.claim.read(actor_id)
        # snapshot_optional validates every native binding field, not just RUN ID.
        run.inspect()
        source = self._operations(binding.scope, binding.run_id)
        if (len(source[2]) > 1 or any(row[0] != OPERATION or row[1] != REGISTRATION
                or row[2] != 'model' or row[7] is not None and bytes(row[7]) != argument.original()
                for row in source[2])):
            raise Unavailable('ACTOR_ORIGINAL_OPERATION_CHANGED')
        receipt = ActorReceipt(binding.conversation_id, binding.generation, actor_id,
            binding.run_id, 1, sha256(argument.original()).hexdigest())
        result = project(binding.scope, ActorOriginal(receipt, argument.original()), source)
        if self._operations(binding.scope, binding.run_id) != source:
            raise Unavailable('ACTOR_ORIGINAL_SNAPSHOT_CHANGED')
        self.host._guard(read_only=True, purpose='query')
        return result

    def _read(self, token, actor_id, project):
        try:
            return self._protected_read(token, actor_id, project)
        except (AccessBlocked, IdentityChanged):
            raise Unavailable('ACTOR_ORIGINAL_AUTH_UNAVAILABLE') from None

    def _protected_read(self, token, actor_id, project):
        if self.metadata.get():
            def read(context):
                if context.scope != self.host.owner.scope:
                    raise Unavailable('ACTOR_ORIGINAL_OWNER_CHANGED')
                return self._original(token, actor_id, project)
            return self.boundary.with_history_context(token, read)
        found = [item for item in self.host.originals if item.argument.binding.message_id == actor_id]
        if len(found) != 1:
            raise Unavailable('ACTOR_ORIGINAL_UNAVAILABLE')
        argument = found[0].argument
        history = json.loads(json.loads(argument.messages)[1]['content'])['history']
        parent = json.loads(argument.source)
        def read(source, check):
            if source != argument.source:
                raise Unavailable('ACTOR_DUT_ORIGINAL_CHANGED')
            check()
            result = self._original(token, actor_id, project)
            check()
            return result
        return self.host.source.use(token, parent['message_id'], history, read)

    def _metadata_read(self, reader, *args):
        token = self.metadata.set(True)
        try:
            return reader(*args)
        finally:
            self.metadata.reset(token)

    def inventory(self, token, actor_id):
        return self._metadata_read(super().inventory, token, actor_id)

    def meter(self, token, actor_id, operation_id):
        return self._metadata_read(super().meter, token, actor_id, operation_id)

    def fee(self, token, actor_id, operation_id):
        return self._metadata_read(super().fee, token, actor_id, operation_id)

    def visible_original(self, token, actor_id):
        raise Unavailable('ACTOR_HAS_NO_MESSAGE_OR_HISTORY')
