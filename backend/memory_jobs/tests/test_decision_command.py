import json,unittest
from cj_memory_jobs.decision_command import DecisionCommand,VERSION
from cj_memory_jobs.codec import InvalidInput


class DecisionCommandTests(unittest.TestCase):
    def value(self):
        return dict(version=VERSION,job_id='任务-id',attempt_id='原-attempt',source=dict(conversation_id='chat',generation='gen',
            epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental'),
            decision=dict(trip_id='trip-original',expected_version=2,content_sha256='a'*64),end=None)

    def test_original_utf8_and_segmented_end_comparisons_are_data_only(self):
        value=self.value();raw=json.dumps(value,ensure_ascii=False,indent=2).encode()+b'\n'
        command=DecisionCommand.parse(raw)
        self.assertEqual(command.raw,raw);self.assertEqual(command.job_id,'任务-id')
        self.assertEqual(command.query,command.reader_query)
        value['source'].update(mode='conversation_end',after=100,through=101)
        value['end']=dict(conversation_id='chat',generation='gen',epoch=0,through=101)
        command=DecisionCommand.parse(json.dumps(value).encode())
        self.assertEqual((command.query.mode,command.reader_query.mode,command.reader_query.after,command.end.through),
            ('conversation_end','incremental',100,101))

    def test_implicit_or_forged_authority_and_original_versions_refuse(self):
        for change in ('owner','legacy','hash','bool','end','wrong_head'):
            with self.subTest(change=change):
                value=self.value()
                if change=='owner':value['owner']='someone'
                elif change=='legacy':value['version']='MEMORY-JOBS@1'
                elif change=='hash':value['decision']['content_sha256']='a'*63
                elif change=='bool':value['decision']['expected_version']=True
                elif change=='end':value['source']['mode']='conversation_end'
                else:
                    value['source']['mode']='conversation_end'
                    value['end']=dict(conversation_id='other',generation='gen',epoch=0,through=1)
                with self.assertRaises(InvalidInput):DecisionCommand.parse(json.dumps(value).encode())
        raw=json.dumps(self.value()).encode()
        with self.assertRaises(InvalidInput):DecisionCommand.parse(raw[:-1]+b',"end":null}')
        with self.assertRaises(InvalidInput):DecisionCommand.parse(b' '*32769)


if __name__=='__main__':unittest.main()
