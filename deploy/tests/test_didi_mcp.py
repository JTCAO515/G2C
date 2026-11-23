from http.client import HTTPException
from io import BytesIO
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from cj_api.didi_mcp import DiDiMCPTransport
from cj_api.plugin_tools import PluginError
from cj_api.taxi_tools import DiDiInformation


@pytest.fixture
def wire():
    class Reply(BytesIO):
        status = 200

        def getheader(self, header):
            assert header == 'Content-Type'
            return 'application/json; charset=utf-8'

    class Connection:
        seen = []
        reply = Reply(b'{"jsonrpc":"2.0","id":1,"result":{"structuredContent":{"items":[]}}}')

        def __init__(self, host, timeout):
            assert (host, timeout) == ('mcp.didichuxing.com', 8)

        def request(self, method, path, *, body, headers):
            self.seen.append((method, path, json.loads(body), headers))

        def getresponse(self):
            return self.reply

        def close(self):
            pass

    return Connection, Reply


def test_transport_uses_only_fixed_post_and_puts_key_in_query(wire):
    connection, _ = wire
    transfer = DiDiInformation(DiDiMCPTransport('fixture+key', connection=connection))
    assert transfer.call('taxi_estimate', {'from_lat':'39.9'}) == {'structuredContent': {'items': []}}
    ((method, path, body, headers),) = connection.seen
    assert method == 'POST'
    assert urlsplit(path).path == '/mcp-servers'
    assert parse_qs(urlsplit(path).query) == {'key': ['fixture+key']}
    assert body == {'jsonrpc':'2.0', 'id':1, 'method':'tools/call',
                    'params': {'name':'taxi_estimate','arguments': {'from_lat':'39.9'}}}
    assert 'fixture' not in json.dumps(headers) + json.dumps(body)


@pytest.mark.parametrize('echo',[b'fixture+key',b'fixture\\u002bkey',b'fixture%2Bkey'])
def test_credential_echo_in_supplier_body_is_rejected(wire, echo):
    connection, reply = wire
    connection.reply = reply(b'{"jsonrpc":"2.0","id":1,"result":{"text":"'+echo+b'"}}')
    transfer = DiDiInformation(DiDiMCPTransport('fixture+key', connection=connection))
    with pytest.raises(PluginError, match='^supplier_unavailable$') as raised:
        transfer.call('taxi_estimate', {})
    assert 'fixture' not in str(raised.value)
    assert len(connection.seen) == 1


def test_transport_does_not_expose_http_exception_or_retry_ambiguous_request(wire):
    connection, _ = wire

    class Broken(connection):
        def request(self, *args, **kwargs):
            super().request(*args, **kwargs)
            raise HTTPException('/mcp-servers?key=fixture+key')

    transfer = DiDiInformation(DiDiMCPTransport('fixture+key', connection=Broken))
    with pytest.raises(PluginError, match='^supplier_unavailable$') as raised:
        transfer.call('taxi_estimate', {})
    assert str(raised.value) == 'supplier_unavailable'
    assert len(connection.seen) == 1
