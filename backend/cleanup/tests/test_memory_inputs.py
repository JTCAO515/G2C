import json,unittest
from cj_cleanup.memory_inputs import consumes_sources,PREFIX,EDIT_PREFIX
from cj_cleanup.core import Denied


class OriginalMemoryInputChecks(unittest.TestCase):
    def memory(self,source='original-source',text='same words'):
        item=dict(subject='self',slot='diet',text=text,kind='preference',extent='long_term',
                  source_id=source,source_version=1,version=1)
        return dict(role='user',content=PREFIX+json.dumps(dict(version='MEMORY-RUN-CONSUME@1',items=[item])))

    def raw(self,messages):return json.dumps(dict(messages=messages,system=None)).encode()
    def match(self,messages,text='current instruction'):
        return consumes_sources(self.raw(messages),text,[dict(source_id='original-source',source_version=1)])

    def test_exact_reserved_memory_slot_and_source_version_not_text(self):
        current=dict(role='user',content='current instruction')
        self.assertTrue(self.match([self.memory(),current]))
        self.assertTrue(self.match([dict(role='system',content=EDIT_PREFIX+'quoted source'),self.memory(),current]))
        self.assertFalse(self.match([self.memory('explicit-new-source'),current]))
        with self.assertRaises(Denied):self.match([self.memory(),dict(role='user',content='different original')])

    def test_user_quote_or_foreign_role_cannot_masquerade_as_memory_lineage(self):
        quoted=self.memory()['content']
        self.assertFalse(self.match([dict(role='user',content=quoted)],text=quoted))
        empty=dict(role='user',content=PREFIX+json.dumps(dict(version='MEMORY-RUN-CONSUME@1',items=[])))
        self.assertFalse(self.match([empty,dict(role='user',content=quoted)],text=quoted))
        self.assertFalse(self.match([dict(self.memory(),role='tool'),dict(role='user',content='current instruction')]))


if __name__=='__main__':unittest.main()
