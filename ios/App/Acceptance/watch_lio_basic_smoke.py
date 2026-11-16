"""A-side first-setup coordinator for C's checkpoint-fenced ordinary Home smoke.

Run only with an independently qualified installed Beta and B's issued purpose.
This emits observed UI facts, never a release certificate or native identity.
"""
import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import subprocess
import time
from zoneinfo import ZoneInfo

from lio_basic_smoke_capture import artifact, day_guard, verify_installation
from lio_paginated_capture import PagedCapture
from lio_basic_ui_driver import NativeUI, decode, write
from lio_basic_ui_projection import EvidenceUnknown, semantic_nodes


def read_private_bytes(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        import stat
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 5_000_000):
            raise EvidenceUnknown('Private handoff is not an owner-bound regular0600 file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(5_000_001)
        if len(data) > 5_000_000:
            raise EvidenceUnknown('Private handoff exceeds its limit')
        return data
    finally:
        os.close(fd)


def read_private(path):
    return decode(read_private_bytes(path))


def wait(path, deadline):
    while not path.exists():
        if time.monotonic() >= deadline:
            raise EvidenceUnknown('Checkpoint handoff did not arrive; do not replay an action')
        time.sleep(.2)
    return read_private(path)


def current_window(config):
    day_guard()
    now = datetime.now(ZoneInfo('UTC'))
    start, end = (datetime.fromisoformat(config[key]) for key in ('starts_at', 'ends_at'))
    if start.tzinfo is None or end.tzinfo is None or not start <= now < end:
        raise EvidenceUnknown('Outside the issued purpose interval')


def read_full_reply(capture, answer):
    """Observe contiguous visible slices of the actual complete reply, not a cache."""
    covered = 0.0
    height = None
    for _ in range(50):
        raw = capture.raw()
        nodes = list(semantic_nodes(raw['nodes']))
        body = [n for n in nodes if n['identifier'] == 'lio.answer' and n['label'] == answer
                and n['value'] in {'Reply complete', '回复已完成'}]
        composer = [n for n in nodes if n['identifier'] == 'lio.composer']
        names = [n for n in nodes if n['identifier'] == 'lio.name']
        if len(body) != 1 or len(composer) != 1 or not names:
            raise EvidenceUnknown('Actual reply/viewport is ambiguous')
        y, h = body[0]['frame'][1], body[0]['frame'][3]
        top = max(n['frame'][1] + n['frame'][3] for n in names)
        bottom = composer[0]['frame'][1]
        if height is None:
            height = h
        if h <= 0 or h != height or bottom <= top:
            raise EvidenceUnknown('Actual completed reply geometry changed')
        first, last = max(0, top - y), min(h, bottom - y)
        if last > first and first <= covered + 2:
            covered = max(covered, last)
        if covered >= height - 1:
            return
        capture.action('swipe_down' if first > covered + 2 else 'swipe_up')
    raise EvidenceUnknown('The entire reply was not actually reached contiguously')


def three_days(answer, locale):
    words = [('1', '一'), ('2', '二'), ('3', '三')]
    return all(re.search(r'第\s*(?:' + number + '|' + han + r')\s*天', answer) for number, han in words) if locale == 'zh' else all(
        re.search(r'\bday\s*' + number + r'\b', answer, flags=re.IGNORECASE) for number, _ in words)


def lifecycle_snapshot(action, view):
    # Later history errors/selection must not rewrite the immediate UI record.
    return dict(action=action, transcript=[dict(row) for row in view['transcript']],
                draft=view['draft'], errors=list(view['errors']), body_complete=view['body_complete'])


class Coordinator:
    def __init__(self, config, plan_directory, output):
        self.config, self.root, self.output = config, Path(plan_directory), Path(output)
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.native, self.capture, self.targets = {}, {}, {}
        raw = read_private_bytes(config['plan']['path'])
        if hashlib.sha256(raw).hexdigest() != config['plan']['sha256']:
            raise EvidenceUnknown('Approved plan bytes changed')
        plan = decode(raw)
        if (plan['version'] != 'LIO-basic-chain-plan.2' or plan['app'] != config['app']
                or plan['first_setup'] is not True):
            raise EvidenceUnknown('Only the approved first-setup plan may execute')
        self.run_id = plan['run_id']
        self.steps = {}
        for index, parent in enumerate(plan['steps']):
            if parent['gate_id'] == 'SM04':
                for number, action in enumerate(parent['read_actions'], 1):
                    self.steps[f'{index:02d}-{number}'] = dict(parent, **action, parent_nonce=parent['nonce'])
            else:
                self.steps[f'{index:02d}'] = parent
        self.next_index = 0

    def guard(self):
        current_window(self.config)
        return dict(startsAt=self.config['starts_at'], endsAt=self.config['ends_at'])

    def client(self, locale):
        self.guard()
        if locale not in self.native:
            simulator = self.config['simulators'][locale]
            native = AdmittedNativeUI(self.guard, self.output / locale, simulator, 'space.go2china.app',
                                      build_directory=self.config['build_directories'][locale])
            self.native[locale] = native
            verify_installation(simulator, self.config)
            # No launch/login occurs here. Official sign-in preparation is a
            # separately admitted operation; a missing signed-in App stays UNKNOWN.
            self.capture[locale] = PagedCapture(native, run_id=self.run_id, locale=locale)
        return self.capture[locale]

    def phase(self, instruction_path):
        instruction = read_private(instruction_path)
        step, app = instruction['step'], instruction['app']
        if (instruction['version'] != 'LIO-basic-ui-instruction.2' or app != self.config['app']
                or step['locale'] not in ('zh', 'en') or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', instruction['run_id'])):
            raise EvidenceUnknown('Instruction differs from the qualified first-setup App/run')
        if self.run_id != instruction['run_id']:
            raise EvidenceUnknown('A coordinator cannot switch to a different run')
        stem = instruction_path.name.removesuffix('-prepare.json')
        if not re.fullmatch(r'[0-9]{2}(?:-[12])?', stem):
            raise EvidenceUnknown('Unknown phase filename')
        if (self.next_index >= len(self.steps) or stem != list(self.steps)[self.next_index]
                or step != self.steps[stem]):
            raise EvidenceUnknown('UI instruction is not the next exact step of the approved plan')
        prepared_path = self.root / (stem + '-A-prepared.json')
        complete_path = self.root / (stem + '-A-completed.json')
        if prepared_path.exists() or complete_path.exists():
            raise EvidenceUnknown('A phase already has records; never replay its UI action')
        self.guard()
        capture = self.client(step['locale'])
        verify_installation(capture.native.simulator, self.config)
        capture.originals = []
        actions = []
        targets = self.targets.setdefault(step['locale'], {})
        # In C's approved first-setup order, SM01 has not yet added the
        # default to accepted views. After that gate C includes it (even when
        # empty); SM03/SM04 must not count it again or guess its CID from a title.
        history_count = len(instruction['accepted_conversations']) + int(step['gate_id'] == 'SM01')
        if step['new_conversation']:
            capture.new_chat(); actions.append('new_chat')
        elif step['gate_id'] in ('SM01', 'SM04'):
            role = 'old' if step['gate_id'] == 'SM01' else 'qa'
            if role not in targets:
                raise EvidenceUnknown('No previously observed target; standard-run selection is not implemented')
            capture.select_transcript(targets[role], history_count)
        expected = step['text'] if step['text'] is not None else instruction['expected_draft']
        if expected is not None:
            _, before = capture.draft(expected)
        else:
            _, before = capture.ready()
        if before['errors'] or not before['body_complete']:
            raise EvidenceUnknown('Actual preparation is unavailable')
        write(prepared_path, dict(version='LIO-basic-app-prepared.2', run_id=self.run_id,
                                 nonce=step['nonce'], app=app, send_taps=0, ui_before=before,
                                 artifacts=list(capture.originals)))
        admitted = wait(self.root / (stem + '-admission.json'), time.monotonic() + self.config['admission_wait_seconds'])
        if (admitted['version'] != 'LIO-basic-ui-admission.2'
                or admitted['run_id'] != self.run_id or admitted['nonce'] != step['nonce']
                or admitted['qualification_sha256'] != self.config['qualification_sha256']
                or not admitted['checkpoint_ref']):
            raise EvidenceUnknown('Admission does not belong to this original phase')
        self.guard()
        _, unchanged = capture.ready()
        if unchanged != before:
            raise EvidenceUnknown('Actual prepared state changed after the server checkpoint')
        lifecycle, history, timing = [], None, None
        if step['text'] is not None:
            _, after, timing = capture.send_once(step['text'])
            actions.append('send')
            if step['gate_id'] == 'SM07' and after['body_complete'] and not after['errors']:
                read_full_reply(capture, after['transcript'][-1]['answer'])
                _, after = capture.ready()
                after['three_day_readback'] = three_days(after['transcript'][-1]['answer'], step['locale'])
            if after['body_complete'] and not after['errors']:
                if step['gate_id'] == 'SEED2': targets['old'] = after['transcript']
                if step['gate_id'] == 'SM02': targets['qa'] = after['transcript']
        elif step['gate_id'] == 'SM03':
            history = capture.history(history_count)
            actions = ['history']
            _, after = capture.ready()
        elif step['gate_id'] == 'SM01':
            capture.action('terminate'); self.guard(); capture.action('launch', language=step['locale'])
            _, after = capture.immediate()
            actions = ['cold_launch']
            lifecycle = [lifecycle_snapshot('cold_launch', after)]
            # Keep the immediate cold result immutable. Only then collect the
            # complete default/local candidate bodies needed for C's unique join.
            if after['body_complete'] and not after['errors']:
                history = capture.history(history_count)
                history_errors = [error for entry in history['opened'] for error in entry['errors']]
                if (history_errors or len(history['opened']) != len(history['rows'])
                        or any(not entry['body_complete'] for entry in history['opened'])):
                    after['errors'].extend(history_errors)
                    after['body_complete'] = False
                else:
                    _, after = capture.select_transcript(targets['old'], history_count)
        elif step['gate_id'] == 'SM04':
            action = step['action']
            if action == 'background_return':
                capture.action('background')
            elif action == 'lock_return':
                self.lock(capture)
            else:
                raise EvidenceUnknown('Unknown lifecycle action')
            self.guard(); capture.action('activate')
            _, after = capture.immediate()
            actions = [action]
            lifecycle = [lifecycle_snapshot(action, after)]
        else:
            raise EvidenceUnknown('Unknown read-only gate')
        after['new_greeting_count'] = max(0, after['greeting_count'] - before['greeting_count'])
        write(complete_path, dict(version='LIO-basic-app-witness.2', source='actual_ordinary_Home_AX',
              run_id=self.run_id, gate_id=step['gate_id'], locale=step['locale'], nonce=step['nonce'], app=app,
              message_id_observed=None, conversation_id_observed=None,
              send_taps=1 if step['text'] is not None else 0, submitted_text=step['text'],
              before=before, after=after, actions=actions, history=history, lifecycle=lifecycle,
              timing=timing, artifacts=list(capture.originals)))
        self.next_index += 1

    def lock(self, capture):
        axe = Path(self.config['axe']['path'])
        if hashlib.sha256(axe.read_bytes()).hexdigest() != self.config['axe']['sha256']:
            raise EvidenceUnknown('Qualified simulator button executable changed')
        env = dict(os.environ, DYLD_FRAMEWORK_PATH=str(axe.parent / 'Frameworks'))
        for button in ('lock', 'home'):
            self.guard()
            result = subprocess.run([str(axe), 'button', button, '--udid', capture.native.simulator],
                                    env=env, capture_output=True, timeout=20)
            # The controller records the actual button invocation/result, not a
            # prefilled lifecycle PASS. No credential is passed to this program.
            path = self.output / ('button-' + str(time.monotonic_ns()) + '.json')
            write(path, dict(button=button, returncode=result.returncode,
                             stdout=result.stdout.decode(errors='replace'), stderr=result.stderr.decode(errors='replace')))
            capture.originals.append(artifact(path))
            if result.returncode:
                raise EvidenceUnknown('Native lock/home transition failed; do not repeat it')
            time.sleep(1)

    def close(self):
        for native in self.native.values():
            native.close()


class AdmittedNativeUI(NativeUI):
    def __init__(self, guard, *args, **kwargs):
        self.guard = guard
        super().__init__(*args, **kwargs)

    def command(self, kind, **fields):
        if kind not in ('snapshot', 'stop'):
            fields.update(self.guard())
        return super().command(kind, **fields)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--plan-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = read_private_bytes(args.config)
    if hashlib.sha256(raw).hexdigest() != args.config_sha256:
        parser.error('Configuration differs from the independently approved packet')
    config = decode(raw)
    if config['version'] != 'LIO-A-ui-coordinator.1' or config['first_setup'] is not True:
        parser.error('Only the explicit first-setup cohort is implemented')
    runner = Coordinator(config, args.plan_directory, args.output)
    handled = set()
    try:
        while True:
            runner.guard()
            for instruction in sorted(args.plan_directory.glob('*-prepare.json')):
                if instruction.name not in handled:
                    runner.phase(instruction)
                    handled.add(instruction.name)
            if (args.plan_directory / 'result.json').exists():
                return
            time.sleep(.2)
    except Exception:
        write(args.output / 'coordinator-UNKNOWN.json', dict(status='UNKNOWN', handled=sorted(handled),
              reason='Original UI/admission/artifact evidence unavailable; no action replay'))
        raise
    finally:
        runner.close()


if __name__ == '__main__':
    main()
