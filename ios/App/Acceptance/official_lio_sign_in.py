"""One B-issued official App sign-in. No business smoke or credential injection.

The invitation is opened only by the native UITest process and entered through
the real SecureField. This process reads lease metadata, never invite contents.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import os
import stat
from pathlib import Path
import time

from lio_basic_smoke_capture import artifact, verify_installation
from lio_basic_ui_driver import compact, decode, write
from lio_basic_ui_projection import EvidenceUnknown
from lio_login_lease import validate_login_lease
from watch_lio_basic_smoke import AdmittedNativeUI, read_private_bytes


ATTEMPT_DIRECTORY = Path.home() / '.local/share/g2c/a1048-official-login-attempts'


def claim_login_attempt(lease_id, locale):
    """Durable single attempt, independent of caller-selected output paths."""
    directory = ATTEMPT_DIRECTORY
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise EvidenceUnknown('The fixed private login-attempt directory is unavailable')
        name = hashlib.sha256(compact([lease_id, locale])).hexdigest() + '.intent.json'
        try:
            attempt = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
        except FileExistsError:
            raise EvidenceUnknown('This lease and locale already have an original attempt; do not retry') from None
        # Keep the marker even if writing, building or login later fails. Its
        # existence denotes an attempted operation, not a successful sign-in.
        with os.fdopen(attempt, 'wb') as stream:
            stream.write(compact(dict(version='LIO-official-login-attempt.1', lease_id=lease_id,
                                      locale=locale, state='ATTEMPT_OUTCOME_UNKNOWN'), sort_keys=True))
            stream.flush(); os.fsync(stream.fileno())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--packet-sha256', required=True)
    parser.add_argument('--lease', type=Path, required=True)
    parser.add_argument('--lease-sha256', required=True)
    parser.add_argument('--locale', choices=('zh', 'en'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = read_private_bytes(args.packet)
    if hashlib.sha256(raw).hexdigest() != args.packet_sha256:
        parser.error('Sign-in packet differs from the separately approved pin')
    packet = decode(raw)
    if packet['version'] != 'LIO-A-official-sign-in-packet.1':
        parser.error('Unknown sign-in packet')
    expected = packet['expected_login']
    if packet['artifact']['app'] != expected['app']:
        parser.error('Installed artifact and login lease must bind the same complete App pin')

    def grant():
        data = read_private_bytes(args.lease)
        return validate_login_lease(data, args.lease_sha256, expected, datetime.now(timezone.utc))

    raw_lease = read_private_bytes(args.lease)
    selected = validate_login_lease(raw_lease, args.lease_sha256, expected, datetime.now(timezone.utc))[args.locale]
    lease = decode(raw_lease)
    output = args.output.resolve(); output.mkdir(mode=0o700, parents=True, exist_ok=False)
    simulator = expected['simulator_udids'][args.locale]
    started = datetime.now(timezone.utc).isoformat()
    def input_guard():
        data = read_private_bytes(args.lease)
        validate_login_lease(data, args.lease_sha256, expected, datetime.now(timezone.utc))
        current = decode(data)
        verify_installation(simulator, packet['artifact'])
        return dict(startsAt=current['starts_at'], endsAt=current['ends_at'])

    grant(); verify_installation(simulator, packet['artifact'])
    claim_login_attempt(lease['lease_id'], args.locale)
    native = AdmittedNativeUI(input_guard, output / 'native', simulator, 'space.go2china.app',
                             build_directory=packet['build_directory'])
    outcome = 'UNKNOWN'
    originals = []
    try:
        verify_installation(simulator, packet['artifact'])
        native.command('launch', language=args.locale)

        def snapshot():
            stem = f'{native.sequence:05d}'
            result = native.command('snapshot')
            originals.extend([artifact(native.commands / (stem + '.response.json')),
                              artifact(native.commands / result['screenshot'])])
            return result['nodes']

        nodes = snapshot()
        if any(n['identifier'] == 'lio.composer' for n in nodes):
            # Do not sign out or replace an existing session merely to consume
            # the invitation. Its actual server identity needs B's readback.
            outcome = 'EXISTING_SESSION_NEEDS_IDENTITY_READBACK'
        else:
            if not any(n['identifier'] == 'demo.invite.code' for n in nodes):
                raise EvidenceUnknown('Official invitation screen is unavailable')
            write(output / '00-input-intent.json', dict(lease_id=lease['lease_id'], locale=args.locale,
                  simulator=simulator, state='INPUT_NOT_ACKNOWLEDGED', at=datetime.now(timezone.utc).isoformat()))
            native.command('private_invite', privateInputPath=selected['invite_file'])
            # Check the immutable lease and actual build again immediately before
            # the normal submit actions; never retype or retry an uncertain tap.
            grant(); verify_installation(simulator, packet['artifact'])
            native.command('tap', identifier='demo.invite.continue')
            deadline = time.monotonic() + 20
            while True:
                nodes = snapshot()
                if any(n['identifier'] == 'demo.invite.signin' and n['enabled'] for n in nodes):
                    break
                if time.monotonic() >= deadline:
                    raise EvidenceUnknown('Official consent action did not become available')
                time.sleep(.2)
            grant(); verify_installation(simulator, packet['artifact'])
            write(output / '01-submit-intent.json', dict(lease_id=lease['lease_id'], locale=args.locale,
                  simulator=simulator, state='SUBMIT_NOT_ACKNOWLEDGED', at=datetime.now(timezone.utc).isoformat()))
            native.command('tap', identifier='demo.invite.signin')
            deadline = time.monotonic() + 45
            while True:
                nodes = snapshot()
                if any(n['identifier'] == 'lio.composer' for n in nodes):
                    outcome = 'SIGNED_IN_UI_NEEDS_IDENTITY_READBACK'
                    break
                if any(n['identifier'] in ('demo.invite.error', 'lio.session.notice') for n in nodes):
                    raise EvidenceUnknown('Official sign-in has a visible failure; preserve the original attempt')
                if time.monotonic() >= deadline:
                    raise EvidenceUnknown('Official sign-in outcome remains unknown; do not retry')
                time.sleep(.2)
    finally:
        write(output / 'result.json', dict(version='LIO-official-App-sign-in-observation.1',
              lease_id=lease['lease_id'], locale=args.locale, simulator=simulator,
              app=expected['app'], source=expected['source'], image=expected['image'],
              started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
              outcome=outcome, business_send_taps=0, artifacts=originals))
        native.close()


if __name__ == '__main__': main()
