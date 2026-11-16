"""Assemble observed history rows by the App's accessible position, never a MID."""
import re

from lio_basic_ui_projection import EvidenceUnknown, semantic_nodes

ROW = re.compile(r'lio\.position\.([0-9]+)\.loaded\.([0-9]+)\.earlier\.([012])')
GLOBAL_ERRORS = {'lio.read.failure', 'lio.read.retry', 'lio.chat.recovery', 'lio.position.notice',
                 'lio.session.notice', 'lio.earlier.failure', 'lio.history.failure', 'lio.reply.unavailable'}
COMPLETE = {'Reply complete', '回复已完成'}


class HistoryProjection:
    def __init__(self):
        self.count = None
        self.rows = {}

    def ingest(self, nodes):
        groups = [(index, match) for index, node in enumerate(nodes) if (match := ROW.fullmatch(node['identifier']))]
        counts = {int(match[2]) for _, match in groups}
        more_values = {match[3] for _, match in groups}
        errors = [node['label'] or node['value'] for node in nodes if node['identifier'] in GLOBAL_ERRORS]
        progress = (any(node['progress_indicator'] for node in nodes)
                    or any(node['identifier'] == 'lio.answer' and node['value'] not in COMPLETE
                           for node in semantic_nodes(nodes)))
        if len(counts) > 1 or len(more_values) > 1:
            return self.view(errors, progress=True, earlier=True)
        if not groups:
            has_turn = any(node['identifier'] in {'lio.question', 'lio.answer', 'lio.failure'} for node in nodes)
            empty = (any(node['identifier'].startswith('lio.example.') for node in nodes)
                     and not has_turn and not progress and not errors)
            if empty:
                self.count, self.rows = 0, {}
            return self.view(errors, progress=progress, earlier=not empty)
        count = counts.pop()
        if count != self.count:
            self.count, self.rows = count, {}
        phase = more_values.pop()
        earlier = phase != '0'
        progress = progress or phase == '2'
        # Position belongs to the actual visible Lio byline. Preserve the
        # established question/answer identifiers and collect only a complete
        # question -> one byline -> answer/failure block in this same snapshot.
        semantic = list(semantic_nodes(nodes))
        starts = [i for i, node in enumerate(semantic) if node['identifier'] == 'lio.question']
        for offset, start in enumerate(starts):
            end = starts[offset + 1] if offset + 1 < len(starts) else len(semantic)
            children = semantic[start:end]
            positions = [ROW.fullmatch(node['identifier']) for node in children
                         if ROW.fullmatch(node['identifier'])]
            if len(positions) != 1:
                continue
            match = positions[0]
            ordinal = int(match[1])
            if not 0 <= ordinal < count:
                raise EvidenceUnknown('Actual UI position is outside its loaded range')
            questions = [n for n in children if n['identifier'] == 'lio.question']
            answers = [n for n in children if n['identifier'] == 'lio.answer']
            failures = [n for n in children if n['identifier'] == 'lio.failure']
            if len(questions) != 1:
                continue
            question = questions[0]['value'] or questions[0]['label']
            if not question:
                continue
            if ordinal in self.rows and self.rows[ordinal]['question'] != question:
                raise EvidenceUnknown('An observed UI question changed without a page-generation change')
            if len(failures) == 1 and failures[0]['label'] and not answers:
                row = dict(question=question, answer=None, visible_failure=True, failure_label=failures[0]['label'])
            elif len(answers) == 1 and answers[0]['label'] and answers[0]['value'] in COMPLETE and not failures:
                row = dict(question=question, answer=answers[0]['label'], visible_failure=False)
            else:
                self.rows.pop(ordinal, None)
                continue
            if ordinal in self.rows and self.rows[ordinal] != row:
                raise EvidenceUnknown('An observed UI position changed without a page-generation change')
            self.rows[ordinal] = row
        return self.view(errors, progress=progress, earlier=earlier)

    def view(self, errors, *, progress, earlier):
        complete = (self.count is not None and set(self.rows) == set(range(self.count))
                    and not progress and not earlier and not errors)
        return dict(transcript=[self.rows[index] for index in sorted(self.rows)], errors=errors,
                    body_complete=complete, loaded_count=self.count, earlier_available=earlier,
                    observed_indices=sorted(self.rows))
