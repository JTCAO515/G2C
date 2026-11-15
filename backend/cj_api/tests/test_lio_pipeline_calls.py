from types import SimpleNamespace
import unittest

from cj_api.local_lio_pipeline_calls import Call,PipelineCalls,PipelineCapacity


class PipelineCallsTests(unittest.TestCase):
    def worker(self,*,fail=None):
        trace=[]
        def stream(binding,key,registration,argument,**kw):
            try:
                trace.append(('send',argument,key));yield ''
                trace.append(('receive',argument,key))
                if argument==fail:raise OSError('original outcome unknown')
                yield str(argument)
            finally:trace.append(('close',argument,key))
        return SimpleNamespace(_registered_stream=stream),trace

    def test_every_send_precedes_response_drain_without_threads_or_extra_attempts(self):
        worker,trace=self.worker();calls=PipelineCalls(worker,'actual-binding')
        result=calls.parallel(tuple(Call('gaode','registered-test',n)for n in range(3)))
        self.assertEqual(result,('0','1','2'))
        self.assertEqual([row[:2]for row in trace[:3]],[('send',0),('send',1),('send',2)])
        self.assertEqual(sum(row[0]=='send'for row in trace),3)
        self.assertEqual(sum(row[0]=='close'for row in trace),3)

    def test_complete_fanout_is_refused_before_dispatch_at_six_models_or_45_tools(self):
        worker,trace=self.worker();calls=PipelineCalls(worker,'actual-binding')
        calls.parallel(tuple(Call('model','registered-test',n)for n in range(5)))
        before=list(trace)
        with self.assertRaises(PipelineCapacity):calls.parallel((Call('model','registered-test',99),))
        self.assertEqual(trace,before)
        calls.parallel(tuple(Call('gaode','registered-test',n)for n in range(45)))
        before=list(trace)
        with self.assertRaises(PipelineCapacity):calls.parallel((Call('gaode','registered-test',99),))
        self.assertEqual(trace,before)

    def test_unknown_preserves_original_failure_closes_all_and_never_refunds_or_retries(self):
        worker,trace=self.worker(fail=1);calls=PipelineCalls(worker,'actual-binding')
        with self.assertRaisesRegex(OSError,'original outcome unknown'):
            calls.parallel(tuple(Call('gaode','registered-test',n)for n in range(3)))
        self.assertEqual(calls.gaode,3)
        self.assertEqual(sum(row[0]=='send'for row in trace),3)
        self.assertEqual(sum(row[0]=='close'for row in trace),3)
        self.assertEqual({row[2]for row in trace if row[0]=='send'},
                         {'lio4.pipeline.0','lio4.pipeline.1','lio4.pipeline.2'})


if __name__=='__main__':unittest.main()
