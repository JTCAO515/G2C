"""CLEANUP@1.0 registry freeze; independent inventory and explicit owner hooks."""
from dataclasses import dataclass
import json
from cj_strict_json import reject_duplicates
from .core import Entry, Invalid, digest, encode, identifier
from .hooks import VERSION

VERSIONS=(VERSION,'CLEANUP@1.1')


@dataclass(frozen=True)
class ProtocolEntry(Entry):
    protocol: str | None


@dataclass(frozen=True, repr=False)
class FrozenRegistry:
    raw: bytes
    inventory: tuple[str, ...]
    entries: tuple[Entry, ...]
    gaps: tuple[str, ...]
    versions: tuple[str, ...] = (VERSION,)

    @property
    def digest(self): return digest(self.raw)


def freeze(raw: bytes, inventory: tuple[str, ...], *, versions=(VERSION,)) -> FrozenRegistry:
    """inventory is the trusted host's independent complete set of leaf targets."""
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= 262144:
            raise Invalid('invalid registry bytes')
        expected = tuple(sorted(identifier(x) for x in inventory))
        versions=tuple(sorted(versions))
        if not versions or len(set(versions))!=len(versions) or any(v not in VERSIONS for v in versions):raise Invalid('explicit cleanup protocols required')
        if not expected or len(set(expected)) != len(expected): raise Invalid('inventory required')
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicates(Invalid,'duplicate registry key'))
        identifier(obj['version'])
        entries = []
        def walk(node, parent=''):
            target = parent + identifier(node['id'])
            children = node.get('objects', [])
            if type(children) is not list: raise Invalid('invalid registry objects')
            nested = [x for x in children if type(x) is dict]
            if nested:
                if len(nested) != len(children): raise Invalid('mixed registry inventory')
                for child in nested: walk(child, target+'/')
            else:
                if any(type(x) is not str for x in children): raise Invalid('invalid registry objects')
                protocol=node.get('cleanup_protocol')
                entries.append(ProtocolEntry(target,digest(encode(node)),protocol in versions,
                                             protocol if protocol in VERSIONS else None))
        for store in obj['stores']: walk(store)
        ids = {e.registry_id for e in entries}
        if len(ids) != len(entries): raise Invalid('duplicate registry target')
        gaps = tuple(sorted(ids.symmetric_difference(expected)))
        return FrozenRegistry(raw,expected,tuple(sorted(entries,key=lambda e:e.registry_id)),gaps,versions)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        raise Invalid('invalid cleanup registry') from None
