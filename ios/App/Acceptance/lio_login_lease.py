"""B-App-login-lease.1 metadata boundary. This module never opens an invite."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID
from zoneinfo import ZoneInfo

from lio_basic_ui_driver import compact, reject_duplicates

KEYS = frozenset('version state purpose lease_id app app_pin_sha256 source image simulator_udids starts_at ends_at identities file_format official_ui allowed_actions'.split())
UI = dict(field='demo.invite.code', kind='SecureField', submit='existing_official_App_login_action')
ACTIONS = ['official_sign_in', 'app_automatic_read_only_loading']


def require(value):
    if not value:
        raise ValueError('Official sign-in lease is unavailable or differs from the approved packet')


def reject_constant(_):
    raise ValueError('Nonfinite JSON is not a lease')


def validate_login_lease(raw, external_sha256, expected, now):
    """Return locale metadata only, after whole-file and whole-App validation."""
    require(hashlib.sha256(raw).hexdigest() == external_sha256)
    value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate login lease field'),
                       parse_constant=reject_constant)
    require(type(value) is dict and set(value) == KEYS)
    require(value['version'] == 'B-App-login-lease.1' and value['state'] == 'SIGN_IN_ONLY_ISSUED'
            and value['purpose'] == 'C1048-basic14-official-App-sign-in-only')
    require(type(value['lease_id']) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value['lease_id']))
    require(value['app'] == expected['app'] and value['app_pin_sha256']
            == hashlib.sha256(compact(value['app'], sort_keys=True)).hexdigest())
    require(type(value['source']) is str and re.fullmatch(r'[0-9a-f]{40}', value['source'])
            and value['source'] == expected['source'])
    require(type(value['image']) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value['image'])
            and value['image'] == expected['image'])
    simulators = value['simulator_udids']
    require(type(simulators) is dict and set(simulators) == {'zh', 'en'}
            and simulators == expected['simulator_udids'] and simulators['zh'] != simulators['en'])
    for identifier in simulators.values():
        require(type(identifier) is str and str(UUID(identifier)).lower() == identifier.lower())
    dates = []
    for key in ('starts_at', 'ends_at'):
        require(type(value[key]) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value[key]))
        dates.append(datetime.fromisoformat(value[key].replace('Z', '+00:00')))
    start, end = dates
    require(now.tzinfo is not None and start <= now < end and 0 < (end - start).total_seconds() <= 600)
    local_start, local_end = (date.astimezone(ZoneInfo('Asia/Shanghai')) for date in dates)
    require(local_start.date() == local_end.date() and local_start.hour >= 8
            and (local_end.hour < 23 or (local_end.hour == 23 and local_end.minute == local_end.second == 0)))
    require(value['file_format'] == 'one_ascii_line_no_lf_preserve_bytes'
            and value['official_ui'] == UI and value['allowed_actions'] == ACTIONS)
    identities = value['identities']
    require(type(identities) is list and len(identities) == 2)
    result = {}
    for identity in identities:
        require(type(identity) is dict and set(identity) == {'locale', 'subject', 'invite_file'})
        locale = identity['locale']
        require(locale in ('zh', 'en') and locale not in result and type(identity['subject']) is str
                and identity['subject'] == expected['subjects'][locale])
        path = identity['invite_file']
        require(type(path) is str and '\0' not in path and Path(path).is_absolute())
        result[locale] = identity
    require(set(result) == {'zh', 'en'} and result['zh']['subject'] != result['en']['subject']
            and result['zh']['invite_file'] != result['en']['invite_file'])
    return result
