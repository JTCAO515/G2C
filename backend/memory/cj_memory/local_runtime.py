"""Explicit local runtime selection; no automatic subject/slot or consent guesses."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from types import MappingProxyType

from .domain import Service, InvalidInput
from .local import LocalMemoryConfiguration, read_private_policy
from .postgres import Repository
from .runtime import RuntimeMemory, RuntimeDenied, Selection


@dataclass(frozen=True)
class RuntimeConfiguration:
    collection: LocalMemoryConfiguration
    selections: object

    @classmethod
    def from_bytes(cls, raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise InvalidInput('duplicate runtime policy field')
                result[key] = value
            return result
        try:
            if type(raw) is not bytes or not 0 < len(raw) <= 262144:
                raise InvalidInput('bounded runtime policy required')
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
            if (type(value) is not dict or set(value) != {'version', 'collection', 'selections'}
                    or value['version'] != 'local-memory-run.1'
                    or type(value['selections']) is not dict or not value['selections']):
                raise InvalidInput('explicit runtime memory policy required')
            collection = LocalMemoryConfiguration.from_bytes(json.dumps(value['collection']).encode())
            selections = {}
            for identity, row in value['selections'].items():
                if (type(row) is not dict or set(row) != {'subject', 'slots', 'max_bytes'}
                        or type(row['slots']) is not list
                        or any(type(s) is not str for s in row['slots'])
                        or len(set(row['slots'])) != len(row['slots'])):
                    raise InvalidInput('explicit runtime selection fields required')
                selection = Selection(row['subject'], frozenset(row['slots']), row['max_bytes'])
                profile = collection.profiles[identity]
                if selection.subject not in profile.subjects or not selection.slots <= profile.slots.keys():
                    raise InvalidInput('selection outside collection policy')
                if any(not profile.slots[slot].collection_allowed
                       or not profile.slots[slot].semantic_resolved for slot in selection.slots):
                    raise InvalidInput('runtime selection requires approved canonical slots')
                selections[identity] = selection
            return cls(collection, MappingProxyType(selections))
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            raise InvalidInput('invalid runtime memory policy') from None

    def bind(self, database, scope, identity, admit):
        """Host passes the canonical identity and fresh admission function."""
        selection = self.selections.get(identity)
        if selection is None:
            raise RuntimeDenied('runtime memory identity not configured')
        profile = self.collection.profiles[identity]

        def guard(stage):
            principal = admit()
            if principal.subject != identity or profile.expires_at <= datetime.now(timezone.utc):
                raise RuntimeDenied('runtime memory selection expired or identity changed')
            return principal, scope

        guard('runtime_bind')
        with database.connect(scope) as conn:
            conn.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s) ON CONFLICT DO NOTHING', (scope,))
        repository = Repository(lambda: database.connect(scope), scope,
                                transaction_binder=lambda conn, cursor: conn.bind_scope(cursor))
        return RuntimeMemory(Service(repository), guard, selection)


def load_runtime_configuration(path):
    return RuntimeConfiguration.from_bytes(read_private_policy(path))
