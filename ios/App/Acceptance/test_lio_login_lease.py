import copy
from datetime import datetime, timezone
import hashlib
import unittest
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
import official_lio_sign_in as login
from lio_basic_ui_projection import EvidenceUnknown
from contextlib import redirect_stderr
from unittest.mock import patch
from official_lio_sign_in import main as sign_in

from lio_basic_ui_driver import compact
from lio_login_lease import validate_login_lease


class LoginLeaseTests(unittest.TestCase):
    def setUp(self):
        self.app = dict(source_commit='a' * 40, build='46', surface='simulator', protocol='LIO-message.2')
        self.sims = dict(zh='11111111-1111-4111-8111-111111111111', en='22222222-2222-4222-8222-222222222222')
        self.expected = dict(app=self.app, source='b' * 40, image='sha256:' + 'c' * 64,
                             simulator_udids=self.sims, subjects=dict(zh='synthetic-zh', en='synthetic-en'))
        self.value = dict(version='B-App-login-lease.1', state='SIGN_IN_ONLY_ISSUED',
            purpose='C1048-basic14-official-App-sign-in-only', lease_id='synthetic-lease', app=self.app,
            app_pin_sha256=hashlib.sha256(compact(self.app, sort_keys=True)).hexdigest(),
            source=self.expected['source'], image=self.expected['image'], simulator_udids=self.sims,
            starts_at='2026-11-16T12:00:00Z', ends_at='2026-11-16T12:05:00Z',
            identities=[dict(locale='zh', subject='synthetic-zh', invite_file='/synthetic/zh-invite'),
                        dict(locale='en', subject='synthetic-en', invite_file='/synthetic/en-invite')],
            file_format='one_ascii_line_no_lf_preserve_bytes',
            official_ui=dict(field='demo.invite.code', kind='SecureField', submit='existing_official_App_login_action'),
            allowed_actions=['official_sign_in', 'app_automatic_read_only_loading'])
        self.now = datetime(2026, 11, 16, 12, 1, tzinfo=timezone.utc)

    def check(self, value, *, now=None, raw=None, digest=None):
        raw = compact(value, sort_keys=True) if raw is None else raw
        return validate_login_lease(raw, digest or hashlib.sha256(raw).hexdigest(), self.expected, now or self.now)

    def test_valid_metadata_selects_only_its_locale_without_opening_any_invite(self):
        result = self.check(self.value)
        self.assertEqual(result['zh']['invite_file'], '/synthetic/zh-invite')
        self.assertEqual(result['en']['subject'], 'synthetic-en')

    def test_not_issued_wrong_app_source_udid_identity_or_action_are_rejected(self):
        changes = [dict(state='NOT_ISSUED_NO_LOGIN_AUTHORITY'), dict(app=dict(self.app, build='45')),
                   dict(source='d' * 40), dict(image='sha256:' + 'd' * 64),
                   dict(simulator_udids=dict(self.sims, en=self.sims['zh'])),
                   dict(allowed_actions=['official_sign_in', 'send']), dict(extra='unknown')]
        for change in changes:
            with self.subTest(change=tuple(change)):
                with self.assertRaises(ValueError): self.check(dict(self.value, **change))
        value = copy.deepcopy(self.value); value['identities'][1]['subject'] = 'another'
        with self.assertRaises(ValueError): self.check(value)

    def test_unknown_duplicate_nonfinite_or_changed_file_cannot_open_a_lease(self):
        raw = compact(self.value, sort_keys=True)
        for bad in [b'{"state":"NO",' + raw[1:], raw.replace(b'"build":"46"', b'"build":NaN')]:
            with self.assertRaises(ValueError): self.check(self.value, raw=bad)
        with self.assertRaises(ValueError): self.check(self.value, digest='0' * 64)

    def test_time_is_utc_bounded_current_and_within_the_beijing_day(self):
        cases = [dict(starts_at='2026-11-16T12:02:00Z'), dict(ends_at='2026-11-16T12:01:00Z'),
                 dict(ends_at='2026-11-16T12:11:00Z'), dict(starts_at='2026-11-16T12:00:00'),
                 dict(starts_at='2026-11-16T14:59:00Z', ends_at='2026-11-16T15:05:00Z')]
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValueError): self.check(dict(self.value, **change))

    def test_artifact_pin_mismatch_stops_before_native_or_invitation_access(self):
        packet = dict(version='LIO-A-official-sign-in-packet.1', expected_login=dict(app=self.app),
                      artifact=dict(app=dict(self.app, build='45')))
        raw = compact(packet, sort_keys=True)
        args = ['sign-in', '--packet', '/synthetic/packet', '--packet-sha256', hashlib.sha256(raw).hexdigest(),
                '--lease', '/synthetic/lease', '--lease-sha256', 'a' * 64, '--locale', 'en', '--output', '/synthetic/output']
        with patch('sys.argv', args), patch('official_lio_sign_in.read_private_bytes', return_value=raw) as read, \
                patch('official_lio_sign_in.AdmittedNativeUI') as native, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure: sign_in()
            self.assertEqual(failure.exception.code, 2)
            self.assertEqual(read.call_count, 1)
            native.assert_not_called()

    def test_same_lease_locale_cannot_repeat_official_submit_with_a_new_output_directory(self):
        packet = dict(version='LIO-A-official-sign-in-packet.1', expected_login=self.expected,
                      artifact=dict(app=self.app), build_directory='/synthetic/build')
        packet_raw, lease_raw = compact(packet, sort_keys=True), compact(self.value, sort_keys=True)
        calls = []
        class Native:
            def __init__(self, *args, **kwargs):
                self.sequence = 0; self.commands = Path('/synthetic/commands')
                self.snapshots = iter([[dict(identifier='demo.invite.code')],
                                       [dict(identifier='demo.invite.signin', enabled=True)],
                                       [dict(identifier='demo.invite.error')]])
            def command(self, kind, **fields):
                self.sequence += 1; calls.append((kind, fields.get('identifier')))
                if kind == 'snapshot': return dict(nodes=next(self.snapshots), screenshot='synthetic.png')
                return {}
            def close(self): pass
        with tempfile.TemporaryDirectory() as folder:
            for number in (1, 2):
                argv = ['login', '--packet', '/synthetic/packet', '--packet-sha256', hashlib.sha256(packet_raw).hexdigest(),
                        '--lease', '/synthetic/lease', '--lease-sha256', hashlib.sha256(lease_raw).hexdigest(),
                        '--locale', 'zh', '--output', str(Path(folder) / str(number))]
                with patch('sys.argv', argv), patch.object(login, 'ATTEMPT_DIRECTORY', Path(folder) / 'attempts', create=True), \
                        patch.object(login, 'read_private_bytes', side_effect=lambda path: packet_raw if str(path).endswith('packet') else lease_raw), \
                        patch.object(login, 'datetime', SimpleNamespace(now=lambda tz: self.now)), \
                        patch.object(login, 'verify_installation'), patch.object(login, 'AdmittedNativeUI', Native), \
                        patch.object(login, 'artifact', return_value=dict(path='/synthetic', sha256='0' * 64)):
                    with self.assertRaises(EvidenceUnknown): login.main()
            self.assertEqual(sum(kind == 'private_invite' for kind, _ in calls), 1)
            self.assertEqual(sum(kind == 'tap' and identifier == 'demo.invite.signin' for kind, identifier in calls), 1)


if __name__ == '__main__': unittest.main()
