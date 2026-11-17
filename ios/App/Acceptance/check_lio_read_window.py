"""Exercise the actual native read fence on an owned, account-free simulator.

Only the separate Debug driver host is launched. No ordinary App, account,
credential, service or business qualification is used by these local controls.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from lio_basic_ui_driver import NativeUI, ROOT, HERE


HOST = 'space.go2china.smoke.driver-host'
RUNNER = 'space.go2china.foundation.control.xctrunner'


def stamp(value):
    return value.isoformat(timespec='seconds').replace('+00:00', 'Z')


def exercise(output, build, simulator, kind):
    native, paused = None, None
    controller = (HERE / 'LioBasicSmokeUI.swift').read_bytes()
    errors = []
    try:
        native = NativeUI(output, simulator, HOST, build_directory=build)
        start = datetime.now(timezone.utc) - timedelta(seconds=10)
        end = datetime.now(timezone.utc) + timedelta(seconds=120)
        native.command('launch', language='en', startsAt=stamp(start), endsAt=stamp(end))
        legacy = native.command('snapshot', startsAt='2020-01-01T00:00:00Z', endsAt='2020-01-01T00:00:01Z')
        assert type(legacy['nodes']) is list
        allowed = native.command('snapshot_in_window', startsAt=stamp(start), endsAt=stamp(end))
        assert type(allowed['nodes']) is list and allowed['screenshot'] == '00002.png'
        listing = subprocess.check_output(['xcrun', 'simctl', 'spawn', simulator, 'launchctl', 'list'], text=True)
        pids = {int(line.split()[0]) for line in listing.splitlines()
                if RUNNER in line and line.split()[0].isdigit()}
        assert len(pids) == 1, 'Expected one SDK runner in the owned simulator'
        paused = pids.pop()
        os.kill(paused, signal.SIGSTOP)
        sequence = native.sequence
        deadline = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=2)

        def dispatch():
            try:
                native.command(kind, startsAt=stamp(deadline - timedelta(seconds=20)), endsAt=stamp(deadline))
            except RuntimeError:
                errors.append('RuntimeError')

        thread = threading.Thread(target=dispatch)
        thread.start()
        request = output / 'commands' / f'{sequence:05d}.request.json'
        until = time.monotonic() + 5
        while not request.exists() and time.monotonic() < until:
            time.sleep(.05)
        assert request.exists()
        while datetime.now(timezone.utc) <= deadline:
            time.sleep(.05)
        os.kill(paused, signal.SIGCONT)
        paused = None
        thread.join(timeout=30)
        assert not thread.is_alive()
        denied = json.loads((output / 'commands' / f'{sequence:05d}.response.json').read_text())
        assert denied['kind'] == kind and denied['ok'] is False
        assert denied['error'] == 'native_UI_read_window_unavailable'
        assert 'nodes' not in denied and 'screenshot' not in denied
        assert not (output / 'commands' / f'{sequence:05d}.png').exists()
        assert errors == ['RuntimeError'] and native.failed and native.sequence == sequence
        try:
            native.command(kind, startsAt=stamp(start), endsAt=stamp(end))
        except RuntimeError:
            pass
        else:
            raise AssertionError('A rejected read allowed a following action')
        assert not (output / 'commands' / f'{sequence + 1:05d}.request.json').exists()
        code = native.process.wait(timeout=30)
        assert code == 0
        assert (output / 'G2CControl.swift').read_text() == controller.decode().replace(
            '__COMMAND_DIRECTORY__', str(output / 'commands'))
        summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary',
                                           '--path', str(output / 'runner.xcresult')])
        (output / 'summary.json').write_bytes(summary)
        counts = json.loads(summary)
        assert counts['passedTests'] == 1 and counts['failedTests'] == counts['skippedTests'] == 0
        proof = dict(scope='local SDK and separate Debug host only; not App/Hong Kong qualification',
                     kind=kind, controller_sha256=hashlib.sha256(controller).hexdigest(),
                     legacy_snapshot=True, valid_scoped_snapshot=True, queued_expiry_rejected=True,
                     partial_data_exported=False, sticky_barrier=True, native_methods=1)
        (output / 'proof.json').write_text(json.dumps(proof, indent=2))
    finally:
        if paused is not None:
            os.kill(paused, signal.SIGCONT)
        if native is not None:
            native.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--case', choices=('snapshot', 'audit'), action='append')
    args = parser.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT) or output.exists():
        parser.error('Use fresh evidence and build directories outside the repository')
    # The harness must never operate on a logged-in ordinary App installation.
    installed = subprocess.run(['xcrun', 'simctl', 'get_app_container', args.simulator,
                                'space.go2china.app', 'app'], capture_output=True)
    if installed.returncode == 0:
        parser.error('Use a task-owned simulator without an ordinary App installation')
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    if not 8 <= now.hour < 23:
        parser.error('The native action window is outside Beijing 08:00–23:00')
    output.mkdir(parents=True, mode=0o700)
    for case in args.case or ('snapshot', 'audit'):
        exercise(output / case, build, args.simulator, case + ('_all' if case == 'audit' else '') + '_in_window')


if __name__ == '__main__':
    main()
