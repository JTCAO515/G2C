"""Operator-selected synthetic tool results before Lio projection."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import time

from cj_message.demo_dialogue import message_id
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import canonical
from cj_usage.metered_exit import BudgetUnknown
from .runtime_private import read_private,PrivateFileError


@dataclass(frozen=True)
class ToolEvidence:
    directory: Path
    selected: frozenset
    expires_at: float
    source_commit: str
    tool_sha256: str
    clock: object = time.time
    intake_enabled: bool = False
    tools_enabled: bool = True
    model_enabled: bool = False
    runtime_scopes: frozenset = frozenset()
    runtime_selection: object = None

    @classmethod
    def load(cls, path, subjects, *, clock=time.time,runtime_selection=None):
        from .local_app import ISSUER, scope_for

        try:raw=read_private(path,131072)
        except PrivateFileError as error:
            raise ValueError('tool evidence manifest bound exceeded' if error.reason=='bound' else
                'owned 0600 tool evidence manifest required') from None
        data = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate tool evidence field'))
        legacy_keys={'version','directory','messages','expires_at','source_commit'}
        if type(data) is not dict:raise ValueError('explicit evidence window required')
        old=data.get('version')=='G2C-tool-evidence-window.1' and data.keys()==legacy_keys
        upgraded=data.get('version')=='G2C-synthetic-evidence-window.2' and data.keys()==legacy_keys|{'kinds'}
        runtime=data.get('version')=='G2C-runtime-evidence-window.3' and data.keys()==legacy_keys|{'kinds'}
        scoped=data.get('version')=='G2C-runtime-evidence-window.4' and data.keys()==(legacy_keys-{'messages'})|{'subjects','kinds'}
        kinds=['tool'] if old else data.get('kinds')
        allowed=('tool','model') if runtime or scoped else ('tool','lio_intake')
        selection=data.get('subjects') if scoped else data.get('messages')
        if (not (old or upgraded or runtime or scoped) or type(kinds) is not list or not kinds or len(kinds)>2
                or any(type(kind) is not str or kind not in allowed for kind in kinds)
                or len(set(kinds))!=len(kinds)
                or type(data['directory']) is not str or not Path(data['directory']).is_absolute()
                or type(data['source_commit']) is not str or type(data['expires_at']) is not str
                or re.fullmatch('[0-9a-f]{40}',data['source_commit']) is None
                or type(selection) is not list or not 1<=len(selection)<=(4 if scoped else 512)
                or (runtime_selection is None)==scoped):
            raise ValueError('explicit tool/model evidence selection required')
        directory = Path(data['directory'])
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('owned 0700 tool evidence directory required')
        expires = datetime.fromisoformat(data['expires_at'])
        if expires.tzinfo is None or not 0 < expires.timestamp() - clock() <= (7*86400 if scoped else 86400):
            raise ValueError('current bounded tool evidence window required')
        selected = set()
        runtime_scopes=set()
        for entry in selection:
            if scoped:
                if type(entry) is not str or entry not in subjects:
                    raise ValueError('existing invited runtime synthetic subject required')
                runtime_scopes.add(scope_for(ISSUER,entry))
                continue
            if (type(entry) is not dict or entry.keys() != {'subject', 'message_id'}
                    or type(entry['subject']) is not str or entry['subject'] not in subjects):
                raise ValueError('existing invited synthetic subject required')
            message_id(entry['message_id'])
            selected.add((scope_for(ISSUER, entry['subject']), entry['message_id']))
        if len(runtime_scopes if scoped else selected) != len(selection):
            raise ValueError('duplicate selected tool evidence message')
        implementation = sha256(Path(__file__).with_name('real_services.py').read_bytes()).hexdigest()
        return cls(directory,frozenset(selected),expires.timestamp(),data['source_commit'],implementation,clock,
                   intake_enabled='lio_intake' in kinds,tools_enabled='tool' in kinds,model_enabled='model' in kinds,
                   runtime_scopes=frozenset(runtime_scopes),runtime_selection=runtime_selection)

    def selects(self,binding):
        if self.runtime_selection is None:return (binding.scope,binding.message_id) in self.selected
        if binding.scope not in self.runtime_scopes:return False
        return self.runtime_selection(binding)

    def captures_model(self,binding):return self.model_enabled and self.selects(binding)

    def record(self, operation, name, raw, receipt):
        if not self.tools_enabled:return
        binding = operation.binding
        if not self.selects(binding):
            return
        now = self.clock()
        if now >= self.expires_at:
            raise BudgetUnknown('original tool evidence window expired')
        value = dict(version='G2C-tool-evidence.1', source_commit=self.source_commit,
            tool_implementation_sha256=self.tool_sha256,
            scope_sha256=sha256(binding.scope.encode()).hexdigest(), message_id=binding.message_id,
            run_id=binding.run_id, operation_key=operation.operation_key,
            registration_id=operation.registration_id, tool=name,
            attempt_id=operation.command.attempt_id, operation_id=operation.command.operation_id,
            input_sha256=operation.command.input_digest,
            input_utf8=operation.original.input_bytes.decode('utf-8'),
            response_sha256=receipt['response_sha256'], result_utf8=raw.decode('utf-8'),
            receipt=dict(receipt), observed_at=datetime.fromtimestamp(now, timezone.utc).isoformat())
        self._persist(operation,value)

    def record_intake(self,operation,raw,receipt):
        """Selected complete model output, explicitly separate from tool evidence."""
        if not self.intake_enabled:return
        self._record_model(operation,raw,receipt,legacy=True)

    def record_model(self,operation,raw,receipt):
        """Explicit v3 windows include answer/draft/intake/reflection/memory."""
        if not self.model_enabled:return
        self._record_model(operation,raw,receipt,legacy=False)

    def record_model_input(self,operation,raw):
        """Exact serialized HTTP body before send; never headers or API keys."""
        binding=operation.binding
        if not self.model_enabled or not self.selects(binding):return
        now=self.clock()
        if now>=self.expires_at:raise BudgetUnknown('original model wire evidence window expired')
        value=dict(version='G2C-model-wire-input.1',capture_kind='model_wire_input',source_commit=self.source_commit,
            model_implementation_sha256=self.tool_sha256,scope_sha256=sha256(binding.scope.encode()).hexdigest(),
            message_id=binding.message_id,run_id=binding.run_id,operation_key=operation.operation_key,
            registration_id=operation.registration_id,attempt_id=operation.command.attempt_id,
            operation_id=operation.command.operation_id,logical_input_sha256=operation.command.input_digest,
            wire_input_sha256=sha256(raw).hexdigest(),wire_input_utf8=raw.decode('utf-8'),
            observed_at=datetime.fromtimestamp(now,timezone.utc).isoformat())
        self._persist(operation,value,variant='model_wire_input')

    def _record_model(self,operation,raw,receipt,*,legacy):
        binding=operation.binding
        if not self.selects(binding):return
        now=self.clock()
        if now>=self.expires_at:raise BudgetUnknown('original intake evidence window expired')
        if legacy:
            if operation.registration_id not in ('model.lio_intake.1','model.lio_intake.2','model.lio_intake.3','model.lio_intake.4','model.lio_intake.5','model.lio_intake.6','model.lio_intake.7','model.lio_intake.8') or operation.command.kind!='model':
                raise BudgetUnknown('original intake registration required')
        elif operation.command.kind not in ('model','memory'):
            raise BudgetUnknown('original model registration required')
        value=dict(version='G2C-lio-intake-evidence.1' if legacy else 'G2C-model-evidence.1',capture_kind='model',source_commit=self.source_commit,
            model_implementation_sha256=self.tool_sha256,scope_sha256=sha256(binding.scope.encode()).hexdigest(),
            message_id=binding.message_id,run_id=binding.run_id,operation_key=operation.operation_key,
            registration_id=operation.registration_id,attempt_id=operation.command.attempt_id,
            operation_id=operation.command.operation_id,input_sha256=operation.command.input_digest,
            response_sha256=sha256(raw).hexdigest(),result_utf8=raw.decode('utf-8'),receipt=dict(receipt),
            observed_at=datetime.fromtimestamp(now,timezone.utc).isoformat())
        if not legacy:value['input_utf8']=operation.original.input_bytes.decode('utf-8')
        self._persist(operation,value)

    def _persist(self,operation,value,*,variant=None):
        binding=operation.binding
        parts=[binding.scope,binding.run_id,operation.operation_key,operation.command.attempt_id]
        if variant is not None:parts.append(variant)
        identity = sha256(canonical(parts)).hexdigest()
        descriptor = None
        try:
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise BudgetUnknown('selected evidence directory authority changed')
            target = os.open(identity + '.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=descriptor)
            with os.fdopen(target, 'wb') as output:
                output.write(canonical(value))
                output.flush()
                os.fsync(output.fileno())
            os.fsync(descriptor)
        except OSError as error:
            raise BudgetUnknown('original selected evidence unavailable; do not redispatch') from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
