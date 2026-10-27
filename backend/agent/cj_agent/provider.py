"""Single-main-agent model providers (P2a). One interface, two implementations.

The provider never retries: once a request may have reached the model, its cost and
result are unknown to us, so the caller records `unknown` instead of resending
(ADR-0003). Keys come from the host only and never appear in errors or logs.
"""
from dataclasses import dataclass
import json
import os
import ssl
from typing import Iterator, Protocol

import certifi
import httpx


class ProviderFailed(Exception):
    """Definite failure (request rejected or not sent); no model output to keep."""


class ProviderUnknown(Exception):
    """The request may have been processed; result and cost are unknown."""


class ModelProvider(Protocol):
    def stream(self, messages: list[dict]) -> Iterator[str]: ...


SYSTEM_PROMPT = (
    'You are G2C, a travel assistant for foreign visitors to China. Answer in the language '
    'of the user (Chinese or English). Be concise. Never invent opening hours, prices or '
    'transport facts; say what needs checking instead.')


class FakeProvider:
    """Deterministic, offline. Used by tests and local runs without a key."""

    def __init__(self, chunks_per_reply=3):
        self.calls = 0
        self.chunks_per_reply = chunks_per_reply

    def stream(self, messages):
        self.calls += 1
        text = messages[-1]['content']
        chinese = any('一' <= ch <= '鿿' for ch in text)
        reply = (f'（本地模拟回复）收到：{text}。北京行程建议需要核实开放时间。' if chinese
                 else f'(local simulated reply) Received: {text}. Beijing plans need opening hours checked.')
        size = max(1, len(reply) // self.chunks_per_reply)
        for start in range(0, len(reply), size):
            yield reply[start:start + size]


@dataclass(frozen=True)
class DashScopeConfig:
    base_url: str
    model_id: str
    api_key: str
    timeout_seconds: float = 60.0
    max_output_tokens: int = 1024
    max_output_chars: int = 20000

    def __post_init__(self):
        if not self.base_url.startswith('https://') or self.base_url.endswith('/'):
            raise ValueError('base_url must be https without trailing slash')
        if not self.model_id or not self.api_key:
            raise ValueError('model_id and api_key are required')

    def __repr__(self):  # never expose the key
        return f'DashScopeConfig(base_url={self.base_url!r}, model_id={self.model_id!r}, api_key=<redacted>)'

    @classmethod
    def from_environment(cls, environ=os.environ):
        names = ('CJ_MODEL_API_BASE_URL', 'CJ_MODEL_ID', 'CJ_MODEL_API_KEY')
        missing = [name for name in names if not environ.get(name)]
        if missing:
            raise ProviderFailed('missing configuration: ' + ', '.join(missing))
        return cls(environ['CJ_MODEL_API_BASE_URL'], environ['CJ_MODEL_ID'], environ['CJ_MODEL_API_KEY'])


def tls_context():
    # Avoid create_default_context, which honours SSLKEYLOGFILE before it can be cleared.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    if context.keylog_filename is not None or not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise ProviderFailed('unsafe TLS context')
    return context


class DashScopeProvider:
    """OpenAI-compatible chat completions streaming (DashScope compatible mode)."""

    def __init__(self, config: DashScopeConfig, transport=None):
        self.config = config
        self.transport = transport  # tests inject httpx.MockTransport

    def _client(self):
        options = dict(timeout=self.config.timeout_seconds, follow_redirects=False, trust_env=False)
        if self.transport is not None:
            return httpx.Client(transport=self.transport, **options)
        return httpx.Client(verify=tls_context(), **options)

    def stream(self, messages):
        body = {'model': self.config.model_id, 'stream': True, 'max_tokens': self.config.max_output_tokens,
                'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, *messages]}
        headers = {'Authorization': 'Bearer ' + self.config.api_key, 'Content-Type': 'application/json'}
        url = self.config.base_url + '/chat/completions'
        produced = 0
        try:
            with self._client() as client:
                with client.stream('POST', url, headers=headers, content=json.dumps(body).encode()) as response:
                    if response.status_code != 200:
                        # Rejected before generation; body is not echoed (may contain request data).
                        raise ProviderFailed(f'provider HTTP {response.status_code}')
                    done = False
                    for line in response.iter_lines():
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            done = True
                            break
                        try:
                            choices = json.loads(data).get('choices') or []
                        except ValueError:
                            raise ProviderUnknown('malformed stream chunk') from None
                        for choice in choices:
                            text = (choice.get('delta') or {}).get('content') or ''
                            if text:
                                produced += len(text)
                                if produced > self.config.max_output_chars:
                                    raise ProviderUnknown('output exceeded bound')
                                yield text
                    if not done:
                        raise ProviderUnknown('stream ended without [DONE]')
        except (ProviderFailed, ProviderUnknown):
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # Connection never established: the request did not reach the model.
            raise ProviderFailed('connect failed') from None
        except httpx.HTTPError:
            # Read/write timeout or broken stream: the request may have been processed.
            raise ProviderUnknown('transport error') from None
