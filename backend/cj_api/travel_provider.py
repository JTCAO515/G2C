"""Bounded transport and short-lived cache for read-only travel plug-ins."""

from collections import OrderedDict
from contextlib import closing, contextmanager
from http.client import HTTPException, HTTPSConnection
from time import monotonic
import json
from urllib.parse import unquote, urlencode, urlsplit
import zlib

from cj_strict_json import compact, reject_duplicates

from .plugin_tools import PluginError


MAX_REPLY = 512 * 1024


def supplier_json(raw, key):
    def reject_nonfinite(_):
        raise ValueError('non-finite supplier value')

    value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate supplier field'),
                       parse_constant=reject_nonfinite)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str) and (key in item or key in unquote(item)):
            raise ValueError('credential echoed in supplier response')
    return value


def read_reply(response, deadline):
    size = 0
    for chunk in response.iter_bytes():
        if monotonic() >= deadline:
            raise PluginError(504, 'supplier_timeout')
        size += len(chunk)
        if size > MAX_REPLY:
            raise PluginError(502, 'supplier_unavailable')
        yield chunk


class SupplierPaymentRequired(PluginError):
    def __init__(self):
        super().__init__(503, 'not_enabled')


def check_status(code):
    if code == 402:
        raise SupplierPaymentRequired()
    if code == 429:
        raise PluginError(429, 'rate_limited')
    if code != 200:
        raise PluginError(502, 'supplier_unavailable')


def checked_key(key):
    if not 8 <= len(key) <= 512 or not key.isascii() or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError('invalid_travel_provider_key')


class ShortCache:
    """Only projected public data stays in this process, never an owner or raw response."""

    def __init__(self, seconds, *, clock=monotonic):
        self.seconds = seconds
        self.clock = clock
        self.entries = OrderedDict()

    def load(self, key, fetch):
        now = self.clock()
        if key in self.entries:
            expires, response = self.entries[key]
            if now < expires:
                return response
            del self.entries[key]
        response = fetch()
        self.entries[key] = self.clock() + self.seconds, response
        if len(self.entries) > 128:
            self.entries.popitem(last=False)
        return response


class ProviderReply:
    def __init__(self, response):
        self.response = response
        self.status_code, self.headers = response.status, response.headers

    def iter_bytes(self):
        encoding = self.headers.get('Content-Encoding', 'identity').lower()
        if encoding not in ('identity', 'gzip'):
            raise ValueError('unsupported supplier encoding')
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == 'gzip' else None
        remaining = MAX_REPLY
        while chunk := self.response.read1(8192):
            if decoder is not None:
                chunk = decoder.decompress(chunk, remaining + 1)
                if decoder.unconsumed_tail or decoder.unused_data:
                    raise ValueError('invalid compressed supplier response')
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError('unbounded supplier reply')
            yield chunk
        if decoder is not None and not decoder.eof:
            raise ValueError('incomplete compressed supplier response')


class ProviderClient:
    """Direct HTTPS with no redirects, environment proxy, or URL logging."""

    @contextmanager
    def stream(self, method, url, *, params=None, json=None, headers):
        target = urlsplit(url)
        path = target.path + ('?' + urlencode(params) if params else '')
        sent = dict(headers)
        if json is not None:
            sent['Content-Type'] = 'application/json'
        try:
            with closing(HTTPSConnection(target.netloc, timeout=8)) as conn:
                conn.request(method, path, body=compact(json) if json is not None else None, headers=sent)
                with closing(conn.getresponse()) as reply:
                    yield ProviderReply(reply)
        except TimeoutError:
            raise PluginError(504, 'supplier_timeout') from None
        except (HTTPException, OSError, zlib.error):
            raise PluginError(502, 'supplier_unavailable') from None


@contextmanager
def provider_client():
    yield ProviderClient()
