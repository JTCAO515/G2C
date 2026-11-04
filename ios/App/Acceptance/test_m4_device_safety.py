"""Local synthetic gate checks. Reads public certificate bytes, never a private key."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from m4_artifacts import export_native_logs, verified_public_certificate


class CertificatePackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Synthetic in-memory test identity; no operational key is read/written.
        key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SYNTHETIC packaging fixture')])
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(datetime(2020,1,1,tzinfo=timezone.utc))
            .not_valid_after(datetime(2020,1,2,tzinfo=timezone.utc)).sign(key,hashes.SHA256()))
        cls.der = certificate.public_bytes(serialization.Encoding.DER)
        cls.pem = certificate.public_bytes(serialization.Encoding.PEM)

    def test_exact_public_certificate_is_reencoded(self):
        self.assertEqual(verified_public_certificate(self.pem, self.der), self.der)

    def test_private_or_mixed_inputs_are_rejected_before_packaging(self):
        sentinel = b'-----BEGIN PRIVATE KEY-----\nSYNTHETIC-NOT-A-KEY\n-----END PRIVATE KEY-----\n'
        for pem, der in [(sentinel,sentinel), (self.pem+sentinel,self.der),
                         (self.pem,self.der+sentinel), (b'damaged',self.der),
                         (self.pem,self.der[:-1]+bytes([self.der[-1]^1]))]:
            with self.subTest(pem_is_certificate=pem.startswith(b'-----BEGIN CERTIFICATE')):
                with self.assertRaises(ValueError):
                    verified_public_certificate(pem,der)


class NativeArtifactTests(unittest.TestCase):
    def check_export(self, exit_status, secret_in_native):
        secret = 'SYNTHETIC-PRIVATE-SENTINEL'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);raw = root/'quarantine.xcresult';raw.mkdir()
            output = root/'exports';output.mkdir()
            native = '{"message":"'+(secret if secret_in_native else 'safe')+'"}'
            with patch('m4_artifacts.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=native)):
                result = export_native_logs(raw,output,[secret],f'build exit {exit_status}')
            self.assertFalse(result['raw_bundle_shareable'])
            self.assertFalse(any(output.rglob('*.xcresult')))
            self.assertTrue(all(secret not in p.read_text() for p in output.iterdir()))
            if secret_in_native:
                self.assertEqual(result['status'],'FAIL')
                self.assertGreater(result['secret_hits'],0)
            else:self.assertTrue(result['status'].startswith('PASS'))

    def test_native_console_or_action_hit_is_not_success(self):
        for exit_status in [0,65]:
            with self.subTest(exit_status=exit_status):self.check_export(exit_status,True)

    def test_clean_exports_do_not_authorize_the_opaque_bundle(self):
        self.check_export(0,False)

    def test_missing_native_logs_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=root/'quarantine.xcresult';raw.mkdir()
            with patch('m4_artifacts.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout='')):
                result=export_native_logs(raw,root,[],'compile failed')
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual(set(result['missing_logs']),{'build','action','console'})


if __name__=='__main__':unittest.main()
