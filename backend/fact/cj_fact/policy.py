"""Explicit source policy for injected transport validation. No DNS or sockets here."""
import ipaddress
import math
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class FactFailure(Exception):
    """Safe code only. Never include source URL/body/transport exception text."""


def canonical_url(url: str) -> tuple[str, str]:
    if (type(url) is not str or len(url) > 4096 or not url.isascii()
            or any(ord(c) <= 32 or ord(c) >= 127 for c in url) or '\\' in url):
        raise FactFailure('invalid_url')
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or parsed.fragment or '%' in parsed.netloc or host.endswith('.')):
            raise ValueError()
        # Canonical lower-case ASCII DNS only. IP literals (including unusual numeric
        # spellings), IDN spellings, zones and single-label internal names are rejected.
        if (host != host.lower() or len(host) > 253 or '.' not in host
                or not re.fullmatch(r'[a-z0-9.-]+', host)
                or all(c in '0123456789.' for c in host)
                or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
                       or label.startswith('xn--') for label in host.split('.'))
                or not re.fullmatch(r'[a-z]{2,63}', host.split('.')[-1])):
            raise ValueError()
        origin = 'https://' + host
        expected_netloc = host + (':443' if parsed.netloc.endswith(':443') else '')
        if parsed.netloc != expected_netloc:
            raise ValueError()
        canonical = urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))
        return canonical, origin
    except (ValueError, TypeError):
        raise FactFailure('invalid_url') from None


def public_addresses(addresses: tuple[str, ...]) -> tuple[str, ...]:
    if type(addresses) is not tuple or not 1 <= len(addresses) <= 32:
        raise FactFailure('invalid_dns_answer')
    normalized = []
    for value in addresses:
        try:
            if type(value) is not str or '%' in value:
                raise ValueError()
            address = ipaddress.ip_address(value)
            if (not address.is_global or address.is_private or address.is_loopback
                    or address.is_link_local or address.is_multicast or address.is_reserved
                    or address.is_unspecified or getattr(address, 'ipv4_mapped', None)
                    or getattr(address, 'sixtofour', None) or getattr(address, 'teredo', None)):
                raise ValueError()
            # Translation prefixes can route to an embedded non-public IPv4 address.
            if address.version == 6 and (address in ipaddress.ip_network('64:ff9b::/96')
                                        or address in ipaddress.ip_network('64:ff9b:1::/48')):
                raise ValueError()
            normalized.append(str(address))
        except (ValueError, TypeError):
            raise FactFailure('non_public_dns_answer') from None
    return tuple(dict.fromkeys(normalized))


@dataclass(frozen=True)
class SourcePolicy:
    """Trusted host-owned allowlist and limits; never construct from source/request data."""
    allowed_origins: tuple[str, ...]
    max_bytes: int
    max_chunks: int
    max_redirects: int
    timeout_seconds: float
    max_json_depth: int
    max_json_nodes: int

    def __post_init__(self):
        if type(self.allowed_origins) is not tuple:
            raise FactFailure('invalid_policy')
        for origin in self.allowed_origins:
            _, canonical_origin = canonical_url(origin)
            if origin != canonical_origin:
                raise FactFailure('invalid_policy_origin')
        for value in (self.max_bytes, self.max_chunks, self.max_json_depth, self.max_json_nodes):
            if type(value) is not int or value <= 0:
                raise FactFailure('invalid_policy_limit')
        if type(self.max_redirects) is not int or not 0 <= self.max_redirects <= 10:
            raise FactFailure('invalid_policy_limit')
        if (type(self.timeout_seconds) not in (int, float)
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise FactFailure('invalid_policy_limit')

    def target(self, url: str) -> str:
        canonical, origin = canonical_url(url)
        if origin not in self.allowed_origins:
            raise FactFailure('source_not_allowed')
        return canonical
