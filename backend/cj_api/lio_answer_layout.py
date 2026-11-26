"""One-screen answer layout switch (W2-1, #1727), behind CJ_LIO_ANSWER_LAYOUT.

`flat` (the default) changes nothing: no layout is committed and the answer prompt is the one in
use today. With `one-screen`, an account named in CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON gets the
two-bubble answer (`split`) and every other account a `single` bubble; the layout is committed
before the answer's first text, so every row of one message reads the same value. Whether a timeline
row shows it is the reader's business: only a poll that declared LIO-answer-followups.1 sees it.
"""
import json
import os
import re

LAYOUTS = ('flat', 'one-screen')
# The server's account names for the invite cohort (`G2C@NN` codes map to these); the deploy side
# checks that every name belongs to the 99-account roster before it writes the variable.
_SUBJECT = re.compile(r'm4-synthetic-demo-[a-z0-9]{12}')


def layout_mode():
    """`flat` unless the switch is explicitly `one-screen`; anything else is a configuration error."""
    value = os.environ.get('CJ_LIO_ANSWER_LAYOUT', 'flat')
    if value not in LAYOUTS:
        raise ValueError('explicit answer layout value required')
    return value


def subjects():
    """The accounts the layout is on for: a non-empty list of distinct invite-cohort names, read only
    while the switch is `one-screen` (an unset or invalid list then fails loudly, never silently on)."""
    if layout_mode() != 'one-screen':
        return frozenset()
    try:
        values = json.loads(os.environ.get('CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON', ''))
    except ValueError:
        raise ValueError('answer layout subjects must be a JSON list') from None
    if (type(values) is not list or not values or len(set(values)) != len(values)
            or any(type(value) is not str or _SUBJECT.fullmatch(value) is None for value in values)):
        raise ValueError('answer layout subjects must be distinct invite-cohort account names')
    return frozenset(values)


def answer_layout(subject, question):
    """The layout committed before an answer's first text, or None while the switch is `flat`.

    Decided from the account and the question alone (no request field), so every row of the
    message, from the first `answering` row to `completed`, reads the same value. Code-written
    self-descriptions are one bubble; an emergency is a normal answer and splits.
    """
    if layout_mode() != 'one-screen':
        return None
    from cj_message.lio_context import self_description
    if subject not in subjects() or self_description(question, 'zh') is not None or self_description(question, 'en') is not None:
        return 'single'
    return 'split'


def prompt_layout(layout):
    """The layout argument for `answer_prompt`: one-screen text only for a `split` answer."""
    return 'one-screen' if layout == 'split' else 'flat'
