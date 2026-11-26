"""Failed invite-code sign-in throttle for the HK API process (#1718).

Each invite exchange reserves one failure before the signer is asked; only a
granted session releases it. Parallel guesses therefore count up front and a
burst cannot slip past the limit between check and record.

Three sliding windows, all in this process's memory only (never persisted,
logged or returned; a restart starts empty, which only ever lowers the count):

- per client: ``PER_CLIENT`` failures in ``CLIENT_WINDOW`` seconds. The client
  key is the address Caddy writes into ``X-Forwarded-For`` (Caddy discards
  client-supplied values; the API port is not published). Requests without a
  single clean value share one ``unattributed`` key.
- short codes: the short code format is public, so every short-format failure
  also counts in one global ``SHORT_GLOBAL`` / ``SHORT_WINDOW`` window; when it
  is full, short codes are refused for everyone while long codes still work.
- all clients: ``GLOBAL`` failures in ``GLOBAL_WINDOW`` seconds stop new
  invite exchanges for everyone. Renewal of an existing session is not throttled.
"""
from collections import deque
import ipaddress
import threading
import time

PER_CLIENT=5
CLIENT_WINDOW=15*60
SHORT_GLOBAL=10
SHORT_WINDOW=60*60
GLOBAL=60
GLOBAL_WINDOW=60*60
MAX_CLIENTS=4096
UNATTRIBUTED='unattributed'


def client_key(headers):
    """The single proxy-written client address, or the shared unattributed key."""
    values=headers.getlist('x-forwarded-for')
    if len(values)!=1 or ',' in values[0]:return UNATTRIBUTED
    try:return ipaddress.ip_address(values[0].strip()).compressed
    except ValueError:return UNATTRIBUTED


class Throttle:
    def __init__(self,*,clock=time.monotonic):
        self.clock=clock;self.lock=threading.Lock()
        self.clients={};self.short=deque();self.all=deque()

    def _prune(self,now):
        for window,entries in ((SHORT_WINDOW,self.short),(GLOBAL_WINDOW,self.all)):
            while entries and entries[0]<=now-window:entries.popleft()
        for key in list(self.clients):
            entries=self.clients[key]
            while entries and entries[0]<=now-CLIENT_WINDOW:entries.popleft()
            if not entries:del self.clients[key]

    def reserve(self,key,*,short):
        """Count one failure now; return a release ticket, or None when refused."""
        with self.lock:
            now=self.clock();self._prune(now)
            entries=self.clients.get(key)
            if (len(self.all)>=GLOBAL or (short and len(self.short)>=SHORT_GLOBAL)
                    or entries is not None and len(entries)>=PER_CLIENT
                    or entries is None and len(self.clients)>=MAX_CLIENTS):
                return None
            if entries is None:entries=self.clients[key]=deque()
            entries.append(now);self.all.append(now)
            if short:self.short.append(now)
            return (key,now,short)

    def release(self,ticket):
        """A granted session is not a failure: drop exactly the reserved entries."""
        key,stamp,short=ticket
        with self.lock:
            for entries in (self.clients.get(key),self.all,self.short if short else None):
                if entries is not None and stamp in entries:entries.remove(stamp)
