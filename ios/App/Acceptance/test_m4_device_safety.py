"""Local synthetic gate checks. Reads public certificate bytes, never a private key."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import importlib.util
import shutil
import sys
import plistlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from m4_artifacts import export_native_logs, verified_public_certificate
from m4_device import ROOT, configure_project, freeze_amap_key, private_directory, private_workspace, stage_accounts


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


class SDKKeySnapshotTests(unittest.TestCase):
    def test_rotation_cannot_change_packaged_bytes_or_scan_values(self):
        from m4_artifacts import redact
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'operator.plist'
            source.write_bytes(plistlib.dumps({'apiKey':'SYNTHETIC-BUILD-A'}))
            snapshot=freeze_amap_key(source,root)
            source.write_bytes(plistlib.dumps({'apiKey':'SYNTHETIC-ROTATED-B'}))
            self.assertEqual(plistlib.loads(snapshot.path.read_bytes()),{'apiKey':'SYNTHETIC-BUILD-A'})
            self.assertEqual(snapshot.path.stat().st_mode&0o777,0o600)
            cleaned,hits=redact('native SDK SYNTHETIC-BUILD-A',[snapshot.value])
            self.assertEqual(hits,1);self.assertNotIn('SYNTHETIC-BUILD-A',cleaned)
            self.assertNotIn('SYNTHETIC-BUILD-A',repr(snapshot))


class OneUseInputTests(unittest.TestCase):
    def test_mac_input_is_removed_after_copy_success_failure_and_exception(self):
        for outcome in [0,1,'exception']:
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as directory:
                source_paths=[]
                def invoke(arguments,**kwargs):
                    if 'copy' in arguments:
                        source=Path(arguments[arguments.index('--source')+1]);source_paths.append(source)
                        self.assertTrue(source.exists());self.assertEqual(source.stat().st_mode&0o777,0o600)
                        if outcome=='exception':raise OSError('synthetic copy interruption')
                        return SimpleNamespace(returncode=outcome)
                    return SimpleNamespace(returncode=0)
                with patch('m4_device.subprocess.run',side_effect=invoke):
                    if outcome==0:stage_accounts('synthetic-device','synthetic.bundle',Path('synthetic.app'),Path(directory),{'A':'SYNTHETIC'})
                    else:
                        with self.assertRaises((RuntimeError,OSError)):
                            stage_accounts('synthetic-device','synthetic.bundle',Path('synthetic.app'),Path(directory),{'A':'SYNTHETIC'})
                self.assertTrue(source_paths)
                self.assertTrue(all(not source.exists() for source in source_paths))


class DeviceWorkspaceTests(unittest.TestCase):
    def test_public_beta_app_does_not_bundle_the_control_server_pin(self):
        spec=importlib.util.spec_from_file_location('m4_fixture_generator',ROOT/'scripts/check_ios_trip_confirm.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            builder=object.__new__(module.XCTestDriver);builder.directory=Path(directory);builder.write_project(0)
            project=builder.directory/'G2CAcceptance.xcodeproj'
            original_app_phase=next(line for line in (project/'project.pbxproj').read_text().splitlines() if line.startswith('000000000000000000000120 ='))
            tls=SimpleNamespace(public_der=b'SYNTHETIC-PUBLIC-CERTIFICATE',team='SYNTHETIC1')
            configure_project(project,tls,'https://192.168.1.1:1234','SYNTHETIC-CONTROL',
                bundle='space.go2china.beta.acceptance',app_local_tls=False)
            pbx=(project/'project.pbxproj').read_text()
            app_phase=next(line for line in pbx.splitlines() if line.startswith('000000000000000000000120 ='))
            control_phase=next(line for line in pbx.splitlines() if line.startswith('A00000000000000000000009 ='))
            self.assertEqual(app_phase,original_app_phase)
            self.assertIn('files = (E',control_phase)
            self.assertNotIn('name = Production;',pbx)

    def test_implicit_build_and_generated_inputs_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'exports';output.mkdir()
            private,build=private_workspace(output)
            try:
                self.assertFalse(private.is_relative_to(output))
                self.assertEqual(private.stat().st_mode&0o777,0o700)
                self.assertTrue(build.is_relative_to(private))
                self.assertEqual(list(output.iterdir()),[])
            finally:shutil.rmtree(private)

    def test_nested_or_symlinked_export_build_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'exports';output.mkdir()
            alias=root/'alias';alias.symlink_to(output,target_is_directory=True)
            for build in (output,output/'dd',root,alias/'dd'):
                with self.subTest(build=build):
                    with self.assertRaises(ValueError):private_workspace(output,build)

    def test_actual_temp_destination_under_export_is_rejected_before_inputs(self):
        from m4_native import DeviceNative
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'exports';temporary=output/'native-temp';temporary.mkdir(parents=True)
            with patch('tempfile.tempdir',str(temporary)):
                with self.assertRaises(ValueError):private_workspace(output,root/'build')
                with self.assertRaises(ValueError):private_directory(output,'raw-native-')
                with self.assertRaises(ValueError):DeviceNative('SYNTHETIC','synthetic.bundle',root/'project',
                    root/'config',root/'build',root,output/'case',{},'SYNTHETIC-CONTROL',{},evidence_root=output)
            self.assertEqual(list(temporary.iterdir()),[])

    def test_matrix_rejects_build_under_aggregate_exports_before_any_child(self):
        spec=importlib.util.spec_from_file_location('m4_matrix',ROOT/'ios/App/Acceptance/check_m4_app.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'exports'
            arguments=['matrix','--device','SYNTHETIC','--local-tls','SYNTHETIC',
                '--run-context','SYNTHETIC','--output',str(output),'--build-dir',str(output/'derived'),
                '--prepare-only','--step','accounts']
            with patch.object(sys,'argv',arguments),patch('m4_device.LocalTLS.load'),patch.object(module.subprocess,'run') as child:
                with self.assertRaisesRegex(ValueError,'separate'):module.main()
                child.assert_not_called()
            self.assertFalse(output.exists())

    def test_actual_generator_removes_production_in_both_device_modes(self):
        spec=importlib.util.spec_from_file_location('m4_fixture_generator',ROOT/'scripts/check_ios_trip_confirm.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for release in (False,True):
            with self.subTest(include_release=release),tempfile.TemporaryDirectory() as directory:
                builder=object.__new__(module.XCTestDriver);builder.directory=Path(directory)
                builder.write_project(0)
                project=builder.directory/'G2CAcceptance.xcodeproj'
                tls=SimpleNamespace(public_der=b'SYNTHETIC-PUBLIC-CERTIFICATE',team='SYNTHETIC1')
                bundle,config,_=configure_project(project,tls,'https://192.168.1.1:1234','SYNTHETIC-CONTROL',include_release=release)
                pbx=(project/'project.pbxproj').read_text()
                self.assertNotIn('name = Production;',pbx)
                self.assertNotIn('PRODUCT_BUNDLE_IDENTIFIER = space.go2china.app;',pbx)
                project_configs='000000000000000000000012'+(', 000000000000000000000013' if release else '')
                app_configs='000000000000000000000014'+(', 000000000000000000000015' if release else '')
                self.assertIn('buildConfigurations = ('+project_configs+');',pbx)
                self.assertIn('buildConfigurations = ('+app_configs+');',pbx)
                if release:self.assertIn('M4_LOCAL_CERT_EXCLUDE_Release_CJProbeApp = G2CM4LocalServer.cer',config.read_text())


if __name__=='__main__':unittest.main()
