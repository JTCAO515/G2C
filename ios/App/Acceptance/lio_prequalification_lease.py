"""Separate B-issued read-only App permission; never opens a credential file."""
import hashlib
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import UUID

from lio_basic_ui_driver import compact, reject_duplicates


ACTIONS = ['launch', 'activate', 'snapshot', 'open_existing_history', 'select_existing_default',
           'earlier', 'scroll', 'audit_all', 'stop']
KEYS = frozenset('version state purpose lease_id app app_pin_sha256 sdk sdk_pin_sha256 source image '
                 'simulator_udids starts_at ends_at identities allowed_actions'.split())


def require(value):
    if not value:
        raise ValueError('Read-only App permission is unavailable or differs from its approved pin')


def reject_constant(_):
    raise ValueError('Nonfinite JSON is not a read-only permission')


def validate_prequalification_lease(raw, external_sha256, expected, now):
    require(hashlib.sha256(raw).hexdigest() == external_sha256)
    value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate read-only field'),
                       parse_constant=reject_constant)
    require(type(value) is dict and set(value) == KEYS)
    require(value['version'] == 'B-App-prequalification-lease.2'
            and value['state'] == 'READ_ONLY_PREQUALIFICATION_ISSUED'
            and value['purpose'] == 'C1048-basic14-official-App-read-only-prequalification')
    require(type(value['lease_id']) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value['lease_id']))
    for key in ('app', 'sdk'):
        require(type(value[key]) is dict and bool(value[key])
                and compact(value[key], sort_keys=True) == compact(expected[key], sort_keys=True)
                and value[key + '_pin_sha256']
                == hashlib.sha256(compact(value[key], sort_keys=True)).hexdigest())
    require(type(value['source']) is str and re.fullmatch(r'[0-9a-f]{40}', value['source'])
            and type(value['image']) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value['image']))
    require(value['source'] == expected['source'] and value['image'] == expected['image']
            and value['simulator_udids'] == expected['simulator_udids']
            and value['identities'] == expected['identities'] and value['allowed_actions'] == ACTIONS)
    simulators = value['simulator_udids']
    require(type(simulators) is dict and set(simulators) == {'zh', 'en'}
            and simulators['zh'] != simulators['en'])
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
    identities = value['identities']
    require(type(identities) is list and len(identities) == 2)
    result = {}
    for identity in identities:
        require(type(identity) is dict and set(identity)
                == {'locale', 'subject', 'default_conversation_id', 'default_generation'})
        locale = identity['locale']
        require(type(locale) is str and locale in ('zh', 'en') and locale not in result)
        for key in ('subject', 'default_conversation_id', 'default_generation'):
            require(type(identity[key]) is str and bool(identity[key].strip())
                    and '\0' not in identity[key] and len(identity[key].encode()) <= 16384)
        result[locale] = identity
    require(set(result) == {'zh', 'en'} and result['zh']['subject'] != result['en']['subject'])
    return result


class ReadOnlyApp:
    """Native-UI boundary with fixed selectors and a fresh grant before each dispatch.

    The caller supplies its separately pinned native controller and installed-App
    verifier. This adapter never signs in, selects arbitrary chats or qualifies a
    release. Missing/failed ACKs leave the same sticky barrier as NativeUI.
    """
    def __init__(self, native, read_lease, lease_sha256, expected, locale, *, clock, verify_artifact):
        require(locale in ('zh', 'en'))
        self.native, self.read_lease, self.lease_sha256 = native, read_lease, lease_sha256
        self.expected, self.locale = expected, locale
        self.clock, self.verify_artifact = clock, verify_artifact
        self.failed = False

    def command(self, action, **fields):
        require(not self.failed and action in ACTIONS)
        if action == 'scroll':
            require(set(fields) == {'direction'} and fields['direction'] in ('up', 'down'))
            steps = [('swipe_' + fields['direction'], {})]
        else:
            require(not fields)
            if action == 'open_existing_history':
                steps = [('tap', dict(identifier='lio.menu')), ('tap', dict(identifier='lio.chat.history'))]
            elif action == 'earlier':
                steps = [('tap', dict(identifier='lio.earlier'))]
            elif action == 'select_existing_default':
                # The old App has no CID in AX. Never guess a row from its title
                # or treat a UI ordinal as B's original conversation identity.
                raise ValueError('Existing default selection needs a separately verified UI mapping')
            else:
                steps = [(action, dict(language=self.locale) if action == 'launch' else {})]
        self.failed = True
        for kind, arguments in steps:
            raw = self.read_lease()
            validate_prequalification_lease(raw, self.lease_sha256, self.expected, self.clock())
            self.verify_artifact()
            require(self.native.simulator == self.expected['simulator_udids'][self.locale]
                    and self.native.bundle == 'space.go2china.app')
            permission = json.loads(raw)
            result = self.native.command(kind, startsAt=permission['starts_at'], endsAt=permission['ends_at'],
                                         **arguments)
        self.failed = False
        return result
