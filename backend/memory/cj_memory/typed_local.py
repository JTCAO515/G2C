"""Explicit typed collection configuration, separate from legacy conversation policy."""
from dataclasses import dataclass, replace
from types import MappingProxyType

from .domain import InvalidInput
from .local import LocalMemoryConfiguration, read_private_policy
from .typed import decode, packed


@dataclass(frozen=True)
class TypedConfiguration:
    collection: LocalMemoryConfiguration
    travel_contexts: object

    @classmethod
    def from_bytes(cls, raw):
        value=decode(raw,maximum=262144)
        if (set(value)!={'version','collection','travel_contexts'}
                or value['version']!='local-memory-typed.1' or type(value['travel_contexts']) is not dict):
            raise InvalidInput('explicit typed collection configuration required')
        collection=LocalMemoryConfiguration.from_bytes(packed(value['collection']))
        if set(value['travel_contexts'])!=set(collection.profiles):
            raise InvalidInput('explicit travel policy for each configured identity required')
        contexts={}
        for identity,identifiers in value['travel_contexts'].items():
            if (type(identifiers) is not list
                    or any(type(v) is not str or not v.strip() or len(v)>4096 for v in identifiers)
                    or len(set(identifiers))!=len(identifiers)):
                raise InvalidInput('explicit immutable allowed travel IDs required')
            for identifier in identifiers:identifier.encode('utf-8')
            contexts[identity]=frozenset(identifiers)
        return cls(collection,MappingProxyType(contexts))

    def policy(self, identity):
        # Consent is explicit. B ownership alone does not permit collecting in
        # every travel; do not reinterpret the legacy conversation allow-list.
        return replace(self.collection.profiles[identity].manual_policy(),
                       context_ids=self.travel_contexts[identity])


def load_typed_configuration(path):
    return TypedConfiguration.from_bytes(read_private_policy(path))
