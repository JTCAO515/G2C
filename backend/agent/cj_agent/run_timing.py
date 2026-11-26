"""Content-free reply timing for the first-text baseline (W2-3, #1729).

Two log lines are joined offline by a message key (eval/lio_timing_baseline.py):

- the API logs LIO_TIMING_ACCEPTED with the wall-clock time a message was accepted;
- the worker logs LIO_TIMING once per RUN it executes, with the wall-clock pickup time
  and millisecond offsets from pickup to the first progress, the first visible text
  and the terminal event.

The message key is the first 16 hex digits of sha256(message_id), because a client
chooses its message_id. Only that key, the RUN id, event kinds and times are written;
never message text, tool names, places or model output. Logging never changes the RUN or raises into the caller.
"""
from hashlib import sha256
import logging
import threading
import time

from cj_message.lio_context import TOOL_EFFECT

_LOG = logging.getLogger('cj_usage.audit')
TERMINAL_KINDS = frozenset(('completed', 'failed', 'cancelled', 'context_invalid', 'unknown'))


def message_key(message_id):
    return sha256(message_id.encode('utf-8')).hexdigest()[:16]


def _epoch_ms():
    return int(time.time() * 1000)


def accepted(message_id):
    """API side: one line when a Lio message is accepted for a RUN."""
    try:
        _LOG.info('LIO_TIMING_ACCEPTED message_key=%s accepted_ms=%d', message_key(message_id), _epoch_ms())
    except Exception:
        pass


class RunTiming:
    """Worker side: first occurrence of each milestone inside one executed RUN."""

    def __init__(self, binding, *, clock=time.perf_counter, wall=_epoch_ms):
        self._clock = clock
        self._lock = threading.Lock()
        self.message_key = message_key(binding.message_id)
        self.run_id = binding.run_id
        self.picked_up_ms = wall()
        self._start = clock()
        self.marks = {}
        self.terminal = None

    def _mark(self, name):
        if name not in self.marks:
            self.marks[name] = int((self._clock() - self._start) * 1000)

    def observe(self, kind, value=''):
        """Record a committed RUN event; progress is a tool-progress effect or the first text."""
        try:
            with self._lock:
                if kind == 'started':
                    self._mark('started')
                elif kind == 'effect_committed' and isinstance(value, str) and value.startswith(TOOL_EFFECT):
                    self._mark('first_progress')
                elif kind == 'text_delta':
                    self._mark('first_progress')
                    self._mark('first_text')
                elif kind in TERMINAL_KINDS:
                    self._mark('terminal')
                    if self.terminal is None:
                        self.terminal = kind
        except Exception:
            pass

    def log(self, status):
        """One line per executed RUN; a RUN that only waited for its lease is not logged."""
        if status == 'waiting':
            return
        try:
            with self._lock:
                fields = ' '.join(f'{name}_ms={self.marks[name]}' if name in self.marks else f'{name}_ms=-'
                                  for name in ('started', 'first_progress', 'first_text', 'terminal'))
                _LOG.info('LIO_TIMING message_key=%s run_id=%s picked_up_ms=%d %s terminal=%s status=%s',
                          self.message_key, self.run_id, self.picked_up_ms, fields,
                          self.terminal or '-', status)
        except Exception:
            pass
