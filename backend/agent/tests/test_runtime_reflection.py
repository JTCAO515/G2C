"""Worker routing controls; actual Meter/wire integration is separate evidence."""
from test_worker_cancel import fixture,CancelsDuringAnswer


class ReflectionExit:
    def __init__(self):self.prepared=[];self.sent=0;self.stopped=[]
    def for_run(self,binding,state):return self
    def prepare_operation(self,runs,binding,key,registration,payload,*,stage):
        self.prepared.append((binding,key,registration,payload))
        return object()
    def stream(self,prepared):
        self.sent+=1
        yield '{"prompt.answer_style":"Short and useful."}'
    def stop(self,binding):self.stopped.append(binding)


class NoMemory:
    def capture(self,*args):raise AssertionError('reflection may not read Memory')


class NoTools:
    def answer(self,*args,**kwargs):raise AssertionError('reflection may not execute tools')


def test_reflection_is_one_original_registered_operation_without_memory_or_writes():
    worker,runs,binding,provider,drafts=fixture(CancelsDuringAnswer)
    original=ReflectionExit();worker.budget_exit=original
    payload={'components':['prompt.answer_style'],'candidate':{'prompt.answer_style':'original'}}
    worker.runtime_reflection=lambda actual:payload if actual==binding else None
    worker.memory=NoMemory();worker.tools=NoTools()
    outcome,=worker.process()
    assert outcome.status=='completed'
    assert original.sent==1 and len(original.prepared)==1
    actual,key,registration,seen=original.prepared[0]
    assert actual==binding and key=='model.runtime_reflection.0' and registration=='model.runtime_reflection.1'
    assert seen is payload and provider.calls==drafts.calls==0
    assert runs.snapshot(binding).effects==()
    assert runs.snapshot(binding).text=='{"prompt.answer_style":"Short and useful."}'
    # A lost delivery ACK returns the terminal original, never a second model.
    worker.messages.acknowledged.clear()
    assert worker.process()[0].status=='completed'
    assert original.sent==1


def test_reflection_cannot_smuggle_a_publication_intent():
    worker,runs,binding,provider,drafts=fixture(CancelsDuringAnswer,'consider_trip')
    original=ReflectionExit();worker.budget_exit=original
    worker.runtime_reflection=lambda actual:{'candidate':'synthetic'}
    outcome,=worker.process()
    assert outcome.status=='unknown'
    assert not original.prepared and original.sent==provider.calls==drafts.calls==0
    assert runs.snapshot(binding).effects==()


def test_reflection_cancellation_keeps_original_partial_and_never_replays():
    worker,runs,binding,provider,drafts=fixture(CancelsDuringAnswer)
    class CancelReflection(ReflectionExit):
        def stream(self,prepared):
            self.sent+=1
            yield 'original partial reflection'
            runs.cancel(binding)
            yield 'late reflection must not publish'
    original=CancelReflection();worker.budget_exit=original
    worker.runtime_reflection=lambda actual:{'candidate':'synthetic'}
    assert worker.process()[0].status=='cancelled'
    assert runs.snapshot(binding).text=='original partial reflection'
    worker.messages.acknowledged.clear()
    assert worker.process()[0].status=='cancelled'
    assert original.sent==1 and provider.calls==drafts.calls==0
