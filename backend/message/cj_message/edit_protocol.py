"""CJ-MESSAGE-EDIT@1 interfaces. No runtime capability is issued by these DTOs."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, ContextManager, Protocol

EDIT_ABI = 'CJ-MESSAGE-EDIT@1'
MEMORY_ABI = 'CJ-MESSAGE-EDIT-MEMORY@1'
PUBLISHER_ABI = 'CJ-MESSAGE-EDIT-PUBLISHER@1'
PROFILE = 'message-trip.2'


@dataclass(frozen=True)
class PreparedEdit:
    """C's bounded model system prompt and captured source data; not permission."""
    system: str
    state: object


class EditSource(Protocol):
    @property
    def reference(self): ...
    @property
    def original_utf8(self) -> bytes: ...
    @property
    def trip_content(self) -> bytes: ...
    @property
    def selected_item_ids(self) -> tuple[str, ...]: ...


class NamespaceLease(Protocol):
    @property
    def kind(self) -> str: ...  # exactly travel, independently selected, not Trip
    @property
    def id(self) -> str: ...
    @property
    def version(self) -> int: ...
    def check(self, binding) -> None: ...


class EditPublication(Protocol):
    @property
    def reference(self): ...
    @property
    def memory_namespace(self) -> NamespaceLease: ...
    @property
    def cursor(self): ...
    def check(self, binding) -> None: ...
    def enter_source(self, source_lease: ContextManager[Callable[[], None]]) -> Callable[[], None]: ...
    def lock_trip(self) -> bytes: ...
    def before_write(self) -> None: ...


class EditMemoryConfiguration(Protocol):
    abi: str  # exact MEMORY_ABI; compatibility only, never authorization
    def bind(self, database, scope, identity, admit, *, message_context): ...
    # Returns the existing RuntimeMemory interface (capture/hold/messages/provide),
    # implemented by C's new adapter, retaining all current typed eligibility/fences.


class ScopedEditPublisher(Protocol):
    abi: str  # exact PUBLISHER_ABI; compatibility only
    def prepare(self, binding, source: EditSource) -> PreparedEdit: ...
    def hold_sources(self, publication: EditPublication, prepared: PreparedEdit) -> ContextManager[Callable[[], None]]: ...
    def publish_in_transaction(self, publication: EditPublication, prepared: PreparedEdit, reply: str) -> str: ...
    # Returns the original proposal ID. Must use C's sole _publish_in_tx on
    # publication.cursor, lock_trip then last before_write; no second commit/writer.


@dataclass(frozen=True)
class EditConfiguration:
    """Explicit trusted host injection. Neither wire data nor a ready/permission DTO."""
    memory: EditMemoryConfiguration
    publisher: ScopedEditPublisher
    abi: str = EDIT_ABI


class EditAuthority(Protocol):
    def read_original(self, binding): ...  # immutable OriginalEditReference, data only
    def capture(self, binding) -> EditSource: ...
    def hold_for_effect(self, binding, *, source_lock=True) -> ContextManager[EditPublication]: ...
    def publication(self, binding, source: EditSource, *, phase='proposal', deadline: Callable[[], None]) -> ContextManager[EditPublication]: ...
