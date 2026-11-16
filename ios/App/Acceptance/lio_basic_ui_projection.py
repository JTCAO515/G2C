"""Project one immutable ordinary Home AX snapshot, without rewriting text.

This is not a conversation-ID observer. Native originals must independently
match the complete ordered text before the C joint gate can accept it.
"""


class EvidenceUnknown(ValueError):
    pass


ERROR_IDENTIFIERS = frozenset({
    'lio.failure', 'lio.read.failure', 'lio.chat.recovery', 'lio.reply.unavailable',
    'lio.position.notice', 'lio.session.notice',
})
HISTORY_ERRORS = frozenset({'Couldn’t show your conversations.', '暂时看不到对话。'})


def semantic_nodes(nodes):
    """A parent carrying an identifier and its children describe one element."""
    end_depth = None
    for node in nodes:
        if end_depth is not None and node['depth'] > end_depth:
            continue
        end_depth = None
        if node['identifier'].startswith('lio.'):
            yield node
            if node['identifier'] in {'lio.question', 'lio.answer', 'lio.opening', 'lio.composer'}:
                end_depth = node['depth']
        elif node['label'] in HISTORY_ERRORS:
            yield node


def project(nodes):
    transcript, errors = [], []
    draft, composer_seen, ready, progress, greetings = '', False, False, False, 0
    progress = any(node['progress_indicator'] for node in nodes)
    answers_complete = True
    for node in semantic_nodes(nodes):
        identifier = node['identifier']
        text = node['value'] if node['value'] else node['label']
        if identifier == 'lio.question':
            if not text:
                raise EvidenceUnknown('Actual question text is unavailable')
            transcript.append(dict(question=text, answer=''))
        elif identifier == 'lio.answer':
            if not transcript or transcript[-1]['answer']:
                raise EvidenceUnknown('The complete ordered question/answer hierarchy is unavailable')
            transcript[-1]['answer'] = node['label']
            answers_complete = answers_complete and node['value'] in {'Reply complete', '回复已完成'}
        elif identifier == 'lio.composer':
            if composer_seen:
                raise EvidenceUnknown('Actual composer is ambiguous')
            composer_seen, draft = True, node['value']
        elif identifier == 'lio.chat.newShortcut':
            ready = node['enabled']
        elif identifier == 'lio.progress':
            progress = True
        elif identifier == 'lio.opening':
            greetings += 1
        if identifier in ERROR_IDENTIFIERS or node['label'] in HISTORY_ERRORS:
            errors.append(text)
    return dict(transcript=transcript, draft=draft, errors=errors, greeting_count=greetings,
                body_complete=composer_seen and ready and not progress and not errors
                    and answers_complete and all(turn['answer'] for turn in transcript))
