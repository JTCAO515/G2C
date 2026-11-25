"""Ordinary Home capture primitives for C's two-phase basic smoke handoff.

No provider/SDK calls, native IDs or permissions are manufactured here. Every
action uses the separately installed App's native UI. A missing ACK is UNKNOWN.
"""
import hashlib
from pathlib import Path
import plistlib
import subprocess
import time

from lio_basic_ui_projection import EvidenceUnknown, project, semantic_nodes


def artifact(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def verify_installation(simulator, manifest):
    """Compare the installed binary and Info values with the actual build record."""
    bundle = manifest['bundle_identifier']
    if bundle != 'space.go2china.app' or manifest['app']['protocol'] != 'LIO-message.2':
        raise EvidenceUnknown('This cohort requires the ordinary Beta v2 App')
    path = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', simulator, bundle, 'app'],
                                        text=True, stderr=subprocess.DEVNULL).strip())
    info = plistlib.loads((path / 'Info.plist').read_bytes())
    if (info['CFBundleIdentifier'] != bundle or str(info['CFBundleVersion']) != manifest['bundle_version']
            or info['CFBundleExecutable'] != manifest['executable_name']
            or hashlib.sha256((path / info['CFBundleExecutable']).read_bytes()).hexdigest()
                != manifest['executable_sha256']):
        raise EvidenceUnknown('Installed App differs from the qualified artifact')
    return artifact(path / info['CFBundleExecutable'])


class Capture:
    def __init__(self, native, *, run_id, locale):
        self.native, self.run_id, self.locale = native, run_id, locale
        self.originals = []
        self.owned_drafts = {''}

    def action(self, kind, **fields):
        return self.native.command(kind, **fields)

    def raw(self):
        stem = f'{self.native.sequence:05d}'
        result = self.native.command('snapshot')
        self.originals += [artifact(self.native.commands / (stem + '.response.json')),
                           artifact(self.native.commands / result['screenshot'])]
        return result

    def ready(self, *, timeout=90):
        deadline = time.monotonic() + timeout
        while True:
            raw = self.raw()
            view = project(raw['nodes'])
            if view['errors'] or view['body_complete']:
                return raw, view
            if time.monotonic() >= deadline:
                view['spinner_past_deadline'] = True
                return raw, view
            time.sleep(.2)

    def draft(self, expected):
        raw, view = self.ready()
        if view['errors'] or not view['body_complete']:
            raise EvidenceUnknown('The actual conversation is not ready for preparation')
        if view['draft'] == expected:
            return raw, view
        if view['draft'] not in self.owned_drafts:
            raise EvidenceUnknown('Preserve the unrelated existing draft; do not replace it')
        if view['draft']:
            self.action('select_all')
        self.action('type', identifier='lio.composer', text=expected)
        self.owned_drafts.add(expected)
        raw, view = self.ready()
        if view['draft'] != expected:
            raise EvidenceUnknown('The exact prepared draft was not observed')
        return raw, view

    def new_chat(self):
        self.action('tap', identifier='lio.chat.newShortcut')
        raw, view = self.ready()
        if view['transcript'] or view['errors'] or not view['body_complete']:
            raise EvidenceUnknown('The actual new-chat transition did not produce an empty conversation')
        return raw, view

    def history_rows(self):
        self.action('tap', identifier='lio.menu')
        self.action('tap', identifier='lio.chat.history')
        deadline = time.monotonic() + 20
        while True:
            raw = self.raw()
            rows = [dict(row_key=f'row-{i}', label=n['label']) for i, n in enumerate(
                n for n in semantic_nodes(raw['nodes']) if n['identifier'] == 'lio.chat.history.row')]
            if rows:
                return raw, rows
            if project(raw['nodes'])['errors'] or time.monotonic() >= deadline:
                raise EvidenceUnknown('The complete actual history list is unavailable')
            time.sleep(.2)

    def history(self, expected_count):
        _, rows = self.history_rows()
        if len(rows) != expected_count:
            raise EvidenceUnknown('The complete local/default history census was not observed')
        opened = []
        for index, row in enumerate(rows):
            if index:
                _, current = self.history_rows()
                if current != rows:
                    raise EvidenceUnknown('Actual history order changed between selections')
            self.action('tap', identifier='lio.chat.history.row', index=index)
            _, view = self.ready()
            opened.append(dict(row_key=row['row_key'], transcript=view['transcript'],
                               errors=view['errors'], body_complete=view['body_complete']))
            if view['errors'] or not view['body_complete']:
                break
        return dict(rows=rows, opened=opened, default_row_key=rows[-1]['row_key'])

    def select_transcript(self, target, expected_count):
        raw, view = self.ready()
        if view['transcript'] == target and view['body_complete']:
            return raw, view
        history = self.history(expected_count)
        matches = [i for i, row in enumerate(history['opened'])
                   if row['body_complete'] and not row['errors'] and row['transcript'] == target]
        if len(matches) != 1:
            raise EvidenceUnknown('Target conversation has no unique actual AX match')
        _, rows = self.history_rows()
        if rows != history['rows']:
            raise EvidenceUnknown('Actual history order changed before selection')
        self.action('tap', identifier='lio.chat.history.row', index=matches[0])
        return self.ready()

    def send_once(self, expected, *, timeout=90):
        _, before = self.ready()
        if before['draft'] != expected or before['errors'] or not before['body_complete']:
            raise EvidenceUnknown('Prepared input changed before its single send')
        tap = self.action('tap', identifier='lio.send')
        start = tap['started_uptime']
        first_body = None
        deadline = time.monotonic() + timeout
        while True:
            raw = self.raw()
            try:
                view = project(raw['nodes'])
            except EvidenceUnknown:
                # A transient/virtualized partial snapshot is not a completed reply.
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.2)
                continue
            new_turn = (len(view['transcript']) == len(before['transcript']) + 1
                        and view['transcript'][-1]['question'] == expected)
            if new_turn and view['transcript'][-1]['answer']:
                if first_body is None:
                    first_body = (raw['finished_uptime'] - start) * 1000
            if view['errors'] or (new_turn and view['body_complete']):
                timing = dict(clock='actual_App_monotonic', first_progress_ms=None,
                              progress_status='NOT_OBSERVED', native_progress_ref=None,
                              first_body_ms=first_body, complete_ms=(raw['finished_uptime'] - start) * 1000)
                return raw, view, timing
            if time.monotonic() >= deadline:
                view['spinner_past_deadline'] = True
                return raw, view, None
            time.sleep(.2)
