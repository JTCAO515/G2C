"""Opaque references to original B registry/reservation sources for one use.

No caller supplies metadata body bytes. Original sources are reconstructed on
each read; private descriptors contain neither credentials nor C payloads.
Existing OriginalReferences formats/kinds remain unchanged.
"""
from hashlib import sha256
import os
from pathlib import Path
import re
from time import monotonic

from runtime_adapter.contract import decode,digest,encode,hash256,require,Unavailable
from .runtime_private import private_directory,read_private,PrivateFileError


VERSION='G2C-fixture-original-reference.1'
SCAN_VERSION='G2C-fixture-scan-reference.1'
PREPARATION_VERSION='G2C-fixture-preparation-policy-reference.1'
COST_VERSION='G2C-fixture-preparation-cost-reference.1'
KINDS=frozenset({'registry','reservation','scan','preparation_policy','preparation_cost'})
PREPARATION_KINDS=frozenset({'preparation_policy','preparation_cost'})
UNSCOPED_KINDS=frozenset({'registry'})|PREPARATION_KINDS


def reference_version(kind):
    if kind=='scan':return SCAN_VERSION
    if kind=='preparation_policy':return PREPARATION_VERSION
    if kind=='preparation_cost':return COST_VERSION
    return VERSION


class FixtureOriginalReferences:
    def __init__(self,directory,registry,use=None,*,scan_journal=None,preparation_cost=None,clock=monotonic):
        self.directory,self.registry,self.use=Path(directory),registry,use
        self.scan_journal,self.clock=scan_journal,clock
        self.preparation_cost=preparation_cost
        if preparation_cost is not None:
            require(preparation_cost.inventory.binding==registry.producer,'FIXTURE_COST_PRODUCER_BINDING')
        self.binding=registry.consumer
        with self._directory()as fd:
            info=os.fstat(fd);self.identity=(info.st_dev,info.st_ino)

    def _directory(self):
        return private_directory(self.directory,Unavailable('FIXTURE_REFERENCE_DIRECTORY_AUTHORITY'))

    def _token(self,token):
        if sha256(token.encode()).hexdigest()!=self.binding.auth_session_id:
            raise Unavailable('FIXTURE_REFERENCE_SESSION_CHANGED')

    def _bytes(self,kind,use=None):
        if kind=='registry':return self.registry.policy_source()
        if kind=='preparation_policy':return self.registry.preparation_policy_source()
        if kind=='preparation_cost':
            self.registry.preparation_policy_source()
            if self.preparation_cost is None:raise Unavailable('FIXTURE_COST_READER_NOT_CONNECTED')
            raw=self.preparation_cost.read(deadline=self.clock()+30)
            self.registry.preparation_policy_source()
            return raw
        selected=self.use if use is None else use
        if selected is None:raise Unavailable('FIXTURE_REFERENCE_USE_REQUIRED')
        if kind=='scan':
            if self.scan_journal is None:raise Unavailable('FIXTURE_SCAN_READER_NOT_CONNECTED')
            return self.scan_journal.read(selected,deadline=self.clock()+30)
        return encode(self.registry.read(selected))

    def _source(self,kind,use=None):
        require(kind in KINDS,'FIXTURE_REFERENCE_KIND')
        selected=self.use if use is None else use
        if kind not in UNSCOPED_KINDS and selected is None:raise Unavailable('FIXTURE_REFERENCE_USE_REQUIRED')
        return dict(version=reference_version(kind),binding_sha256=self.binding.key,kind=kind,
            policy_sha256=self.registry.policy_sha256,
            use_sha256=None if kind in UNSCOPED_KINDS else sha256(selected).hexdigest())

    def issue(self,token,kind):
        self._token(token);source=self._source(kind);raw=self._bytes(kind)
        record=dict(source=source,sha256=sha256(raw).hexdigest())
        ref='original-'+digest(record)
        with self._directory()as fd:
            self._identity(fd)
            try:out=os.open(ref+'.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
            except FileExistsError:
                if self._record(fd,ref)!=record:raise Unavailable('FIXTURE_REFERENCE_CHANGED')
            else:
                with os.fdopen(out,'wb')as target:
                    target.write(encode(record));target.flush();os.fsync(target.fileno())
                os.fsync(fd)
        if self._bytes(kind)!=raw:raise Unavailable('FIXTURE_REFERENCE_SOURCE_CHANGED')
        self._token(token)
        return dict(ref=ref,sha256=record['sha256'])

    def _identity(self,fd):
        info=os.fstat(fd)
        if(info.st_dev,info.st_ino)!=self.identity:
            raise Unavailable('FIXTURE_REFERENCE_DIRECTORY_CHANGED')

    def _record(self,fd,ref):
        try:raw=read_private(ref+'.json',65536,directory_fd=fd)
        except(PrivateFileError,OSError):raise Unavailable('FIXTURE_REFERENCE_UNAVAILABLE')from None
        value=decode(raw)
        require(type(value)is dict and set(value)=={'source','sha256'}
            and ref=='original-'+digest(value)and encode(value)==raw,'FIXTURE_REFERENCE_INTEGRITY')
        hash256(value['sha256'])
        source=value['source']
        require(type(source)is dict and set(source)=={'version','binding_sha256','kind','policy_sha256','use_sha256'}
            and type(source['kind'])is str and source['kind']in KINDS,'FIXTURE_REFERENCE_DESCRIPTOR')
        if source['kind']not in UNSCOPED_KINDS and self.use is None:
            hash256(source['use_sha256'])
            expected=dict(version=reference_version(source['kind']),
                binding_sha256=self.binding.key,kind=source['kind'],
                policy_sha256=self.registry.policy_sha256,use_sha256=source['use_sha256'])
        else:expected=self._source(source['kind'])
        if source!=expected:raise Unavailable('FIXTURE_REFERENCE_ORIGINAL_USE_CHANGED')
        return value

    def contains(self,token,ref):
        """Route only by an existing owned descriptor; unreadable is not absent."""
        require(type(ref)is str and re.fullmatch('original-[a-f0-9]{64}',ref)is not None,'FIXTURE_REFERENCE_ID')
        self._token(token)
        with self._directory()as fd:
            self._identity(fd)
            try:read_private(ref+'.json',65536,directory_fd=fd)
            except FileNotFoundError:return False
        return True

    def resolve(self,token,ref):
        require(type(ref)is str and re.fullmatch('original-[a-f0-9]{64}',ref)is not None,'FIXTURE_REFERENCE_ID')
        self._token(token)
        with self._directory()as fd:
            self._identity(fd);record=self._record(fd,ref)
        kind=record['source']['kind']
        use=self.registry.original_use(record['source']['use_sha256'])if kind not in UNSCOPED_KINDS and self.use is None else self.use
        raw=self._bytes(kind,use)
        if sha256(raw).hexdigest()!=record['sha256']:
            raise Unavailable('FIXTURE_REFERENCE_SOURCE_CHANGED')
        if self._bytes(kind,use)!=raw:
            raise Unavailable('FIXTURE_REFERENCE_SOURCE_CHANGED')
        self._token(token)
        return raw
