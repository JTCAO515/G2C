"""CJ-PLACE-DRAFT@1: source data and explicit C producer configuration, never grants."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from cj_run.core import Binding
from .models import Result
from .gaode import Config

ABI='CJ-PLACE-DRAFT@1'
PUBLISHER_ABI='CJ-PLACE-DRAFT-PUBLISHER@1'
TOOLS_VERSION='CJ-LOCAL-PLACE-DRAFT-TOOLS@1'


class PlaceSourceUnavailable(Exception):
    """Original observation/currentness is unavailable; never silently omit sources."""


@dataclass(frozen=True)
class PlaceObservation:
    operation_key:str
    request_ref:str
    original_query:bytes
    result_utf8:bytes
    result:Result
    config:Config
    started_at:datetime


@dataclass(frozen=True)
class PlaceSourceBatch:
    binding:Binding
    observations:tuple[PlaceObservation,...]


class PlaceSources(Protocol):
    abi:str
    def capture(self,binding:Binding)->PlaceSourceBatch: ...
    def check(self,binding:Binding,batch:PlaceSourceBatch)->None: ...


class PlaceDraftPublisherConfiguration(Protocol):
    abi:str
    def bind(self,database,checker,message_context,token_supplier,scope,*,place_sources:PlaceSources): ...
    # New explicit structured.1/2 producer interface, C owns builder and sole writer.


@dataclass(frozen=True)
class PlaceDraftConfiguration:
    publisher:PlaceDraftPublisherConfiguration
    abi:str=ABI
