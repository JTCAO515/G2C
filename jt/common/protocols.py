"""Interfaces implemented by the recognition engine and workbench."""

from typing import Protocol

from .models import DecisionContext, DecisionOutput, Signal


class DecisionModel(Protocol):
    async def decide(self, context: DecisionContext) -> DecisionOutput: ...


class SignalSink(Protocol):
    async def publish(self, signal: Signal) -> None:
        """Accept a signal once by ID. Reject conflicting content and surface failures."""
        ...
