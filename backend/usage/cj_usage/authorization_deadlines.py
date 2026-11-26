"""JT-approved authorization deadlines, kept in one reviewed config file (#1716).

``authorization_deadlines.json`` is the only place these instants are written.
Changing one still needs JT approval and an independently reviewed PR; the file
only removes scattered copies so docs, tests and runtime read one source.

- ``deadlines``: exclusive end of each approval, Asia/Shanghai time.
- ``previous``: earlier approved ends of the same allowance. A renewal that only
  moves the end keeps counting against the original allowance (OSS lineage).
- ``boundaries``: fixed historical instants that are not expiries. The M4
  original period end splits the HK run Meter into the original period and the
  Demo period (``hk_demo``); the HK run context persists it, so it never moves.
"""
from datetime import datetime,timezone
import json
from pathlib import Path

from cj_strict_json import reject_duplicates

PATH=Path(__file__).with_name('authorization_deadlines.json')
NAMES=frozenset({'oss_backup','supabase_test','mac_provider_acceptance','hk_demo'})
BOUNDARIES=frozenset({'m4_original_period_end'})


def _instant(text):
    value=datetime.fromisoformat(text) if type(text) is str else None
    if value is None or value.tzinfo is None or value.utcoffset().total_seconds()!=8*3600 or value.isoformat()!=text:
        raise ValueError('explicit_Asia_Shanghai_deadline_required')
    return value


def _load():
    data=json.loads(PATH.read_bytes(),object_pairs_hook=reject_duplicates(ValueError,'duplicate_authorization_deadline'))
    if (type(data) is not dict or set(data)!={'version','approval','deadlines','previous','boundaries'}
            or data['version']!='g2c-authorization-deadlines.2' or type(data['approval']) is not str or not data['approval']
            or type(data['deadlines']) is not dict or set(data['deadlines'])!=NAMES
            or type(data['previous']) is not dict or not set(data['previous'])<=NAMES
            or type(data['boundaries']) is not dict or set(data['boundaries'])!=BOUNDARIES):
        raise ValueError('authorization_deadline_config_invalid')
    current={name:_instant(text) for name,text in data['deadlines'].items()}
    previous={}
    for name,items in data['previous'].items():
        if type(items) is not list or not items:raise ValueError('authorization_deadline_config_invalid')
        values=tuple(_instant(text) for text in items)
        if list(values)!=sorted(set(values)) or values[-1]>=current[name]:
            raise ValueError('previous_deadlines_must_precede_current')
        previous[name]=values
    return current,previous,{name:_instant(text) for name,text in data['boundaries'].items()}


DEADLINES,PREVIOUS,FIXED=_load()


def deadline(name):
    """Exclusive end of the named approval as an aware Asia/Shanghai datetime."""
    return DEADLINES[name]


def boundary(name):
    """A fixed historical instant (not an expiry) as an aware datetime."""
    return FIXED[name]


def utc_text(name):
    """The current end in the UTC ISO form used by root-installed authority files."""
    return deadline(name).astimezone(timezone.utc).isoformat()


def approved_utc_texts(name):
    """Every approved end of one allowance, oldest first, in UTC ISO form."""
    return tuple(value.astimezone(timezone.utc).isoformat() for value in PREVIOUS.get(name,()))+(utc_text(name),)
