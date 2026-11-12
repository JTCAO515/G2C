"""Opaque original references; persist descriptors/hashes, never escaped AUTH bytes."""
from contextlib import contextmanager
from hashlib import sha256
import os
from pathlib import Path
import re
import stat

from runtime_adapter.contract import decode,digest,encode,require,Unavailable


class OriginalReferences:
    def __init__(self,directory,binding,reader,*,guard):
        self.directory=Path(directory);self.binding=binding;self.reader=reader;self.guard=guard
        with self._directory():pass

    @contextmanager
    def _directory(self):
        fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
                raise Unavailable('ORIGINAL_REFERENCE_DIRECTORY_AUTHORITY')
            yield fd
        finally:os.close(fd)

    def _bytes(self,token,descriptor):
        kind=descriptor['kind'];mid=descriptor['message_id'];op=descriptor['operation_id']
        if kind=='inventory':return self.reader.inventory(token,mid)
        if kind=='input':return self.reader.input(token,mid,op)
        if kind=='meter':return self.reader.meter(token,mid,op)
        if kind=='fee':return self.reader.fee(token,mid,op)
        return self.reader.artifact(token,mid,op,wire_input=kind=='wire_input')

    def issue(self,token,*,kind,message_id,operation_id=None):
        require(kind in ('inventory','input','meter','fee','artifact','wire_input'),'ORIGINAL_REFERENCE_KIND')
        require(type(message_id) is str and message_id and (kind=='inventory' and operation_id is None or
            kind!='inventory' and type(operation_id) is str and operation_id),'ORIGINAL_REFERENCE_SOURCE')
        self.guard(read_only=True)
        descriptor=dict(binding_sha256=self.binding.key,kind=kind,message_id=message_id,operation_id=operation_id)
        raw=self._bytes(token,descriptor)
        record=dict(source=descriptor,sha256=sha256(raw).hexdigest())
        ref='original-'+digest(record);body=encode(record)
        with self._directory() as directory:
            try:fd=os.open(ref+'.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            except FileExistsError:
                if self._record(directory,ref)!=record:raise Unavailable('ORIGINAL_REFERENCE_CHANGED')
            else:
                with os.fdopen(fd,'wb') as output:output.write(body);output.flush();os.fsync(output.fileno())
                os.fsync(directory)
        self.guard(read_only=True)
        return dict(ref=ref,sha256=record['sha256'])

    @staticmethod
    def _record(directory,ref):
        fd=os.open(ref+'.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as source:
            info=os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
                raise Unavailable('ORIGINAL_REFERENCE_AUTHORITY')
            raw=source.read(65537)
        require(len(raw)<=65536,'ORIGINAL_REFERENCE_BOUND')
        record=decode(raw)
        require(type(record) is dict and set(record)=={'source','sha256'} and
                ref=='original-'+digest(record),'ORIGINAL_REFERENCE_INTEGRITY')
        descriptor=record['source']
        require(type(descriptor) is dict and set(descriptor)=={'binding_sha256','kind','message_id','operation_id'} and
                descriptor['kind'] in ('inventory','input','meter','fee','artifact','wire_input'),'ORIGINAL_REFERENCE_DESCRIPTOR')
        return record

    def resolve(self,token,ref):
        require(type(ref) is str and re.fullmatch('original-[a-f0-9]{64}',ref) is not None,'ORIGINAL_REFERENCE_ID')
        self.guard(read_only=True)
        with self._directory() as directory:record=self._record(directory,ref)
        if record['source']['binding_sha256']!=self.binding.key:
            raise Unavailable('ORIGINAL_REFERENCE_OWNER_CHANGED')
        raw=self._bytes(token,record['source'])
        if sha256(raw).hexdigest()!=record['sha256']:raise Unavailable('ORIGINAL_REFERENCE_BYTES_CHANGED')
        self.guard(read_only=True)
        return raw
