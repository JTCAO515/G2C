"""Which remembered items an answer used, and what to call them now (#2001, M-3; LIO-answer-rich.1 `rich.memory.used`).

Two halves, both read-only:

* `used_effect(run)` (write side, in the worker): the ids of the memory items the server itself handed the model
  in this turn (`MemoryRun.payload`), at most three, as the effect `lio_memory_used:{"item_ids":[...],"total":n}`.
  Ids and a count only: no title, no text. The model's claim to have used something is never read.
* `memory_titles(repository, item_ids)` (read side, at every timeline read): for each id, the title derived from the
  item as it is **now**, and only when the item is still `active` and its approved source is still valid. An item
  that was stopped, withdrawn or deleted, or whose source expired, gets no entry, so a title of something the
  traveler took back never reaches a row (contract R-8). It takes no row lock: it is a plain read in the
  account's own scope, outside the memory write path.

Off by default: `CJ_LIO_MEMORY_USED=on` writes the effect.
"""
import json
import os
import re

from .domain import Unavailable
from .title_projection import derive_title, valid_title

USED_EFFECT = 'lio_memory_used:'
MAX_USED = 3
MAX_TOTAL = 99
_ITEM_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}')


def used_enabled():
    value = os.environ.get('CJ_LIO_MEMORY_USED', 'off')
    if value not in ('off', 'on'):
        raise ValueError('explicit CJ_LIO_MEMORY_USED value required')
    return value == 'on'


def used_item_ids(run, keep=None):
    """`(item_ids, total)` of the items this run's payload carried, in the payload's order; ids are those of the run's
    own snapshot, so a source id the snapshot does not know is skipped. `([], 0)` when there is nothing."""
    try:
        payload = json.loads(bytes(run.payload).decode('utf-8'))
        sources = [item['source_id'] for item in payload['items']]
        by_source = {item.command.source_id: item.command.item_id for item in run.snapshot.items
                     if keep is None or keep(item.command)}
    except Exception:
        return [], 0
    ids = []
    for source in sources:
        item_id = by_source.get(source)
        if type(item_id) is str and _ITEM_ID.fullmatch(item_id) and item_id not in ids:
            ids.append(item_id)
    return ids[:MAX_USED], min(len(ids), MAX_TOTAL)


def used_effect(run, keep=None):
    """The effect string for a finished answer, or None (switch off, no run, nothing used)."""
    if not used_enabled() or run is None:
        return None
    ids, total = used_item_ids(run, keep)
    if not ids:
        return None
    return USED_EFFECT + json.dumps(dict(item_ids=ids, total=total), separators=(',', ':'), sort_keys=True)


def parse_used(effect_value):
    """`(item_ids, total)` from a stored effect, or None for anything that is not exactly the stored shape."""
    try:
        payload = json.loads(effect_value.removeprefix(USED_EFFECT))
        ids, total = payload['item_ids'], payload['total']
        if (set(payload) != {'item_ids', 'total'} or type(ids) is not list or not 1 <= len(ids) <= MAX_USED
                or len(set(ids)) != len(ids) or any(type(i) is not str or _ITEM_ID.fullmatch(i) is None for i in ids)
                or type(total) is not int or not len(ids) <= total <= MAX_TOTAL):
            return None
        return ids, total
    except Exception:
        return None


def memory_titles(repository, item_ids):
    """`{item_id: title}` for the ids that are active and whose source is valid now; at most MAX_USED ids are read.

    `repository` is the account's own memory repository (its scope and role); nothing here crosses accounts. Any
    failure of one item leaves that item out; a failure to open the read raises, and the caller leaves `used` out.

    It does not check `cj_memory_scope.active` (as `effective()` does): a deactivated account is stopped by the account
    fence before any answer is produced, so an inactive scope never reaches this read.
    """
    ids = list(dict.fromkeys(i for i in item_ids if type(i) is str))[:MAX_USED]
    titles = {}
    if not ids:
        return titles
    with repository.transaction() as tx:
        for item_id in ids:
            try:
                item = tx.detail(item_id)
                if item is None or item.status != 'active':
                    continue
                command = item.command
                tx.cur.execute('SELECT approved_input,confirmed,semantic_resolved FROM cj_memory_source WHERE scope=%s AND '
                               'source_id=%s AND version=%s AND authorized AND active AND expires_at>clock_timestamp()',
                               (tx.scope, command.source_id, command.source_version))
                row = tx.cur.fetchone()
                if row is None or bytes(row[0]) != command.raw or not (row[1] and row[2]):
                    continue
                title = derive_title(command)
                if title and valid_title(command.text, title) and len(title) <= 40:
                    titles[item_id] = title
            except (Unavailable, ValueError, TypeError, KeyError):
                continue
    return titles
