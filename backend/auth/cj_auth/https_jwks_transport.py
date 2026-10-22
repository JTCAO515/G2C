"""CJ-JWKS-HTTPS@0.1.0-rc.1. Explicit opt-in HTTPS, no environment/default endpoint."""
import asyncio
import math
import ssl
from dataclasses import dataclass

import httpx

from .jwks_provider import JWKSRequest, _https

HTTPS_TRANSPORT_VERSION = 'CJ-JWKS-HTTPS@0.1.0-rc.1'


class HTTPTransportFailure(Exception):
    """Safe reason only: no URL, credentials, response body or underlying exception text."""


@dataclass(frozen=True)
class HTTPSConfiguration:
    url: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    write_timeout_seconds: float
    pool_timeout_seconds: float
    cancellation_poll_seconds: float
    max_response_bytes: int
    max_chunks: int

    def __post_init__(self):
        if not _https(self.url) or str(httpx.URL(self.url)) != self.url:
            raise ValueError('explicit canonical trusted HTTPS URL required')
        for value in (self.connect_timeout_seconds, self.read_timeout_seconds, self.write_timeout_seconds,
                      self.pool_timeout_seconds, self.cancellation_poll_seconds):
            if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
                raise ValueError('positive finite explicit timeout required')
        for value in (self.max_response_bytes,self.max_chunks):
            if type(value) is not int or value <= 0: raise ValueError('positive explicit bound required')


class BufferedJWKSResponse:
    def __init__(self, status, url, content_type, chunks):
        self.status, self.final_url, self.content_type = status, url, content_type
        self.chunks = tuple(chunks)
        self.closed = False
    def close(self):
        self.chunks = ()
        self.closed = True


class HTTPSJWKSTransport:
    def __init__(self, configuration: HTTPSConfiguration | None = None, *,
                 tls_context: ssl.SSLContext | None = None, http_transport_factory=None):
        if tls_context is not None and (tls_context.verify_mode != ssl.CERT_REQUIRED or not tls_context.check_hostname):
            raise ValueError('TLS verification and hostname checking must remain enabled')
        self._config, self._tls = configuration, tls_context
        self._factory = http_transport_factory # explicit test injection; must obey asyncio cancellation

    def fetch(self, request: JWKSRequest) -> BufferedJWKSResponse:
        config = self._config
        if config is None: raise HTTPTransportFailure('disabled')
        if request.url != config.url: raise HTTPTransportFailure('target_mismatch')
        if (type(request.max_response_bytes) is not int or request.max_response_bytes <= 0
                or type(request.timeout_seconds) not in (int,float) or not math.isfinite(request.timeout_seconds)
                or request.timeout_seconds <= 0): raise HTTPTransportFailure('invalid_request_limits')
        if request.cancelled.is_set(): raise HTTPTransportFailure('cancelled')
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise HTTPTransportFailure('sync_entry_requires_worker')
        try:
            return asyncio.run(self._bounded_fetch(request))
        except HTTPTransportFailure:
            raise
        except Exception:
            raise HTTPTransportFailure('request_failed') from None

    async def _bounded_fetch(self, request):
        async def watch(task):
            while not task.done():
                if request.cancelled.is_set():
                    task.cancel()
                    return
                await asyncio.sleep(min(self._config.cancellation_poll_seconds,request.timeout_seconds))
        network = asyncio.create_task(self._request(request))
        watcher = asyncio.create_task(watch(network))
        try:
            async with asyncio.timeout(request.timeout_seconds):
                result = await network
            if request.cancelled.is_set(): raise HTTPTransportFailure('cancelled')
            return result
        except asyncio.CancelledError:
            raise HTTPTransportFailure('cancelled') from None
        except TimeoutError:
            raise HTTPTransportFailure('total_timeout') from None
        except httpx.ConnectTimeout:
            raise HTTPTransportFailure('connect_timeout') from None
        except httpx.ReadTimeout:
            raise HTTPTransportFailure('read_timeout') from None
        except httpx.TimeoutException:
            raise HTTPTransportFailure('io_timeout') from None
        except HTTPTransportFailure:
            raise
        except Exception:
            raise HTTPTransportFailure('request_failed') from None
        finally:
            network.cancel(); watcher.cancel()
            await asyncio.gather(network,watcher,return_exceptions=True)

    async def _request(self, request):
        c=self._config
        timeout=httpx.Timeout(connect=min(c.connect_timeout_seconds,request.timeout_seconds),
            read=min(c.read_timeout_seconds,request.timeout_seconds),write=min(c.write_timeout_seconds,request.timeout_seconds),
            pool=min(c.pool_timeout_seconds,request.timeout_seconds))
        transport = self._factory() if self._factory is not None else httpx.AsyncHTTPTransport(
            verify=self._tls if self._tls is not None else True, trust_env=False, retries=0,
            limits=httpx.Limits(max_connections=1,max_keepalive_connections=0))
        async with httpx.AsyncClient(transport=transport,timeout=timeout,follow_redirects=False,trust_env=False) as client:
            if request.cancelled.is_set(): raise HTTPTransportFailure('cancelled')
            async with client.stream('GET',c.url,headers={'Accept':'application/jwk-set+json, application/json',
                                                        'Accept-Encoding':'identity'},follow_redirects=False) as response:
                if str(response.url)!=c.url: raise HTTPTransportFailure('target_mismatch')
                # Redirect statuses return only metadata. No Location parsing/follow-up request.
                if response.status_code != 200:
                    return BufferedJWKSResponse(response.status_code,str(response.url),response.headers.get('content-type',''),())
                if response.headers.get('content-encoding','identity').lower()!='identity':
                    raise HTTPTransportFailure('encoded_body_rejected')
                chunks=[]; size=0; bound=min(request.max_response_bytes,c.max_response_bytes)
                async for chunk in response.aiter_raw():
                    if request.cancelled.is_set(): raise HTTPTransportFailure('cancelled')
                    if len(chunks)>=c.max_chunks or size+len(chunk)>bound:
                        raise HTTPTransportFailure('body_limit')
                    chunks.append(chunk); size+=len(chunk)
                return BufferedJWKSResponse(response.status_code,str(response.url),response.headers.get('content-type',''),chunks)
