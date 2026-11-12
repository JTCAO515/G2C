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

    @classmethod
    def load(cls, path, subjects, *, clock=time.time):
        from .local_app import ISSUER, scope_for

        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError('owned 0600 tool evidence manifest required')
            raw = source.read(131073)
        if len(raw) > 131072:
            raise ValueError('tool evidence manifest bound exceeded')
        data = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate tool evidence field'))
        legacy_keys={'version','directory','messages','expires_at','source_commit'}
        if type(data) is not dict:raise ValueError('explicit evidence window required')
        old=data.get('version')=='G2C-tool-evidence-window.1' and data.keys()==legacy_keys
        upgraded=data.get('version')=='G2C-synthetic-evidence-window.2' and data.keys()==legacy_keys|{'kinds'}
        kinds=['tool'] if old else data.get('kinds')
        if (not (old or upgraded) or type(kinds) is not list or not kinds or len(kinds)>2
                or any(type(kind) is not str or kind not in ('tool','lio_intake') for kind in kinds)
                or len(set(kinds))!=len(kinds)
                or type(data['directory']) is not str or not Path(data['directory']).is_absolute()
                or type(data['source_commit']) is not str or type(data['expires_at']) is not str
                or re.fullmatch('[0-9a-f]{40}',data['source_commit']) is None
                or type(data['messages']) is not list or not 1<=len(data['messages'])<=512):
            raise ValueError('explicit tool/model evidence selection required')
        directory = Path(data['directory'])
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('owned 0700 tool evidence directory required')
        expires = datetime.fromisoformat(data['expires_at'])
        if expires.tzinfo is None or not 0 < expires.timestamp() - clock() <= 86400:
            raise ValueError('current bounded tool evidence window required')
        selected = set()
        for entry in data['messages']:
            if (type(entry) is not dict or entry.keys() != {'subject', 'message_id'}
                    or type(entry['subject']) is not str or entry['subject'] not in subjects):
                raise ValueError('existing invited synthetic subject required')
            message_id(entry['message_id'])
            selected.add((scope_for(ISSUER, entry['subject']), entry['message_id']))
        if len(selected) != len(data['messages']):
            raise ValueError('duplicate selected tool evidence message')
        implementation = sha256(Path(__file__).with_name('real_services.py').read_bytes()).hexdigest()
        return cls(directory,frozenset(selected),expires.timestamp(),data['source_commit'],implementation,clock,
                   intake_enabled='lio_intake' in kinds,tools_enabled='tool' in kinds)

    def record(self, operation, name, raw, receipt):
        if not self.tools_enabled:return
        binding = operation.binding
        if (binding.scope, binding.message_id) not in self.selected:
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
        binding=operation.binding
        if (binding.scope,binding.message_id) not in self.selected:return
        now=self.clock()
        if now>=self.expires_at:raise BudgetUnknown('original intake evidence window expired')
        if operation.registration_id not in ('model.lio_intake.1','model.lio_intake.2','model.lio_intake.3','model.lio_intake.4','model.lio_intake.5','model.lio_intake.6','model.lio_intake.7','model.lio_intake.8') or operation.command.kind!='model':
            raise BudgetUnknown('original intake registration required')
        value=dict(version='G2C-lio-intake-evidence.1',capture_kind='model',source_commit=self.source_commit,
            model_implementation_sha256=self.tool_sha256,scope_sha256=sha256(binding.scope.encode()).hexdigest(),
            message_id=binding.message_id,run_id=binding.run_id,operation_key=operation.operation_key,
            registration_id=operation.registration_id,attempt_id=operation.command.attempt_id,
            operation_id=operation.command.operation_id,input_sha256=operation.command.input_digest,
            response_sha256=sha256(raw).hexdigest(),result_utf8=raw.decode('utf-8'),receipt=dict(receipt),
            observed_at=datetime.fromtimestamp(now,timezone.utc).isoformat())
        self._persist(operation,value)

    def _persist(self,operation,value):
        binding=operation.binding
        identity = sha256(canonical([binding.scope, binding.run_id, operation.operation_key,
                                     operation.command.attempt_id])).hexdigest()
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
