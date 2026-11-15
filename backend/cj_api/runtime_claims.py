"""B's canonical admission records, separate from G's disposable local mapping.

The B host supplies an existing protected directory, original-auth guard and
original-operation lookup. This records no fees and dispatches nothing. B must
retain this directory across releases/restores; it is not an experiment folder.
"""
import os
from pathlib import Path

from runtime_adapter.contract import VERSION, candidate, decode, digest, encode, label, require, Unavailable
from runtime_adapter.ports import PreparedOriginal
from .runtime_private import PrivateFileError,private_directory,read_private


class CanonicalClaims:
    def __init__(self,directory,binding,pins,*,guard,original_exists,admission_lock):
        self.directory=Path(directory)
        self.binding,self.pins=binding,pins
        self.guard,self.original_exists=guard,original_exists
        self.admission_lock=admission_lock
        self.capabilities={}
        with self._directory() as descriptor:
            info=os.fstat(descriptor)
            self.directory_identity=(info.st_dev,info.st_ino)

    def _directory(self):
        return private_directory(self.directory,Unavailable('CANONICAL_DIRECTORY_AUTHORITY'))

    def _request(self,raw):
        require(type(raw) is bytes and len(raw)<=131072,'CANONICAL_REQUEST_BOUND')
        request=decode(raw)
        require(type(request) is dict and set(request)=={'version','attempt_id','step_id',
            'binding_sha256','pins_sha256','kind','payload','candidate','prior_step_ids'},'CANONICAL_REQUEST_FIELDS')
        require(request['version']==VERSION and request['binding_sha256']==self.binding.key and
                request['pins_sha256']==self.pins.key,'CANONICAL_BINDING_MISMATCH')
        label(request['attempt_id'])
        prior=request['prior_step_ids']
        require(type(prior) is list and len(prior)<=128,'CANONICAL_STEP_BOUND')
        expected=['runtime-'+digest([self.binding.scope,request['attempt_id'],index]) for index in range(len(prior)+1)]
        require(prior==expected[:-1] and request['step_id']==expected[-1],'CANONICAL_CLIENT_STEP')
        require(request['kind'] in ('task_setup','message','new_conversation_message','lio_undo_current_trip',
            'start_controlled_generation','cancel_original_run','reflection') and type(request['payload']) is dict,
            'CANONICAL_ACTION')
        candidate(request['candidate'])
        require(encode(request)==raw,'CANONICAL_REQUEST_BYTES')
        return request

    def _name(self,step):
        # Same original scope/ledger/producer across token or pin changes. A new
        # session/candidate must not create a second namespace for the same ID.
        return digest([self.binding.scope,self.binding.ledger_id,self.binding.producer_id,step])+'.json'

    def claim(self,raw):
        request=self._request(raw)
        # The host supplies the original MESSAGE/action admission fence, not a
        # new unrelated filesystem/experiment lock. Lookup and claim share it.
        with self.admission_lock():
            return self._claim_locked(raw,request)

    def _write_guard(self,request):
        # Use only the validated canonical action, after consuming a capability
        # on dispatch. A malformed/mismatched request cannot preserve its token.
        self.guard(read_only=False,purpose='cancel_original' if request['kind']=='cancel_original_run' else 'claim')

    def _claim_locked(self,raw,request):
        self._write_guard(request)
        if self.original_exists(request['step_id']):return PreparedOriginal(False,None)
        with self._directory() as directory:
            info=os.fstat(directory)
            if (info.st_dev,info.st_ino)!=self.directory_identity:
                raise Unavailable('CANONICAL_DIRECTORY_CHANGED')
            try:
                descriptor=os.open(self._name(request['step_id']),
                    os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            except FileExistsError:
                return PreparedOriginal(False,None)
            # Interrupted/short/fsync-unknown records remain present. Never
            # unlink or repair them into a fresh admission.
            with os.fdopen(descriptor,'wb') as output:
                output.write(raw);output.flush();os.fsync(output.fileno())
            os.fsync(directory)
        self._write_guard(request)
        capability=object()
        self.capabilities[capability]=raw
        return PreparedOriginal(True,capability)

    def consume(self,raw,capability):
        """Consume before dispatch; failure or lost ACK never restores a token."""
        original=self.capabilities.pop(capability,None)
        if original is None or original!=raw:
            raise Unavailable('CANONICAL_CAPABILITY_SPENT_OR_MISMATCH')
        request=decode(original)
        self._write_guard(request)
        if self.read(request['step_id'])!=raw:
            raise Unavailable('CANONICAL_ORIGINAL_CHANGED')
        return request

    def read(self,step):
        self.guard(read_only=True)
        label(step)
        with self._directory() as directory:
            info=os.fstat(directory)
            if (info.st_dev,info.st_ino)!=self.directory_identity:
                raise Unavailable('CANONICAL_DIRECTORY_CHANGED')
            try:raw=read_private(self._name(step),131072,directory_fd=directory)
            except PrivateFileError as error:
                if error.reason=='bound':require(False,'CANONICAL_REQUEST_BOUND')
                raise Unavailable('CANONICAL_ORIGINAL_AUTHORITY') from None
        request=self._request(raw)
        require(request['step_id']==step,'CANONICAL_ORIGINAL_STEP')
        self.guard(read_only=True)
        return raw
