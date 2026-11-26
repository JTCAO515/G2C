"""Run several accounts' pending messages at once (W4-6, #1750).

`run_once` used to process every scope (account) one after another, so one
traveler's long plan made every other traveler wait. With
CJ_WORKER_SCOPE_CONCURRENCY=N (N > 1) different scopes run on up to N threads.
Each scope is still handled by exactly one thread per pass, so messages of one
account, and therefore of one conversation, keep their original order; the
per-scope worker, leases and checks are unchanged.

Pool guard: one plan save can hold about PEAK_CONNECTIONS database connections
at once (Hong Kong run -46 exhausted a pool of 6). The number of scopes that
run at the same time is capped at pool_size // PEAK_CONNECTIONS (at least one),
so turning the switch on with the current pool of 8 keeps one scope at a time
instead of starving each other; a pool of 16 allows two. Without a bounded pool
scopes also stay one at a time.

The default is 1, which is the old sequential loop byte for byte.
"""
from concurrent.futures import ThreadPoolExecutor
import contextvars
import logging
import os
import re

PEAK_CONNECTIONS = 7
MAX_CONCURRENCY = 4
_LOGGED = set()


def configured_concurrency():
    """The server switch: 1 (default, sequential) to MAX_CONCURRENCY."""
    value = os.environ.get('CJ_WORKER_SCOPE_CONCURRENCY', '1')
    if re.fullmatch(r'[1-9]', value) is None or int(value) > MAX_CONCURRENCY:
        raise ValueError('explicit worker scope concurrency 1-4 required')
    return int(value)


def effective_concurrency(configured, pool_size):
    """Cap by the connection pool: each running scope may need a full plan-save peak.

    Without a bounded pool there is nothing to guard direct connections with, so
    scopes stay one at a time (review of #1873).
    """
    if configured == 1 or pool_size is None:
        return 1
    return max(1, min(configured, pool_size // PEAK_CONNECTIONS))


def _log_once(configured, effective, pool_size):
    key = (configured, effective, pool_size)
    if key in _LOGGED:
        return
    _LOGGED.add(key)
    logging.getLogger('cj_usage.audit').info('LIO_WORKER_CONCURRENCY configured=%d effective=%d pool=%s',
                                             configured, effective, '-' if pool_size is None else pool_size)


def run_scopes(scopes, run_scope, *, pool_size):
    """Return (results in scope order, first failure in scope order or None).

    run_scope(scope) returns that scope's outcomes or raises. As before, one
    scope's failure never stops the other scopes; the caller raises it after all
    of them ran.
    """
    configured = configured_concurrency()
    workers = effective_concurrency(configured, pool_size)
    if configured != 1:
        _log_once(configured, workers, pool_size)
    results, failure = [], None
    if workers == 1 or len(scopes) < 2:
        for scope in scopes:
            try:
                results += run_scope(scope)
            except Exception as error:
                if failure is None:
                    failure = error
        return results, failure
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='cj-scope') as pool:
        # Each scope runs in a copy of the caller's context (for example the
        # rejected-intake capture set by the entrypoint), as the sequential loop did.
        futures = [pool.submit(contextvars.copy_context().run, run_scope, scope) for scope in scopes]
        for future in futures:
            try:
                results += future.result()
            except Exception as error:
                if failure is None:
                    failure = error
    return results, failure
