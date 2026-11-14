"""Private capture lifetime and exact native completion; fixtures are not HK proof."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,os,unittest
from cj_run.core import Binding
from cj_usage.core import Command,Attempt,Receipt
from cj_api.rejected_intake_capture import (RejectedIntakeSink,CaptureUnavailable,TTL_SECONDS,
    capture_rejected_intake,use_rejected_intake_sink,observe_complete,acknowledge_settlement)


class RejectedCapture(unittest.TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)
        self.now=1000000;self.sink=RejectedIntakeSink(self.root,clock=lambda:self.now)
        self.binding=Binding('owner','chat','gen','mid','run',1)
        self.command=Command('attempt','operation','run','model','a'*64,1,12000)
        self.operation=SimpleNamespace(binding=self.binding,command=self.command,
            registration_id='model.lio_intake.9',operation_key='model.lio_intake.0')
        self.raw=b'{"invalid":true}'
        self.metadata=dict(receipt_sha256='b'*64,model_id='qwen3.8-flash',input_utf8='DO_NOT_COPY_INPUT',headers='DO_NOT_COPY_HEADERS')
        self.attempt=Attempt(self.command,'settled',Receipt('attempt','live:'+'b'*64,'provider_call',1,len(self.raw)))
        self.allowed=True;self.checks=0;self.fail_at=None;self.fail_exit=False

    def check(self):
        self.checks+=1
        if not self.allowed or self.checks==self.fail_at:raise CaptureUnavailable('original source revoked')

    @contextmanager
    def lifetime(self):
        yield self.check
        if self.fail_exit:raise CaptureUnavailable('original source close revoked')

    def observed(self,*,ack=True,attempt=None):
        observe_complete(self.operation,self.raw,self.metadata,self.lifetime)
        if ack:acknowledge_settlement(self.operation,attempt or self.attempt)

    def test_exact_confirmed_rejection_is_private_and_retained_after_context(self):
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed();receipt=capture.reject('field_source_binding',self.raw)
            self.assertEqual(capture.reject('field_source_binding',self.raw),receipt)
        self.assertEqual(receipt.status,'CAPTURED');self.assertEqual(capture.result,receipt)
        self.assertIsNone(capture.observed);self.assertIsNone(capture.settled)
        files=list(self.root.iterdir());self.assertEqual(len(files),1)
        self.assertEqual(files[0].stat().st_mode&0o777,0o600)
        stored=json.loads(files[0].read_bytes());self.assertEqual(stored['result_utf8'].encode(),self.raw)
        self.assertNotIn('DO_NOT_COPY_INPUT',files[0].read_text());self.assertNotIn('DO_NOT_COPY_HEADERS',files[0].read_text())
        with self.assertRaises(CaptureUnavailable):capture.reject('field_source_binding',self.raw)

    def test_success_and_normal_clarification_do_not_persist_and_drop_ram(self):
        for _ in range(2):
            with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
                self.observed()
            self.assertIsNone(capture.observed);self.assertEqual(list(self.root.iterdir()),[])

    def test_transport_or_settlement_unknown_has_no_capture_or_replay(self):
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed(ack=False)
            receipt=capture.reject('invalid_model_intake',self.raw)
            self.assertEqual(receipt.status,'NOT_CAPTURED')
        self.assertEqual(list(self.root.iterdir()),[])

    def test_read_holder_only_comes_from_live_confirmed_producer(self):
        from cj_api.rejected_intake_capture import OriginalIntakeReadLifetime
        with capture_rejected_intake(self.binding,check_running=self.check)as empty:
            with self.assertRaises(CaptureUnavailable):empty.read_lifetime()
            with self.assertRaises(CaptureUnavailable):OriginalIntakeReadLifetime(empty,_factory=object())
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed();holder=capture.read_lifetime()
        with self.assertRaises(CaptureUnavailable):
            with holder.hold(SimpleNamespace(scope='owner'),self.binding,'operation','a'*64,None):pass

    def test_wrong_binding_and_mismatched_output_are_refused(self):
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            wrong=SimpleNamespace(**dict(vars(self.operation),binding=replace(self.binding,run_id='foreign')))
            with self.assertRaises(CaptureUnavailable):observe_complete(wrong,self.raw,self.metadata,self.lifetime)
            self.observed()
            with self.assertRaises(CaptureUnavailable):capture.reject('invalid_model_intake',b'fabricated')
        self.assertEqual(list(self.root.iterdir()),[])

    def test_bad_cancelled_or_exceeded_native_ack_is_not_confirmation(self):
        for attempt in (replace(self.attempt,state='unknown',receipt=None),replace(self.attempt,cancelled=True),
                        replace(self.attempt,exceeded=True),replace(self.attempt,receipt=replace(self.attempt.receipt,receipt_id='wrong'))):
            with self.subTest(attempt=attempt),use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check):
                with self.assertRaises(CaptureUnavailable):self.observed(attempt=attempt)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_source_revocation_at_write_removes_unconfirmed_bytes(self):
        self.fail_at=4
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed()
            with self.assertRaises(CaptureUnavailable):capture.reject('invalid_model_intake',self.raw)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_source_close_failure_removes_new_file_but_not_prior_confirmation(self):
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed();self.fail_exit=True
            with self.assertRaises(CaptureUnavailable):capture.reject('invalid_model_intake',self.raw)
        self.assertEqual(list(self.root.iterdir()),[])
        self.fail_exit=False
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed();receipt=capture.reject('invalid_model_intake',self.raw);self.allowed=False
            with self.assertRaises(CaptureUnavailable):capture.reject('invalid_model_intake',self.raw)
        self.assertEqual(capture.result,receipt);self.assertEqual(len(list(self.root.iterdir())),1)

    def test_seven_day_expiry_and_corruption_are_not_silent_deletion(self):
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed();capture.reject('invalid_model_intake',self.raw)
        self.now+=TTL_SECONDS-1;self.sink.prune();self.assertEqual(len(list(self.root.iterdir())),1)
        self.now+=1;self.sink.prune();self.assertEqual(list(self.root.iterdir()),[])
        (self.root/('a'*64+'.json')).write_text('{}');(self.root/('a'*64+'.json')).chmod(0o600)
        self.now+=60
        self.sink.prune()  # A corrupt record is reported, not allowed to block all GC.
        with self.assertRaises(CaptureUnavailable):self.sink.read('a'*64)

    def test_public_directory_nested_scope_and_symlink_are_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(CaptureUnavailable):RejectedIntakeSink(self.root)
        self.root.chmod(0o700)
        with capture_rejected_intake(self.binding,check_running=self.check):
            with self.assertRaises(CaptureUnavailable):
                with capture_rejected_intake(self.binding,check_running=self.check):pass
        other=self.root/'target';other.write_text('private');other.chmod(0o600)
        link=self.root/'link';link.symlink_to(other)
        with self.assertRaises((CaptureUnavailable,OSError)):RejectedIntakeSink(link)




    def test_broken_first_does_not_block_expired_complete_records(self):
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed();receipt=capture.reject('invalid_model_intake',self.raw)
        broken='a'*64+'.json';(self.root/broken).write_text('{partial');(self.root/broken).chmod(0o600)
        os.utime(self.root/broken,(self.now,self.now))
        expired=receipt.reference+'.json';self.now+=TTL_SECONDS+1
        with patch('cj_api.rejected_intake_capture.os.listdir',return_value=[broken,expired]):
            RejectedIntakeSink(self.root,clock=lambda:self.now).prune()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_abandoned_partial_is_bounded_and_unpublished(self):
        name='.'+'a'*64+'.'+'b'*32+'.tmp';path=self.root/name;path.write_bytes(b'partial');path.chmod(0o600)
        os.utime(path,(self.now-61,self.now-61));self.sink.prune()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_final_reference_never_overwrites_prior_file(self):
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed();receipt=capture.reject('invalid_model_intake',self.raw)
        old=(self.root/(receipt.reference+'.json')).read_bytes()
        with use_rejected_intake_sink(self.sink),capture_rejected_intake(self.binding,check_running=self.check)as capture:
            self.observed()
            with self.assertRaises(FileExistsError):capture.reject('invalid_model_intake',self.raw)
        self.assertEqual((self.root/(receipt.reference+'.json')).read_bytes(),old)
        self.assertEqual(len(list(self.root.iterdir())),1)


if __name__=='__main__':unittest.main()
