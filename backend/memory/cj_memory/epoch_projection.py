"""Scope-version display in an already-held canonical MESSAGE projection.

The L host supplies the public HistoryReadContext projection guard. This reader
never creates an effect authority or reacquires MESSAGE through another
connection. It grants no history collection, item read, write or future effect.
"""
from datetime import datetime, timezone

from psycopg import Error as DatabaseError

from cj_message.auth_boundary import HistoryReadContext
from .domain import CommitUnknown, Unavailable
from .postgres import Repository
from .runtime import RuntimeDenied, RuntimeUnknown
from .typed_runtime import TypedRuntimeConfiguration
from .typed_local import TypedConfiguration


class CurrentScopeEpochReader:
    def __init__(self,database,configuration: TypedRuntimeConfiguration):
        self.database=database
        self.configuration=configuration
        self.collection=configuration.collection
        self.selections=configuration.selections

    @classmethod
    def for_api(cls,database,configuration: TypedConfiguration):
        """Use the API's real policy; no worker policy or fake slot selection.

        Only the owning scope version is displayed, not selected Memory items.
        This does not add consumption/collection permission to the API host.
        """
        if configuration is None:raise RuntimeDenied('explicit API Memory policy required')
        reader=cls.__new__(cls)
        reader.database=database
        reader.configuration=configuration
        reader.collection=configuration
        reader.selections=None
        return reader

    def project(self,context: HistoryReadContext,binding,encode,*,max_result_bytes):
        """Encode a display using the real active scope epoch under a short lock.

        Call only from with_lio_timeline_projection. encode is synchronous,
        bounded and performs no provider/network operation. The result is point
        data, not a Source4 permit. Candidate/history readers remain separate.
        """
        from cj_api.local_app import scope_for
        if type(context) is not HistoryReadContext:
            raise RuntimeDenied('original MESSAGE history context required')
        if type(max_result_bytes) is not int or not 1<=max_result_bytes<=1_000_000:
            raise RuntimeDenied('bounded epoch display required')
        context.require_lio_projection()
        principal,scope=context.principal,context.scope
        if binding.scope!=scope or scope_for(principal.issuer,principal.subject)!=scope:
            raise RuntimeDenied('epoch view owner differs')
        configuration=self.configuration
        collection=self.collection
        selections=self.selections
        selected=None if selections is None else selections.get(principal.subject)
        if selections is not None and selected is None:raise RuntimeDenied('original runtime selection unavailable')
        profile=collection.collection.profiles.get(principal.subject)
        if profile is None:raise RuntimeDenied('original API Memory profile unavailable')
        original=context.query_lio_message(binding.message_id)
        if original is None:raise RuntimeDenied('original Lio message unavailable')
        receipt=original.receipt
        if (receipt.conversation_id,receipt.generation,receipt.message_id,receipt.run_id,receipt.sequence)!=(
                binding.conversation_id,binding.generation,binding.message_id,binding.run_id,binding.message_sequence):
            raise RuntimeDenied('epoch view original RUN differs')

        def check():
            context.require_lio_projection()
            if (context.principal!=principal or context.scope!=scope or self.configuration is not configuration
                    or self.collection is not collection or self.selections is not selections
                    or collection.collection.profiles.get(principal.subject) is not profile
                    or selections is not None and selections.get(principal.subject)!=selected
                    or profile.expires_at<=datetime.now(timezone.utc)
                    or context.query_lio_message(binding.message_id)!=original):
                raise RuntimeDenied('epoch view binding changed')
        check()
        repository=Repository(lambda:self.database.connect(scope),scope,
            transaction_binder=lambda connection,cursor:connection.bind_scope(cursor),typed_context=True)
        try:
            with repository.transaction() as memory:
                epoch=memory.lock_scope()  # Actual active scope only; no INSERT or history fence.
                result=encode(epoch)
                if type(result) is not bytes or len(result)>max_result_bytes:
                    raise RuntimeDenied('materialized bounded epoch display required')
                check()
            return result
        except Unavailable as error:
            raise RuntimeDenied('current Memory scope unavailable') from error
        except (CommitUnknown,DatabaseError) as error:
            raise RuntimeUnknown('epoch display outcome unavailable') from error
