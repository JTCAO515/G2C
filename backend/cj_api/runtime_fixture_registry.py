"""B-issued fixture reuse policy and durable use reservations.

This stores no C payload, creates no fixture, changes no financial ledger and
dispatches nothing. Native source qualification, isolation and publication are
separate required boundaries; a reservation is never their PASS witness.
"""
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re

from runtime_adapter.contract import decode,digest,encode,hash256,label,require,Unavailable
from .runtime_private import private_directory,read_private,PrivateFileError

VERSION='G2C-fixture-use-registry.1'
POLICY_FIELDS=frozenset({'version','registry_id','fixture_id','fixture_revision','producer_binding_sha256',
    'consumer_binding_sha256','baseline','consumer_pins_sha256','consumer_registration_ref',
    'experiment_ref','public_release_ref','batch_ids','candidate_ids','languages','valid_from',
    'valid_until','maximum_uses'})
USE_FIELDS=frozenset({'binding_sha256','pins_sha256','batch_id','candidate_id','task_id','language',
    'attempt_id','step_id','request_sha256'})


def origin(value):
    require(type(value)is dict and set(value)=={'ref','sha256'}
        and type(value['ref'])is str and re.fullmatch('original-[a-f0-9]{64}',value['ref'])is not None,
        'FIXTURE_ORIGINAL_REFERENCE')
    hash256(value['sha256'])


def timestamp(value):
    require(type(value)is str,'FIXTURE_REGISTRY_TIME')
    try:result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:require(False,'FIXTURE_REGISTRY_TIME')
    require(result.tzinfo is not None,'FIXTURE_REGISTRY_TIME')
    return result


def use_fields(value):
    require(type(value)is dict and set(value)==USE_FIELDS,'FIXTURE_USE_FIELDS')
    for key in ('binding_sha256','pins_sha256','request_sha256'):hash256(value[key])
    for key in ('batch_id','candidate_id','attempt_id','step_id'):label(value[key])
    require(value['task_id']=='val-owner'and value['language']in('zh','en'),'FIXTURE_USE_TASK')


def policy(raw,producer,observer,consumer,pins):
    value=decode(raw)
    require(type(value)is dict and set(value)==POLICY_FIELDS and value['version']==VERSION,
            'FIXTURE_REGISTRY_FIELDS')
    for key in ('registry_id','fixture_id'):label(value[key])
    require(type(value['fixture_revision'])is int and value['fixture_revision']>0,
            'FIXTURE_REGISTRY_REVISION')
    require(value['producer_binding_sha256']==producer.key and producer==observer
        and value['consumer_binding_sha256']==consumer.key and producer.scope!=consumer.scope,
        'FIXTURE_ORIGINAL_BINDINGS')
    require(value['consumer_pins_sha256']==pins.key,'FIXTURE_CONSUMER_PINS')
    baseline=value['baseline']
    require(type(baseline)is dict and set(baseline)=={'trip_id_sha256','trip_version','content_sha256'},
            'FIXTURE_BASELINE_FIELDS')
    hash256(baseline['trip_id_sha256']);hash256(baseline['content_sha256'])
    require(type(baseline['trip_version'])is int and baseline['trip_version']>0,'FIXTURE_BASELINE_VERSION')
    for key in ('consumer_registration_ref','experiment_ref','public_release_ref'):origin(value[key])
    for key in ('batch_ids','candidate_ids','languages'):
        items=value[key]
        require(type(items)is list and 0<len(items)<=100 and all(type(x)is str for x in items)
            and len(set(items))==len(items),'FIXTURE_ALLOWED_CONSUMERS')
        for item in items:label(item)
    require(set(value['languages'])<= {'zh','en'},'FIXTURE_LANGUAGE')
    require(timestamp(value['valid_from'])<timestamp(value['valid_until']),'FIXTURE_REGISTRY_INTERVAL')
    require(type(value['maximum_uses'])is int and 1<=value['maximum_uses']<=100,'FIXTURE_MAXIMUM_USES')
    require(encode(value)==raw,'FIXTURE_POLICY_CANONICAL_BYTES')
    return value


