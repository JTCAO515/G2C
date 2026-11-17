"""Lock the existing Memory scope inside a genuine API MESSAGE source frame.

This holds metadata only. It grants no item read, collection, model, Trip write
or PlanNow authority. The domain caller retains its independent source/profile
and write checks and keeps M -> Memory -> NEEDS -> Trip ordering.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime,timezone
from threading import get_ident
from typing import Protocol
from psycopg import Error as DatabaseError
from cj_auth.interfaces import TrustedPrincipal
from .domain import Unavailable,CommitUnknown
from .postgres import Repository
from .runtime import RuntimeDenied,RuntimeUnknown
from .typed_local import TypedConfiguration


class MessageScopeFrame(Protocol):
    principal:TrustedPrincipal
    scope:str
    def check(self)->None: ...


@dataclass(frozen=True)
class HeldScope:
    epoch:int
    check:object


class ApiMemoryScopeHolder:
    def __init__(self,database,configuration:TypedConfiguration):
        if configuration is None:raise RuntimeDenied('explicit API Memory policy required')
        self.database,self.configuration=database,configuration

    @contextmanager
    def hold(self,message_context:MessageScopeFrame):
        from cj_api.local_app import scope_for
        database,configuration=self.database,self.configuration
        principal,scope=message_context.principal,message_context.scope
        if scope_for(principal.issuer,principal.subject)!=scope:
            raise RuntimeDenied('Memory scope owner differs')
        profile=configuration.collection.profiles.get(principal.subject)
        if profile is None:raise RuntimeDenied('original API Memory profile unavailable')
        thread=get_ident();active=True
        def check():
            if not active or get_ident()!=thread:
                raise RuntimeDenied('Memory API holder expired or crossed thread')
            if (message_context.principal!=principal or message_context.scope!=scope
                    or self.database is not database or self.configuration is not configuration
                    or configuration.collection.profiles.get(principal.subject)is not profile
                    or profile.expires_at<=datetime.now(timezone.utc)):
                raise RuntimeDenied('Memory API binding or policy changed')
            if message_context.check()is not None:
                raise RuntimeDenied('original throwing MESSAGE guard required')
        try:
            check()  # The actual M owner/admission frame precedes Memory IO.
            repository=Repository(lambda:database.connect(scope),scope,typed_context=True,
                transaction_binder=lambda connection,cursor:connection.bind_scope(cursor))
            with repository.transaction()as memory:
                epoch=memory.lock_scope()  # Existing active scope only; no INSERT.
                yield HeldScope(epoch,check)
                check()  # Still held through the caller's final Trip commit.
        except Unavailable as error:
            raise RuntimeDenied('current Memory scope unavailable')from error
        except(CommitUnknown,DatabaseError)as error:
            raise RuntimeUnknown('Memory API hold completion unknown')from error
        finally:active=False
