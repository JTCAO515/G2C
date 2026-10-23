"""Credential-boundary controls using the same real private TLS response seam."""
from datetime import datetime, timezone
import unittest

from cj_place import Outcome, parse_response
from secret_echo_checks import SecretEchoChecks
from https_transport_checks import CONFIG, SENTINEL


class SecretBodyControls(SecretEchoChecks):
    async def test_inspectable_nonsecret_json_retains_exact_source_bytes(self):
        self.payload = (b' { "status" : "1", "info":"OK", "infocode":"10000", '
                        b'"count":"0", "pois":[], "extra":"\\u5408\\u6210" } \n')
        request, receipt = await self.call()
        self.assertEqual(receipt.state, "received")
        self.assertEqual(receipt.response.body, self.payload)
        self.assertEqual(receipt.response.binding_digest, request.binding_digest)
        result = parse_response(CONFIG, request, receipt.response, now=datetime.now(timezone.utc), evidence="synthetic")
        self.assertEqual(result.outcome, Outcome.NO_RESULTS)
        self.assertIs(result.source.query_started_at, request.started_at)

    async def test_uninspectable_bodies_without_literal_secret_also_drop_response(self):
        bodies = (
            b'{"duplicate":1,"duplicate":2}', b'{"truncated":', b'{"bad":"\xff"}',
            b'null', b'[]', b'{"bad":"\\ud800"}',
            b'{"number":1e9999999999999999999999999999999999999999}',
            b'{"deep":' + b'[' * 40 + b'0' + b']' * 40 + b'}',
        )
        for body in bodies:
            self.payload = body
            _, receipt = await self.call()
            self.assertEqual(receipt.state, "unknown")
            self.assertEqual(receipt.reason, "response_secret_check_unavailable")
            self.assertIsNone(receipt.response)
            self.assertNotIn(SENTINEL, repr(receipt))
        self.assertEqual(self.dials, len(bodies))


if __name__ == "__main__":
    suite = unittest.TestSuite(SecretBodyControls(name) for name in (
        "test_inspectable_nonsecret_json_retains_exact_source_bytes",
        "test_uninspectable_bodies_without_literal_secret_also_drop_response"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
