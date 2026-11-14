"""Retained, at-most-once exact classification of one reserved native use.

An intent without a complete result is query-only UNKNOWN. Neither this private
journal nor a filesystem write is the final cross-binding publication witness.
"""
from hashlib import sha256
import os
from pathlib import Path

from runtime_adapter.contract import decode,encode,hash256,require,Unavailable
from .runtime_disclosure_scan import VERSION as SCAN_VERSION
from .runtime_private import private_directory,read_private,PrivateFileError


VERSION='G2C-fixture-scan-journal.1'


class FixtureScanJournal:
    def __init__(self,directory,registry,collector,scanner):
        self.directory,self.registry,self.collector,self.scanner=Path(directory),registry,collector,scanner
        with self._directory()as fd:
            info=os.fstat(fd);self.identity=(info.st_dev,info.st_ino)

    def _directory(self):
        return private_directory(self.directory,Unavailable('SCAN_JOURNAL_DIRECTORY_AUTHORITY'))

    def _identity(self,fd):
        info=os.fstat(fd)
        if(info.st_dev,info.st_ino)!=self.identity:raise Unavailable('SCAN_JOURNAL_DIRECTORY_CHANGED')

    def _original(self,use,deadline):
        reservation=self.registry.read(use)
        value=reservation['use']
        request=self.collector.original_request(value['step_id'],deadline=deadline)
        original=decode(request)
        require(sha256(request).hexdigest()==value['request_sha256']
            and original['attempt_id']==value['attempt_id']and original['step_id']==value['step_id']
            and original['binding_sha256']==value['binding_sha256']
            and original['pins_sha256']==value['pins_sha256']
            and original['kind']in('message','new_conversation_message'),'SCAN_ORIGINAL_REQUEST_BINDING')
        intent=encode(dict(version=VERSION,use_sha256=sha256(use).hexdigest(),
            reservation_sha256=sha256(encode(reservation)).hexdigest(),
            request_sha256=sha256(request).hexdigest(),message_id=value['step_id'],
            source_state_sha256=sha256(self.scanner.expected).hexdigest(),
            sentinel_set_sha256=self.scanner.sentinel_sha256))
        return self.registry.reservation_identity(use),intent

    @staticmethod
    def _write(fd,name,raw):
        out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(out,'wb')as target:
            target.write(raw);target.flush();os.fsync(target.fileno())
        os.fsync(fd)

    def scan_once(self,use,*,deadline):
        key,intent=self._original(use,deadline)
        with self._directory()as fd:
            self._identity(fd)
            try:self._write(fd,key+'.intent',intent)
            except FileExistsError:return self.read(use,deadline=deadline)
        # The durable intent is never removed, including source/ACK failures.
        # Do not hold either owner's native locks over the whole classification.
        report=self.scanner.scan(decode(intent)['message_id'],deadline=deadline)
        record=encode(dict(version=VERSION,intent_sha256=sha256(intent).hexdigest(),report=decode(report)))
        with self._directory()as fd:
            self._identity(fd);self._write(fd,key+'.result',record)
        return self.read(use,deadline=deadline)

    def read(self,use,*,deadline):
        key,intent=self._original(use,deadline)
        with self._directory()as fd:
            self._identity(fd)
            try:
                saved=read_private(key+'.intent',65536,directory_fd=fd)
                raw=read_private(key+'.result',1048576,directory_fd=fd)
            except(FileNotFoundError,PrivateFileError):
                raise Unavailable('ORIGINAL_SCAN_UNRESOLVED_QUERY_ONLY')from None
        if saved!=intent:raise Unavailable('ORIGINAL_SCAN_BINDING_CHANGED')
        record=decode(raw)
        require(type(record)is dict and set(record)=={'version','intent_sha256','report'}
            and record['version']==VERSION and record['intent_sha256']==sha256(intent).hexdigest()
            and encode(record)==raw,'ORIGINAL_SCAN_RESULT_INTEGRITY')
        report=record['report'];binding=decode(intent);mid=binding['message_id']
        require(type(report)is dict and report.get('version')==SCAN_VERSION
            and report.get('message_id')==mid
            and report.get('source_state_sha256')==binding['source_state_sha256']
            and report.get('private_sentinel_set_sha256')==binding['sentinel_set_sha256']
            and report.get('exact_status')in('PASS','FAIL','UNKNOWN'),'ORIGINAL_SCAN_REPORT_BINDING')
        hash256(report['consumer_surface_inventory_sha256'])
        # Re-read evidence and qualification; never classify it again. Read E
        # before C holders, preserving the native MESSAGE/source lock order.
        surface=self.scanner.surfaces.collect(mid)
        if sha256(surface).hexdigest()!=report['consumer_surface_inventory_sha256']:
            raise Unavailable('ORIGINAL_SCAN_SURFACES_CHANGED')
        result=self.scanner.producer.with_current(self.scanner.expected,
            lambda state,private:encode(report),deadline=deadline)
        if self._original(use,deadline)!=(key,intent):raise Unavailable('ORIGINAL_SCAN_BINDING_CHANGED')
        if self.scanner.surfaces.collect(mid)!=surface:raise Unavailable('ORIGINAL_SCAN_SURFACES_CHANGED')
        return result
