"""Normalize the frozen native4 presentation, not AUTH or accepted profile truth.

The qualified host still supplies the actual RUN outcome, exploration boundary,
accepted-context observation, injected Memory observation and original fees.
Neither a valid wire object nor its public labels proves those observations.
"""
import json

from jsonschema import ValidationError

from cj_strict_json import reject_duplicates
from contracts.message.check_lio_v4 import validate
from .core import InputError


def _non_json_constant(_):
    raise InputError('strict native4 JSON required')


def presentation_fields(raw, *, conversation_id, message_id, user_text,
                        observation_ref, independent_question_census_complete=False):
    """Return presentation fields for the unchanged DialogueHost interface.

    Inputs are an actual host-captured timeline and its expected original
    selectors. Importing bytes does not authenticate them. Completeness defaults
    to false: the native observer must independently account for factor questions
    outside question_groups too. No terminal/exploration status is inferred.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
        raise InputError('bounded native4 timeline bytes required')
    if type(independent_question_census_complete) is not bool:
        raise InputError('explicit independent question census required')
    if type(observation_ref) is not str or not 0 < len(observation_ref) <= 4096:
        raise InputError('original native observation reference required')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates(InputError, 'duplicate native4 field'),
                           parse_constant=_non_json_constant)
        validate(value)
    except (ValueError, UnicodeError, RecursionError, ValidationError) as error:
        raise InputError('complete frozen native4 timeline required') from error
    if (value['version'] != 'LIO-timeline.4' or value['conversation_id'] is None
            or value['conversation_id'] != conversation_id):
        raise InputError('actual native4 conversation differs')
    selected = [row for row in value['messages'] if row['message_id'] == message_id]
    if len(selected) != 1 or selected[0]['text'] != user_text:
        raise InputError('actual original native4 message/text differs')
    message = selected[0]
    answer = message['answer']
    if not answer.strip():
        raise InputError('actual nonempty presentation required')

    # The frozen plain projection puts segments before groups. Count Unicode
    # characters in their original order, not bytes/UTF-16 or first text matches.
    cursor = sum(len(segment['text']) + 2 for segment in message['segments'])
    questions = []
    for group in message['question_groups']:
        question = group['question']
        questions.append(dict(factor=group['factor_key'], start=cursor, end=cursor+len(question)))
        cursor += len(question) + 1 + len(' / '.join(option['display_text'] for option in group['options'])) + 2

    unannotated = any('?' in part['text'] or '？' in part['text']
                      for part in [*message['segments'], *message['notices']])
    complete = (independent_question_census_complete and not unannotated
                and message['status'] == 'completed' and message['failure'] is None)
    return dict(wire_status=message['status'], turn_fields=dict(
        text=answer, questions=questions, questions_complete=complete,
        question_evidence='native_structured', profile=None, profile_complete=False,
        profile_evidence='unavailable', observation_ref=observation_ref))
