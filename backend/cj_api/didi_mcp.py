"""Fixed-host DiDi JSON-RPC transport for the information-only taxi adapter."""

from contextlib import closing
from enum import Enum
from http.client import HTTPSConnection, HTTPException
import json
from urllib.parse import urlencode

from cj_strict_json import compact, reject_duplicates


HOST = 'mcp.didichuxing.com'
ENDPOINT = '/mcp-servers'
MAX_REPLY = 512 * 1024


class DiDiTool(str, Enum):
    TEXT_SEARCH = 'maps_textsearch'
    REGEOCODE = 'maps_regeocode'
    ESTIMATE = 'taxi_estimate'
    LINK = 'taxi_generate_ride_app_link'


class DiDiMCPTransport:
    def __init__(self, key, *, connection=HTTPSConnection):
        if not key or len(key) > 512 or any(not 33 <= ord(char) <= 126 for char in key):
            raise ValueError('invalid_didi_key_config')
        self._key = key
        self._connection = connection

    def __call__(self, tool: DiDiTool, arguments):
        endpoint = ENDPOINT + '?' + urlencode({'key': self._key})
        payload = compact(dict(jsonrpc='2.0', id=1, method='tools/call',
                               params=dict(name=tool.value, arguments=arguments)))
        try:
            with closing(self._connection(HOST, timeout=8)) as client:
                client.request('POST', endpoint, body=payload, headers={
                    'Content-Type': 'application/json; charset=utf-8',
                    'Accept': 'application/json, text/event-stream',
                })
                with closing(client.getresponse()) as response:
                    if response.status in {401, 403}:
                        return {'error': {'code': -32002}}
                    if response.status == 429:
                        return {'error': {'code': -32001}}
                    if (response.status != 200 or
                            (response.getheader('Content-Type') or '').partition(';')[0].strip().lower()
                            != 'application/json'):
                        raise OSError('didi_reply_unavailable')
                    raw = response.read(MAX_REPLY + 1)
                    if len(raw) > MAX_REPLY or self._key.encode() in raw or endpoint.encode() in raw:
                        raise OSError('didi_reply_unavailable')
            packet = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate DiDi field'))
            if (type(packet) is not dict or packet.get('jsonrpc') != '2.0'
                    or type(packet.get('id')) is not int or packet['id'] != 1
                    or ('result' in packet) == ('error' in packet)):
                raise OSError('didi_reply_unavailable')
            if 'error' in packet:
                error = packet['error']
                code = error.get('code') if type(error) is dict else None
                return {'error': {'code': code if type(code) is int else None}}
            return packet['result']
        except TimeoutError:
            raise TimeoutError('didi_http_timeout') from None
        except (HTTPException, OSError, RecursionError, ValueError):
            # The endpoint carries the credential. Never expose supplier or HTTP exception details.
            raise OSError('didi_http_unavailable') from None
