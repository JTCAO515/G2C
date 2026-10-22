"""Offline fixture composition only. Injected Python is trusted code, not a sandbox."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import time

from .gaode import Config, PreparationError, PreparedRequest, Response, parse_response, prepare
from .models import Outcome, Query, Result


async def run_synthetic(config: Config | None, query: Query, *, request_ref: str,
                        transport: Callable[[PreparedRequest], Awaitable[Response]] | None) -> Result:
    """One attempt, no retries or settlement. NEVER register with a production host.

    Transport must be an offline, cancellation-cooperative fixture. The timeout is
    cooperative; this helper cannot sandbox arbitrary injected code or prove a
    stopped external call. It receives no credentials or authenticated context.
    """
    if config is None or transport is None:
        return Result(Outcome.UNAVAILABLE, query, "fixture_configuration_required")
    started = datetime.now(timezone.utc)
    try:
        request = prepare(config, query, request_ref, started)
    except PreparationError as error:
        return Result(Outcome.UNSUPPORTED, query, str(error))
    before = time.monotonic()
    try:
        response = await asyncio.wait_for(transport(request), timeout=config.timeout_seconds)
    except asyncio.CancelledError:
        raise  # Cancellation is not a provider result or proof of non-dispatch.
    except Exception:
        return Result(Outcome.UNKNOWN, query, "fixture_transport_unknown")
    if time.monotonic() - before > config.timeout_seconds:
        return Result(Outcome.UNKNOWN, query, "fixture_deadline_exceeded")
    return parse_response(config, request, response, now=datetime.now(timezone.utc), evidence="synthetic")
