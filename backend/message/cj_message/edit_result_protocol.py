"""CJ-MESSAGE-EDIT-RESULT@1, additive publisher2 data/interface only.

Descriptors, preparation data and ABI strings never grant a publication lease.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import ContextManager,Callable,Protocol
from .edit_protocol import PreparedEdit,EditSource,EditPublication,EditMemoryConfiguration

PUBLISHER_ABI='CJ-MESSAGE-EDIT-PUBLISHER@2'
CONFIGURATION_ABI='CJ-MESSAGE-EDIT-RESULT@1'
PROFILE='message-edit-result.1'
KINDS=frozenset({'clarification_required','expansion_required'})


@dataclass(frozen=True)
class PreparedClarification:
    """Non-READY source selection, before model. C state retains all source data."""
    state: object


@dataclass(frozen=True)
class ScopedResult:
    """C's original stored-result descriptor; data only, not a Proposal or permit."""
    kind: str
    result_id: str


class ScopedResultPublisher(Protocol):
    abi: str  # exactly PUBLISHER_ABI, explicit actual server dependency
    def prepare(self,binding,source:EditSource) -> PreparedEdit | PreparedClarification: ...
    def hold_sources(self,publication:EditPublication,prepared:PreparedEdit | PreparedClarification) -> ContextManager[Callable[[],None]]: ...
    def publish_clarification_in_transaction(self,publication:EditPublication,prepared:PreparedClarification) -> ScopedResult: ...
    def publish_in_transaction(self,publication:EditPublication,prepared:PreparedEdit,reply:str) -> str | ScopedResult: ...


@dataclass(frozen=True)
class EditResultConfiguration:
    memory: EditMemoryConfiguration
    publisher: ScopedResultPublisher
    abi: str=CONFIGURATION_ABI
