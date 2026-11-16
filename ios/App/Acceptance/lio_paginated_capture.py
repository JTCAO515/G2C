"""Actual UI pagination and ordinal census. Never reads a journal or substitutes API data."""
import time

from lio_basic_smoke_capture import Capture
from lio_basic_ui_projection import EvidenceUnknown, semantic_nodes
from lio_history_projection import HistoryProjection, ROW


class PagedCapture(Capture):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.projection = HistoryProjection()

    def state(self):
        return self.observe(self.projection)

    def observe(self, projection):
        raw = self.raw()
        view = projection.ingest(raw['nodes'])
        composers = [node for node in raw['nodes'] if node['identifier'] == 'lio.composer']
        shortcuts = [node for node in raw['nodes'] if node['identifier'] == 'lio.chat.newShortcut']
        view['draft'] = composers[0]['value'] if len(composers) == 1 else None
        view['greeting_count'] = sum(node['identifier'] == 'lio.opening' for node in raw['nodes'])
        page_ready = (len(composers) == 1 and bool(shortcuts) and all(node['enabled'] for node in shortcuts)
                      and not any(node['progress_indicator'] for node in raw['nodes']))
        view['page_ready'] = page_ready
        view['body_complete'] = view['body_complete'] and page_ready
        return raw, view

    def immediate(self, *, timeout=90):
        """Observe lifecycle recovery without history navigation or old census."""
        self.projection = HistoryProjection()
        deadline = time.monotonic() + timeout
        while True:
            fresh = HistoryProjection()
            raw, view = self.observe(fresh)
            if view['errors'] or view['body_complete']:
                self.projection = fresh
                return raw, view
            if time.monotonic() >= deadline:
                view['spinner_past_deadline'] = True
                return raw, view
            time.sleep(.2)

    @staticmethod
    def visible(nodes, identifier):
        areas = [node['frame'] for node in nodes if node.get('scroll_container') is True]
        if not areas:
            return False
        for node in nodes:
            if node['identifier'] != identifier:
                continue
            left, top, w, h = node['frame']
            for x, y, width, height in areas:
                if w > 0 and h > 0 and x <= left and y <= top and left + w <= x + width and top + h <= y + height:
                    return True
        return False

    def ready(self, *, timeout=90):
        deadline = time.monotonic() + timeout
        # Reach the beginning before each earlier-page request. The loaded
        # ordinal generation resets whenever prepend changes the actual count.
        while time.monotonic() < deadline:
            raw, view = self.state()
            if view['errors'] or view['body_complete']:
                return raw, view
            if not view['page_ready']:
                time.sleep(.2)
                continue
            if view['loaded_count'] is None:
                raise EvidenceUnknown('This App lacks the qualified accessible history positions')
            if view['earlier_available']:
                if self.visible(raw['nodes'], 'lio.earlier'):
                    self.action('tap', identifier='lio.earlier')
                else:
                    self.action('swipe_down')
                continue
            missing = sorted(set(range(view['loaded_count'])) - set(view['observed_indices']))
            if not missing:
                return raw, view
            current = [int(match[1]) for node in raw['nodes']
                       if (match := ROW.fullmatch(node['identifier']))]
            if not current:
                raise EvidenceUnknown('Current UI position is unavailable; do not guess a scroll direction')
            direction = 'swipe_down' if missing[0] < min(current) else 'swipe_up'
            self.action(direction)
        _, view = self.state()
        view['spinner_past_deadline'] = True
        return raw, view

    def new_chat(self):
        self.projection = HistoryProjection()
        return super().new_chat()

    def history(self, expected_count):
        _, rows = self.history_rows()
        if len(rows) != expected_count:
            raise EvidenceUnknown('The complete local/default history list was not observed')
        opened = []
        for index, row in enumerate(rows):
            if index:
                _, current = self.history_rows()
                if current != rows:
                    raise EvidenceUnknown('Actual history order changed')
            self.projection = HistoryProjection()
            self.action('tap', identifier='lio.chat.history.row', index=index)
            _, view = self.ready()
            opened.append(dict(row_key=row['row_key'], transcript=view['transcript'], errors=view['errors'],
                               body_complete=view['body_complete']))
            if view['errors'] or not view['body_complete']:
                break
        return dict(rows=rows, opened=opened, default_row_key=rows[-1]['row_key'])

    def select_transcript(self, target, expected_count):
        raw, view = self.ready()
        if view['transcript'] == target and view['body_complete']:
            return raw, view
        history = self.history(expected_count)
        if (len(history['opened']) != len(history['rows'])
                or any(not entry['body_complete'] or entry['errors'] for entry in history['opened'])):
            raise EvidenceUnknown('History candidates are incomplete; uniqueness is unknown')
        matches = [index for index, entry in enumerate(history['opened'])
                   if entry['body_complete'] and not entry['errors'] and entry['transcript'] == target]
        if len(matches) != 1:
            raise EvidenceUnknown('No unique actual complete history matches the target')
        _, rows = self.history_rows()
        if rows != history['rows']:
            raise EvidenceUnknown('History changed before target selection')
        self.projection = HistoryProjection()
        self.action('tap', identifier='lio.chat.history.row', index=matches[0])
        return self.ready()

    def send_once(self, expected, *, timeout=90):
        _, before = self.ready()
        if before['draft'] != expected or before['errors'] or not before['body_complete']:
            raise EvidenceUnknown('Exact prepared input changed before the admitted single send')
        tap = self.action('tap', identifier='lio.send')
        first_body = None
        deadline = time.monotonic() + timeout
        expected_count = before['loaded_count'] + 1
        while time.monotonic() < deadline:
            raw, view = self.state()
            # The first visible body can precede completion. Look only at the
            # actual last question/byline/body block from this native snapshot.
            semantic = list(semantic_nodes(raw['nodes']))
            starts = [index for index, node in enumerate(semantic) if node['identifier'] == 'lio.question']
            if starts:
                block = semantic[starts[-1]:]
                question = block[0]['value'] or block[0]['label']
                positions = [ROW.fullmatch(node['identifier']) for node in block if ROW.fullmatch(node['identifier'])]
                body = [node for node in block if node['identifier'] == 'lio.answer' and node['label']]
                if (question == expected and len(positions) == 1 and int(positions[0][1]) == expected_count - 1
                        and int(positions[0][2]) == expected_count and len(body) == 1 and first_body is None):
                    first_body = (raw['finished_uptime'] - tap['started_uptime']) * 1000
            last = self.projection.rows.get(expected_count - 1) if self.projection.count == expected_count else None
            new_turn = last is not None and last['question'] == expected
            timing = dict(clock='actual_App_monotonic', first_progress_ms=None,
                progress_status='NOT_OBSERVED', native_progress_ref=None, first_body_ms=first_body,
                complete_ms=(raw['finished_uptime'] - tap['started_uptime']) * 1000)
            if new_turn and last['visible_failure']:
                view['errors'].append(last['failure_label'])
                view['body_complete'] = False
            if view['errors']:
                return raw, view, timing
            if new_turn:
                # Record completion when the last body was actually complete;
                # collecting offscreen history afterwards is a separate read.
                final_raw, final = self.ready(timeout=timeout)
                if (not final['body_complete'] or len(final['transcript']) != expected_count
                        or final['transcript'][-1] != last):
                    final['body_complete'] = False
                return final_raw, final, timing
            time.sleep(.2)
        view['spinner_past_deadline'] = True
        return raw, view, None