class FixtureUseRegistry:
    def __init__(self,directory,policy_file,producer,observer,consumer,pins,*,guard,source_guard,
                 admission_lock,clock,preparation_guard=None):
        self.directory,self.policy_file=Path(directory),Path(policy_file)
        self.producer=producer
        self.consumer,self.pins=consumer,pins
        self.guard,self.source_guard,self.admission_lock,self.clock=guard,source_guard,admission_lock,clock
        self.preparation_guard=preparation_guard
        self.raw=read_private(self.policy_file,65536)
        self.policy=policy(self.raw,producer,observer,consumer,pins)
        self.policy_sha256=sha256(self.raw).hexdigest()
        with self._directory()as directory:
            info=os.fstat(directory);self.identity=(info.st_dev,info.st_ino)

    def _directory(self):
        return private_directory(self.directory,Unavailable('FIXTURE_RESERVATION_DIRECTORY_AUTHORITY'))

    def _policy_current(self,read_only):
        self.guard(read_only=read_only)
        if read_private(self.policy_file,65536)!=self.raw:
            raise Unavailable('FIXTURE_REGISTRY_POLICY_CHANGED')
        now=self.clock()
        if now.tzinfo is None or not timestamp(self.policy['valid_from'])<=now<timestamp(self.policy['valid_until']):
            raise Unavailable('FIXTURE_REGISTRY_EXPIRED')

    def _current(self,read_only):
        self._policy_current(read_only)
        definition=self.source_guard()
        origin(definition)
        return {'ref':definition['ref'],'sha256':definition['sha256']}

    def preparation_policy_source(self):
        """Read the approved header before a definition exists; grants no use.

        The host supplies current producer/observer qualification independently
        of the final definition. Reservations still require source_guard.
        """
        if self.preparation_guard is None:
            raise Unavailable('FIXTURE_PREPARATION_READER_NOT_CONNECTED')
        self._policy_current(read_only=True)
        self.preparation_guard()
        self._policy_current(read_only=True)
        self.preparation_guard()
        return self.raw

    def _use(self,raw):
        value=decode(raw)
        use_fields(value)
        require(encode(value)==raw,'FIXTURE_USE_CANONICAL_BYTES')
        require(value['binding_sha256']==self.consumer.key and value['pins_sha256']==self.pins.key,
                'FIXTURE_USE_ORIGINAL_BINDING')
        require(value['task_id']=='val-owner' and value['language']in self.policy['languages']
            and value['batch_id']in self.policy['batch_ids'] and value['candidate_id']in self.policy['candidate_ids'],
            'FIXTURE_USE_NOT_REGISTERED')
        return value

    def _name(self,use):
        # Stable across session/pin changes: those cannot create a second slot
        # for the same original consumer attempt/step.
        return digest([self.consumer.scope,self.consumer.ledger_id,self.consumer.producer_id,
            use['attempt_id'],use['step_id']])+'.json'

    def _records(self,directory):
        info=os.fstat(directory)
        if (info.st_dev,info.st_ino)!=self.identity:raise Unavailable('FIXTURE_RESERVATION_DIRECTORY_CHANGED')
        records={}
        for name in os.listdir(directory):
            if re.fullmatch('[a-f0-9]{64}[.]json',name)is None:
                raise Unavailable('FIXTURE_RESERVATION_UNRESOLVED')
            try:raw=read_private(name,65536,directory_fd=directory)
            except (PrivateFileError,OSError):raise Unavailable('FIXTURE_RESERVATION_UNRESOLVED')from None
            try:record=decode(raw)
            except ValueError:raise Unavailable('FIXTURE_RESERVATION_UNRESOLVED')from None
            require(type(record)is dict and set(record)=={'version','policy_sha256','definition_ref','use','ordinal','reserved_at'},
                    'FIXTURE_RESERVATION_FIELDS')
            origin(record['definition_ref'])
            hash256(record['policy_sha256']);use_fields(record['use']);timestamp(record['reserved_at'])
            require(record['version']==VERSION
                and type(record['ordinal'])is int and record['ordinal']>0
                and self._name(record['use'])==name and encode(record)==raw,'FIXTURE_RESERVATION_INTEGRITY')
            records[name]=record
        selected=[r for r in records.values()if r['policy_sha256']==self.policy_sha256]
        if sorted(x['ordinal']for x in selected)!=list(range(1,len(selected)+1)):
            raise Unavailable('FIXTURE_RESERVATION_SEQUENCE_UNRESOLVED')
        return records

    def reserve(self,raw):
        use=self._use(raw);name=self._name(use)
        # The host must supply the same native consumer MESSAGE admission lock
        # as canonical claims, not an unrelated experiment/file lock.
        with self.admission_lock():
            definition=self._current(read_only=False)
            with self._directory()as directory:
                records=self._records(directory)
                if name in records:
                    if records[name]['policy_sha256']!=self.policy_sha256:
                        raise Unavailable('FIXTURE_ORIGINAL_USE_POLICY_CHANGED')
                    if records[name]['definition_ref']!=definition:
                        raise Unavailable('FIXTURE_ORIGINAL_DEFINITION_CHANGED')
                    require(records[name]['use']==use,'FIXTURE_ORIGINAL_USE_CHANGED')
                    result=records[name]
                else:
                    count=sum(r['policy_sha256']==self.policy_sha256 for r in records.values())
                    if count>=self.policy['maximum_uses']:raise Unavailable('FIXTURE_USE_LIMIT_REACHED')
                    result=dict(version=VERSION,policy_sha256=self.policy_sha256,definition_ref=definition,use=use,
                        ordinal=count+1,reserved_at=self.clock().isoformat())
                    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
                    with os.fdopen(fd,'wb')as output:output.write(encode(result));output.flush();os.fsync(output.fileno())
                    os.fsync(directory)
            if self._current(read_only=False)!=definition:
                raise Unavailable('FIXTURE_ORIGINAL_DEFINITION_CHANGED')
            return result

    def read(self,raw):
        use=self._use(raw);definition=self._current(read_only=True)
        with self._directory()as directory:
            records=self._records(directory);record=records.get(self._name(use))
        if record is None:raise Unavailable('FIXTURE_ORIGINAL_RESERVATION_UNAVAILABLE')
        if record['policy_sha256']!=self.policy_sha256:
            raise Unavailable('FIXTURE_ORIGINAL_USE_POLICY_CHANGED')
        if record['definition_ref']!=definition:raise Unavailable('FIXTURE_ORIGINAL_DEFINITION_CHANGED')
        require(record['use']==use,'FIXTURE_ORIGINAL_USE_CHANGED')
        if self._current(read_only=True)!=definition:raise Unavailable('FIXTURE_ORIGINAL_DEFINITION_CHANGED')
        return record

    def policy_source(self):
        """Original canonical B policy bytes, under current read qualification."""
        definition=self._current(read_only=True)
        if self._current(read_only=True)!=definition:
            raise Unavailable('FIXTURE_ORIGINAL_DEFINITION_CHANGED')
        return self.raw

    def reservation_identity(self,raw):
        record=self.read(raw)
        return self._name(record['use']).removesuffix('.json')

    def original_use(self,use_sha256):
        """Locate a retained use, never reconstruct one from reader assertions."""
        hash256(use_sha256);self._current(read_only=True)
        with self._directory()as directory:records=self._records(directory)
        selected=[encode(r['use'])for r in records.values()
            if r['policy_sha256']==self.policy_sha256 and sha256(encode(r['use'])).hexdigest()==use_sha256]
        if len(selected)!=1:raise Unavailable('FIXTURE_ORIGINAL_USE_UNAVAILABLE')
        self.read(selected[0])
        return selected[0]
