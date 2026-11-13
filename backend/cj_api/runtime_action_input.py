"""Retain exact native action targets before side effects, not a fee ledger.

Targets live beside the non-restored canonical claim. They are used internally
to query that original native action after ACK loss, never as authority to apply
another action, restore erased content or expose a file through the collector.
"""
import os

from runtime_adapter.contract import decode,digest,encode,require,Unavailable
from .runtime_private import read_private


class NativeActionInputs:
    def __init__(self,claims):self.claims=claims

    def _name(self,step_id,label):
        binding=self.claims.binding
        return 'native-'+digest([binding.scope,binding.ledger_id,binding.producer_id,step_id,label])+'.json'

    def record(self,request,native,*,deadline,label='action'):
        original=self.claims.read(request['step_id'],deadline=deadline)
        if original!=encode(request):raise Unavailable('NATIVE_ACTION_CLAIM_CHANGED')
        value=dict(version='G2C-native-action-input.1',binding_sha256=self.claims.binding.key,
            request_sha256=digest(request),label=label,native=native)
        raw=encode(value)
        require(len(raw)<=524288,'NATIVE_ACTION_INPUT_BOUND')
        # The canonical directory was already pinned by B. No mkdir, alternate
        # target, overwrite, repair or replay if any prior file/ACK exists.
        with self.claims.claims._directory() as directory:
            descriptor=os.open(self._name(request['step_id'],label),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                0o600,dir_fd=directory)
            with os.fdopen(descriptor,'wb') as output:
                output.write(raw);output.flush();os.fsync(output.fileno())
            os.fsync(directory)
        self.claims.read(request['step_id'],deadline=deadline)

    def read(self,request,*,deadline,label='action'):
        self.claims.read(request['step_id'],deadline=deadline)
        with self.claims.claims._directory() as directory:
            raw=read_private(self._name(request['step_id'],label),524288,directory_fd=directory)
        value=decode(raw)
        require(type(value) is dict and set(value)=={'version','binding_sha256','request_sha256','label','native'} and
            value['version']=='G2C-native-action-input.1' and value['binding_sha256']==self.claims.binding.key and
            value['request_sha256']==digest(request) and value['label']==label,'NATIVE_ACTION_INPUT_BINDING_CHANGED')
        self.claims.read(request['step_id'],deadline=deadline)
        return value['native']
