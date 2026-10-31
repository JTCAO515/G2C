"""Explicit accept/reject of a source-bound Proposal via the sole original act."""
from dataclasses import dataclass
import json
from .domain import identifier,packed


@dataclass(frozen=True)
class NeedsAction:
    raw:bytes
    action_id:str
    kind:str
    proposal_id:str
    candidate_hash:str

    @classmethod
    def parse(cls,raw):
        if type(raw) is not bytes or not 0<len(raw)<=32768:raise ValueError('bounded original action required')
        value=json.loads(raw)
        if (type(value) is not dict or set(value)!={'version','action_id','kind','proposal_id','candidate_hash'}
                or value['version']!='TRIP-needs-action.1' or packed(value)!=raw):
            raise ValueError('exact canonical needs action required')
        identifier(value['action_id']);identifier(value['proposal_id'])
        if value['kind'] not in ('accept','reject'):raise ValueError('explicit choice required')
        digest=value['candidate_hash']
        if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('original candidate hash required')
        return cls(raw,value['action_id'],value['kind'],value['proposal_id'],digest)
