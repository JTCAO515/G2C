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




class EditRuntimePolicy(unittest.TestCase):
    def document(self):
        from datetime import datetime,timedelta,timezone
        profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
                     extents=['long_term','current'],context_ids=[])
        return dict(version='local-memory-edit-run.1',collection=dict(version='local-memory-typed.1',
            collection=dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                profiles={'alice':profile}),travel_contexts={'alice':[]}),
            selections={'alice':dict(subject='self',slots=['pace'],max_bytes=2048)})

    def test_explicit_new_policy_and_old_versions_stay_separate(self):
        from cj_memory.edit_runtime import EditRuntimeConfiguration
        from cj_memory.typed_runtime import TypedRuntimeConfiguration
        from cj_memory.typed import packed
        value=self.document();new=EditRuntimeConfiguration.from_bytes(packed(value))
        self.assertEqual(new.abi,'CJ-MESSAGE-EDIT-MEMORY@1')
        self.assertEqual(new.selections['alice'].max_bytes,2048)
        with self.assertRaises(InvalidInput):TypedRuntimeConfiguration.from_bytes(packed(value))
        value['version']='local-memory-run.2'
        with self.assertRaises(InvalidInput):EditRuntimeConfiguration.from_bytes(packed(value))
        self.assertIsInstance(TypedRuntimeConfiguration.from_bytes(packed(value)),TypedRuntimeConfiguration)

    def test_policy_bounds_duplicates_and_missing_dependencies_fail_closed(self):
        from cj_memory.edit_runtime import EditRuntimeConfiguration
        from cj_memory.typed import packed
        for kind in ('slots','bytes','identity','extra'):
            value=self.document()
            if kind=='slots':value['selections']['alice']['slots']=['unknown']
            elif kind=='bytes':value['selections']['alice']['max_bytes']=0
            elif kind=='identity':value['selections']['stranger']=value['selections'].pop('alice')
            else:value['abi']='caller'
            with self.subTest(kind=kind),self.assertRaises(ValueError):EditRuntimeConfiguration.from_bytes(packed(value))
        raw=packed(self.document())
        with self.assertRaises(InvalidInput):EditRuntimeConfiguration.from_bytes(raw[:-1]+b',"version":"local-memory-edit-run.1"}')
        from cj_memory.runtime import RuntimeDenied
        with self.assertRaises(RuntimeDenied):EditRuntimeConfiguration.from_bytes(raw).bind(None,'owner','alice',None,message_context=None)


if __name__=='__main__':unittest.main(verbosity=2)
