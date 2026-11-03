"""Single-item delete intent data; no cleanup/account/source authority."""
from dataclasses import dataclass
from hashlib import sha256
from cj_memory.domain import strict_object,InvalidInput

VERSION='MEMORY-ERASURE-DRAFT@1'


@dataclass(frozen=True,repr=False)
class ErasureCommand:
    action_id:str
    item_id:str
    expected_version:int
    raw:bytes

    @classmethod
    def parse(cls,raw):
        if type(raw) is not bytes or not 0<len(raw)<=32768:raise InvalidInput('bounded original erasure UTF8 required')
        try:value=strict_object(raw)
        except (ValueError,RecursionError) as error:raise InvalidInput('invalid original erasure JSON') from error
        if (type(value) is not dict or set(value)!={'version','action_id','item_id','expected_version'}
                or value.pop('version')!=VERSION):raise InvalidInput('exact erasure command fields required')
        for key in ('action_id','item_id'):
            identifier=value[key]
            if type(identifier) is not str or not identifier.strip() or len(identifier)>4096 or '\0' in identifier:
                raise InvalidInput('exact original erasure identifier required')
            try:identifier.encode('utf-8')
            except UnicodeError as error:raise InvalidInput('invalid erasure identifier UTF8') from error
        version=value['expected_version']
        if type(version) is not int or not 1<=version<=2**63-1:raise InvalidInput('positive original item version required')
        return cls(**value,raw=raw)

    def operation_id(self,scope):
        # ASCII cleanup ID does not truncate or normalize the private Unicode ID.
        return 'memory-erasure-v1:'+sha256(scope.encode()+b'\0'+self.raw).hexdigest()
