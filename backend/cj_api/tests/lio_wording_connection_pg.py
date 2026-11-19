"""Native4 wording connection phase against the actual signed plan host."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
import lio_pipeline_models_pg as pipeline
from cj_agent.provider import M4_BASE, MeteredDashScopeProvider
from cj_agent.worker import RunWorker
from cj_message.lio_pipeline_schema import WORDING

original_init = MeteredDashScopeProvider.__init__
original_registered = RunWorker._registered_stream
profile = ContextVar("signed_wording_profile", default=None)
original_post = TestClient.post
active = {}
waited = []
sent = []


def post(api, url, **kwargs):
    response = original_post(api, url, **kwargs)
    if url == '/v4/lio/messages' and response.status_code == 200:
        body = response.json()
        active.update(api=api, headers=kwargs['headers'], conversation=body['conversation_id'])
    return response


def read_timeline():
    return active['api'].get('/v4/lio/timeline', headers=active['headers'],
        params={'conversation_id': active['conversation']})


def read_while_waiting():
    sent_before = len(sent)
    with ThreadPoolExecutor(max_workers=3) as readers:
        pages = tuple(readers.map(lambda _: read_timeline(), range(3)))
    assert len(sent) == sent_before, 'wording must not write POST before connecting'
    statuses = tuple(page.status_code for page in pages)
    for page in pages:
        if page.status_code == 200:
            current = page.json()['messages'][-1]
            assert current['status'] == 'answering' and current['trip'] is None
    waited.append(statuses)
    print('wording while connecting', statuses, flush=True)


async def dial(host, port, *, server_hostname, **options):
    assert host == server_hostname == 'dashscope.aliyuncs.com' and port == 443
    transport = active['fixture']
    selected = profile.get() == WORDING
    if selected:
        await asyncio.to_thread(read_while_waiting)
    reader = asyncio.StreamReader()

    def send(raw):
        headers, _, packet = raw.partition(b'\r\n\r\n')
        assert headers.startswith(b'POST /compatible-mode/v1/chat/completions ')
        response = transport.handle_request(httpx.Request('POST', M4_BASE+'/chat/completions', content=packet))
        assert response.status_code == 200
        payload = response.read()
        if selected:
            sent.append(True)
        head = ('HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                f'Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n').encode()
        reader.feed_data(head + payload)
        reader.feed_eof()

    return reader, SimpleNamespace(write=send, drain=AsyncMock(), transport=SimpleNamespace(abort=lambda: None))


def init(provider, config, authorization, *, transport=None):
    assert type(transport) is httpx.MockTransport
    active['fixture'] = transport
    original_init(provider, config, authorization)


def registered(worker, binding, key, registration, argument, **kwargs):
    stage = argument.profile if registration == 'model.lio_exploration.1' else None
    stream = original_registered(worker, binding, key, registration, argument, **kwargs)
    try:
        while True:
            token = profile.set(stage)
            try:
                chunk = next(stream)
            except StopIteration:
                return
            finally:
                profile.reset(token)
            yield chunk
    finally:
        stream.close()


def check_wording_connections(run, **scenario):
    active.clear()
    waited.clear()
    sent.clear()
    with patch.object(TestClient, 'post', post), patch.object(MeteredDashScopeProvider, '__init__', init), \
         patch.object(RunWorker, '_registered_stream', registered), patch('asyncio.open_connection', new=dial):
        run(**scenario)

    assert len(sent) == len(waited) and len(waited) >= 2, (len(sent), len(waited))
    assert all(codes == (200, 200, 200) for codes in waited), waited


if __name__ == '__main__':
    check_wording_connections(pipeline.main, production=True, cases=(0,), followups=False)
