"""One-screen answer layout switch and per-answer layout (W2-1, #1727), behind CJ_LIO_ANSWER_LAYOUT.

Three conditions must all hold for the two-bubble answer (`split`): the server switch is
`one-screen`, the account is in CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON, and the request declared
`accepts: ["LIO-answer-followups.1"]`. A request that did not declare it gets no layout at all
(`None`: the response stays byte-identical to today's). A request that declared it always gets
`split` or `single`, decided before the answer starts and fixed for the whole message.

Nothing here reads a request or a response; the wire parts come with the contract change. The
switch defaults to `flat`: nothing changes until it is set to `one-screen` with a subject list.
"""
import json
import os
import re

from cj_message.lio_followups import VERSION

LAYOUTS = ('flat', 'one-screen')
_SUBJECT = re.compile(r'G2C@(?:0[1-9]|[1-9][0-9])')
# Replies the code writes itself, edits and confirmations, a plan body (one sentence, the cards carry
# the rest), failures and limits are one bubble. An emergency takes the normal answer path (split).
SINGLE_ROUTES = frozenset({'greeting', 'self_description', 'change', 'confirm', 'plan', 'failure', 'limit'})


def layout_mode():
    """`flat` unless the switch is explicitly `one-screen`; anything else is a configuration error."""
    value = os.environ.get('CJ_LIO_ANSWER_LAYOUT', 'flat')
    if value not in LAYOUTS:
        raise ValueError('explicit answer layout value required')
    return value


def subjects():
    """The accounts the layout is on for: a non-empty list of distinct G2C@01–99 names, read only
    while the switch is `one-screen` (an unset or invalid list then fails loudly, never silently on)."""
    if layout_mode() != 'one-screen':
        return frozenset()
    try:
        values = json.loads(os.environ.get('CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON', ''))
    except ValueError:
        raise ValueError('answer layout subjects must be a JSON list') from None
    if (type(values) is not list or not values or len(set(values)) != len(values)
            or any(type(value) is not str or _SUBJECT.fullmatch(value) is None for value in values)):
        raise ValueError('answer layout subjects must be distinct G2C@01 to G2C@99 names')
    return frozenset(values)


def accepted(accepts):
    """True when the request declared this follow-ups version; other values are ignored."""
    return type(accepts) is list and VERSION in accepts


def layout_for(subject, *, accepts, route='answer'):
    """`'split'`, `'single'` or `None` (no field) for one answer.

    `subject` is the account's name (G2C@NN). `accepts` is the request's declared list or None.
    """
    if not accepted(accepts):
        return None
    if route in SINGLE_ROUTES:
        return 'single'
    if route != 'answer':
        raise ValueError('unknown answer route')
    return 'split' if layout_mode() == 'one-screen' and subject in subjects() else 'single'


def prompt_layout(layout):
    """The layout argument for `answer_prompt`: one-screen text only for a `split` answer."""
    return 'one-screen' if layout == 'split' else 'flat'
