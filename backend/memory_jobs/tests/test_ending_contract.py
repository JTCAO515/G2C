"""Explicit new ending grammar; no end authority or legacy parse fallback."""
import json,unittest
from cj_memory_jobs.ending import EndingCommand
from cj_memory_jobs.consent import EnqueueCommand
from cj_memory_jobs.codec import InvalidInput


class EndingContract(unittest.TestCase):
    def setUp(self):
        self.value=dict(version='MEMORY-END-JOBS@1',job_id='job',attempt_id='attempt',
            source=dict(conversation_id='chat',generation='generation',epoch=0,after=0,through=100,
                source_version=1,withdrawal_epoch=1,mode='conversation_end'),
            end=dict(conversation_id='chat',generation='generation',epoch=0,through=101))

    def test_segment_preserves_full_head_and_exact_original(self):
        raw=json.dumps(self.value).encode()+b'\n'
        command=EndingCommand.parse(raw)
        self.assertEqual((command.query.through,command.segment.end.through),(100,101))
        self.assertEqual(command.raw,raw)
        with self.assertRaises(InvalidInput):EnqueueCommand.parse(raw)

    def test_no_legacy_or_invented_head_widening(self):
        changes=[dict(version='MEMORY-JOBS@1'),dict(end=dict(self.value['end'],through=99)),
            dict(end=dict(self.value['end'],conversation_id='other')),
            dict(end=dict(self.value['end'],epoch=True)),
            dict(source=dict(self.value['source'],mode='incremental')),
            dict(source=dict(self.value['source'],through=101)),dict(owner='alice')]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(InvalidInput):
                EndingCommand.parse(json.dumps(dict(self.value,**change)).encode())
        for raw in (b'{}',b'[]',b'{"version":"MEMORY-END-JOBS@1","version":"MEMORY-END-JOBS@1"}',b'x'*32769):
            with self.subTest(raw=raw[:30]),self.assertRaises(InvalidInput):EndingCommand.parse(raw)
