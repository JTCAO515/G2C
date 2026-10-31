"""Shared route helpers: exact failure mapping callers rely on."""
import asyncio
import json
from types import SimpleNamespace
import unittest

from starlette.datastructures import Headers

from cj_api.history_routes import _message_id_query
from cj_api.message_routes import (BodyError, ReadInterrupted, _body_error, _read_body, _read_octets,
                                   _sanitized_read)


class Interrupted(BaseException):
    pass


class StreamFault(Exception):
    pass


def request(*, chunks=(b'ab', b'c'), content_type='application/octet-stream', encoding=None, fault=None, query=b''):
    raw = [(b'content-type', content_type.encode())] if content_type else []
    if encoding:
        raw.append((b'content-encoding', encoding.encode()))

    async def stream():
        for chunk in chunks:
            yield chunk
        if fault:
            raise fault
    return SimpleNamespace(headers=Headers(raw=raw), stream=stream, state=SimpleNamespace(request_id='00000000-0000-4000-8000-000000000000'),
                           scope={'query_string': query})


class BodyTests(unittest.TestCase):
    def read(self, value, limit=3):
        return asyncio.run(_read_octets(value, limit))

    def refused(self, value, limit=3):
        with self.assertRaises(BodyError) as caught:
            self.read(value, limit)
        return caught.exception.status, caught.exception.code

    def test_exact_bytes_at_limit(self):
        self.assertEqual(self.read(request()), b'abc')
        self.assertEqual(self.read(request(content_type='Application/Octet-Stream; x=1')), b'abc')

    def test_media_encoding_and_size_refused(self):
        for value in (request(content_type='application/json'), request(content_type=None),
                      request(encoding='gzip')):
            self.assertEqual(self.refused(value), (415, 'UNSUPPORTED_MEDIA_TYPE'))
        self.assertEqual(self.refused(request(), limit=2), (413, 'BODY_TOO_LARGE'))

    def test_stream_fault_stays_with_the_caller(self):
        with self.assertRaises(StreamFault):
            self.read(request(fault=StreamFault()))

    def test_message_body_maps_stream_fault(self):
        with self.assertRaises(BodyError) as caught:
            asyncio.run(_read_body(request(fault=StreamFault()), 3))
        self.assertEqual((caught.exception.status, caught.exception.code), (503, 'BODY_UNAVAILABLE'))

    def test_body_error_response(self):
        response = _body_error(request(), BodyError(413, 'BODY_TOO_LARGE'))
        self.assertEqual(response.status_code, 413)
        error = json.loads(response.body)['error']
        self.assertEqual((error['code'], error['category'], error['outcome'], error['recovery']),
                         ('BODY_TOO_LARGE', 'input', 'failed', 'do_not_retry'))


class SanitizedReadTests(unittest.TestCase):
    def test_value_and_ordinary_failure_pass_through(self):
        self.assertEqual(_sanitized_read(lambda: b'body'), b'body')
        fault = ValueError('original')

        def fail():
            raise fault
        with self.assertRaises(ValueError) as caught:
            _sanitized_read(fail)
        self.assertIs(caught.exception, fault)

    def test_reader_interruption_is_sanitized(self):
        def interrupted():
            raise Interrupted()
        with self.assertRaises(ReadInterrupted) as caught:
            _sanitized_read(interrupted)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)


class MessageIdTests(unittest.TestCase):
    def query(self, raw, limit=8):
        return _message_id_query(request(query=raw), limit)

    def status(self, raw, limit=8):
        return self.query(raw, limit).status_code

    def test_original_id_is_returned_exactly(self):
        self.assertEqual(self.query(b'message_id=m%C3%A9'), 'mé')

    def test_invalid_and_oversize_refused(self):
        for raw in (b'', b'message_id=', b'message_id=%20', b'message_id=a%00b', b'other=1',
                    b'message_id=a&message_id=b', b'message_id=%zz'):
            self.assertEqual(self.status(raw), 400, raw)
        self.assertEqual(self.status(b'message_id=123456789'), 413)
