"""Regression: non-VALID results must carry exactly None, not merely a non-principal."""
import unittest
from cj_auth.interfaces import TrustedPrincipal, VerificationResult, VerificationStatus


class VerificationResultTests(unittest.TestCase):
    def setUp(self):
        self.principal = TrustedPrincipal('synthetic-issuer', 'synthetic-sub', 'synthetic-aud', 1, 1, 2)
        self.wrong_types = ('', 'synthetic-identity', 0, 1, False, True, [], ['synthetic'], {},
                            {'subject': 'synthetic'}, object())

    def test_nonvalid_requires_exact_none_for_empty_nonempty_and_wrong_types(self):
        for status in (VerificationStatus.INVALID, VerificationStatus.UNKNOWN):
            for value in (*self.wrong_types, self.principal):
                with self.subTest(status=status.value, value_type=type(value).__name__, empty=not bool(value)):
                    with self.assertRaises(ValueError):
                        VerificationResult(status, value)

    def test_nonvalid_accepts_none_only(self):
        for status in (VerificationStatus.INVALID, VerificationStatus.UNKNOWN):
            self.assertIsNone(VerificationResult(status).principal)
            self.assertIsNone(VerificationResult(status, None).principal)

    def test_valid_requires_trusted_principal(self):
        self.assertIs(VerificationResult(VerificationStatus.VALID, self.principal).principal, self.principal)
        for value in (None, *self.wrong_types):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    VerificationResult(VerificationStatus.VALID, value)

    def test_invalid_status_type_still_rejected(self):
        for status in ('valid', 'invalid', 'unknown', '', None, 0, True):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    VerificationResult(status, None)


if __name__ == '__main__': unittest.main()
