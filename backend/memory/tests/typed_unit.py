"""Typed grammar only: these selectors/objects never grant source or owner rights."""
import json
import unittest
from cj_memory.domain import Command, InvalidInput
from cj_memory.typed import ContextRef, parse_manual, parse_stored


def raw(**changes):
    value=dict(version='MEMORY-manual.2',operation_id='op',item_id='item',subject='self',slot='pace',
               kind='preference',text='Original 新原文',extent='current',
               context=dict(kind='travel',id='a'*32,expected_version=1),occurred_at='unknown date')
    value.update(changes)
    return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()


class TypedGrammar(unittest.TestCase):
    def test_current_and_longterm_preserve_source_bytes_and_scope(self):
        value=parse_manual(raw());self.assertEqual(value.context_kind,'travel')
        self.assertEqual(value.context_id,'a'*32);self.assertEqual(value.context_version,1)
        self.assertEqual(value.text,'Original 新原文');self.assertEqual(parse_stored(value.raw),value)
        with self.assertRaises(InvalidInput):Command.parse(value.raw)
        long=parse_manual(raw(extent='long_term',context=None))
        self.assertEqual((long.context_kind,long.context_id,long.context_version),('legacy',None,None))
        self.assertNotEqual(ContextRef('legacy','a'*32),ContextRef('travel','a'*32))

    def test_no_caller_authority_or_ambiguous_context(self):
        for changes in (dict(context=None),dict(context={'kind':'legacy','id':'a','expected_version':1}),
                        dict(context={'kind':'travel','id':'a','expected_version':True}),
                        dict(context={'kind':'travel','id':'a','expected_version':0}),
                        dict(extent='long_term'),dict(source_id='caller'),dict(owner='alice'),dict(version='unknown')):
            with self.subTest(changes=changes),self.assertRaises(InvalidInput):parse_manual(raw(**changes))
        value=raw()
        with self.assertRaises(InvalidInput):parse_manual(value[:-1]+b',"slot":"duplicate"}')


if __name__=='__main__':unittest.main(verbosity=2)
