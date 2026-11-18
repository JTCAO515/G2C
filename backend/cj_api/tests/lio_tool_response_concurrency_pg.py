"""Signed Lio timeline during a real registered tool transport's response wait."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import socket
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cj_agent.provider import _M4_REQUEST_SENT, DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_app import load_confirmation_signer
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices, RealTools
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
import run_worker
from test_lio_city import data as city_catalog
from test_lio_planning_flow import flow

ADDRESS = ('1.1.1.1', 443)
FIXTURE_CREDENTIAL = 'local-fixture-not-live'
CASES = (
    ('weather', '成都明天的天气怎么样？', '成都'),
    ('place_search', '成都有哪些博物馆？', '成都'),
    ('fact', '中国240小时过境免签有哪些条件？', None),
)


class PendingReader(asyncio.StreamReader):
    def __init__(self, ready, release, response):
        super().__init__()
        self.ready = ready
        self.release = release
        self.response = response

    async def receive(self):
        if self.response is not None:
            self.ready.set()
            assert await asyncio.to_thread(self.release.wait, 12)
            self.feed_data(self.response)
            self.feed_eof()
            self.response = None

    async def read(self, *args):
        await self.receive()
        return await super().read(*args)

    async def readuntil(self, separator=b'\n'):
        await self.receive()
        return await super().readuntil(separator)


class MockWriter:
    def __init__(self, writes):
        self.writes = writes
        self.transport = self

    def write(self, wire):
        assert wire.startswith(b'GET ')
        self.writes.append(wire.split(b' ', 2)[1].split(b'?')[0])

    async def drain(self):
        pass

    def get_extra_info(self, kind):
        return ADDRESS if kind == 'peername' else SimpleNamespace(selected_alpn_protocol=lambda: 'http/1.1')

    def close(self):
        pass

    async def wait_closed(self):
        pass

    def abort(self):
        pass


def check_tool_response(api, headers, database, auth, subject, scope, memory, root):
    subjects = frozenset({subject})
    signer = load_confirmation_signer(auth)
    observed = {}
    for name, text, city in CASES:
        ready, release = Event(), Event()
        writes, models = [], []
        budget = AuthorizationBudget(root / ('response-' + name),
            clock=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
        model = MeteredDashScopeProvider(
            DashScopeConfig(M4_BASE, M4_MODEL, FIXTURE_CREDENTIAL, max_output_tokens=1536), budget)
        services = RealServices(model, FIXTURE_CREDENTIAL, subjects,
            demo_subjects=subjects, national_subjects=subjects)
        tools = RealTools(services, buffered_streaming_subjects=subjects)
        worker = run_worker._worker_for_scope(database, model, auth, scope, checker_for(auth),
            memory_configuration=memory, tools_configuration=tools, draft_profile='needs-structured.1',
            assembly_planning=True, demo_planning=True, national_planning=True, lio_confirmation=signer)
        day = (datetime.now(ZoneInfo('Asia/Shanghai')).date() + timedelta(days=1)).isoformat()
        arguments = (dict(keyword='博物馆', city='510100', page=1, page_size=2) if name == 'place_search'
                     else dict(start_date=day, end_date=day))
        mime = 'application/json'
        if name == 'fact':
            mime = 'text/html'
            response = (b'<h2>240-Hour Visa-Free Transit Policy</h2>'
                        b'<p>Only for this fixture, the policy excerpt contains 240 hours.</p>')
        elif name == 'weather':
            response = json.dumps(dict(status='1', infocode='10000', count='1',
                forecasts=[dict(adcode='510100', casts=[dict(date=day, dayweather='Sunny')])])).encode()
        else:
            response = json.dumps(dict(status='1', info='OK', infocode='10000', count='1',
                pois=[dict(id='SYNTH_ONLY', name='Synthetic Museum', location='104.1,30.1')])).encode()
        http = (f'HTTP/1.1 200 OK\r\nContent-Type: {mime}\r\nContent-Length: {len(response)}\r\nConnection: close\r\n\r\n'
                .encode() + response)

        async def connect(*args, **kwargs):
            expect = 'en.nia.gov.cn' if name == 'fact' else 'restapi.amap.com'
            assert kwargs.get('server_hostname') == expect
            return PendingReader(ready, release, http), MockWriter(writes)

        async def address(loop, host, port, **kwargs):
            assert name == 'fact' and host == 'en.nia.gov.cn' and port == 443
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ADDRESS)]

        async def pinned_connect(loop, sock, peer):
            assert name == 'fact' and peer == ADDRESS

        async def catalogue(key, guard):
            assert guard() is True
            return city_catalog()

        async def wire(config, raw, guard, observation):
            assert guard() is True
            payload = json.loads(raw)
            schema = payload.get('response_format', {}).get('json_schema', {}).get('schema', {})
            index = schema.get('properties', {}).get('current_source_index', {}).get('const')
            if index is not None:
                value = flow(text, city=city, days=None, intent='consult', questions=(), index=index)
                value.update(version='LIO-planning-intake.8', planning_request_index=None, needs_tools=True)
                stage, delta, finish = 'intake', {'content': json.dumps(value, ensure_ascii=False)}, 'stop'
            elif any(row['role'] == 'tool' for row in payload['messages']):
                stage, delta, finish = 'followup', {'content': '可以从这里继续，想了解哪一点？'}, 'stop'
            else:
                stage, finish = 'tool', 'tool_calls'
                assert name in [tool['function']['name'] for tool in payload['tools']]
                delta = dict(tool_calls=[dict(index=0, id='signed-local-tool', type='function',
                    function=dict(name=name, arguments=json.dumps(arguments, ensure_ascii=False)))])
            models.append(stage)
            yield _M4_REQUEST_SENT
            observation['http_status'] = 200
            packet = dict(id='signed-tool-'+name+'-'+stage, model=M4_MODEL,
                choices=[dict(index=0, delta=delta, finish_reason=finish)],
                usage=dict(prompt_tokens=100, completion_tokens=100, total_tokens=200))
            yield ('data: '+json.dumps(packet, ensure_ascii=False)+'\n\ndata: [DONE]\n\n').encode()

        def send(mid, message, **target):
            result = api.post('/v2/lio/messages', headers=headers, content=encode(dict(
                version='LIO-message.2', message_id=mid, text=message, locale='zh', **target)))
            assert result.status_code == 200, result.status_code
            return result.json()['conversation_id']

        seed, mid = 'signed-tool-'+name+'-seed', 'signed-tool-'+name+'-pending'
        cid = send(seed, '你是谁', new_conversation=True)
        assert [item.status for item in worker.process()] == ['completed']
        send(mid, text, conversation_id=cid)

        def timeline():
            return api.get('/v2/lio/timeline', headers=headers, params={'conversation_id':cid})

        pinned_socket = SimpleNamespace(AF_INET=socket.AF_INET, AF_INET6=socket.AF_INET6,
            SOCK_STREAM=socket.SOCK_STREAM, socket=lambda *args: SimpleNamespace(
                setblocking=lambda value: None, getpeername=lambda: ADDRESS, close=lambda: None))
        with patch('asyncio.open_connection', new=connect), \
             patch.object(asyncio.BaseEventLoop, 'getaddrinfo', new=address), \
             patch.object(asyncio.SelectorEventLoop, 'sock_connect', new=pinned_connect), \
             patch('cj_fact.https_transport.socket', new=pinned_socket), \
             patch('cj_api.lio_city._catalog_exchange', new=catalogue), \
             patch('cj_agent.provider._m4_wire', new=wire), ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(worker.process)
            try:
                assert ready.wait(6), (name, future.result(timeout=0.1))
                assert len(writes) == 1
                kind = 'place' if name == 'place_search' else name
                assert [(row['kind'], row['state']) for row in budget.inspect() if row['state'] == 'INTENT'] == [(kind, 'INTENT')]
                with ThreadPoolExecutor(max_workers=3) as readers:
                    pages = tuple(readers.map(lambda _: timeline(), range(3)))
                observed[name] = [page.status_code for page in pages]
                print(f'signed tool response wait {name} timeline statuses {observed[name]}', flush=True)
                for page in pages:
                    if page.status_code == 200:
                        original, current = page.json()['messages']
                        assert (original['message_id'], original['status']) == (seed, 'completed')
                        assert (current['message_id'], current['status'], current['trip']) == (mid, 'answering', None)
            finally:
                release.set()
            outcome, = future.result(timeout=12)
        assert outcome.status == 'completed' and outcome.proposal_id is None, (name, models, outcome.status)
        assert models == ['intake', 'tool', 'followup'] and len(writes) == 1, (name, models)
        receipts = [(row['kind'], row['state']) for row in budget.inspect()]
        expected = ['model'] * 3 + [kind] + (['place'] if city is not None else [])
        assert sorted(receipts) == sorted((item, 'RECEIVED') for item in expected), receipts
        final = timeline()
        assert final.status_code == 200
        last = final.json()['messages'][-1]
        assert (last['message_id'], last['status'], last['trip'], last['memory']) == (mid, 'completed', None, None)
        assert last['answer']
        if name == 'fact':
            assert '240 小时' in last['answer']
            source, = last['sources']
            assert source['title'] == '国家移民管理局' and source['url'].startswith('https://en.nia.gov.cn/')
    assert all(statuses == [200, 200, 200] for statuses in observed.values()), observed
