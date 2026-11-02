"""L0 canonical command preparation only; not a Memory write/model acceptance."""
from dataclasses import replace
import unittest

from cj_memory.typed import parse_stored
from cj_message.travel import Selection
from cj_memory_jobs.extraction import CollectionUnavailable,Entry,Evidence
from cj_memory_jobs.publication import build_command
from test_extraction_boundary import source_message


class PublicationCommands(unittest.TestCase):
    def setUp(self):
        self.messages=(source_message('不吃辣'),)
        self.entry=Entry('self','diet.spicy','preference','不吃辣','long_term','date unknown',
                         (Evidence('m1','不吃辣'),))

    def test_prepared_command_uses_existing_canonical_typed_decoder(self):
        command=build_command('scope-a',self.entry,self.messages,None)
        self.assertEqual(parse_stored(command.raw),command)
        self.assertEqual((command.context_kind,command.context_id,command.context_version),('legacy',None,None))
        self.assertEqual(command.text,'不吃辣')
        self.assertTrue(command.source_id.startswith('history-v1:'))

    def test_current_scope_is_explicit_and_never_promoted_to_long_term(self):
        current=replace(self.entry,extent='current')
        with self.assertRaises(CollectionUnavailable):build_command('scope-a',current,self.messages,None)
        selected=Selection.parse(dict(id='a'*32,expected_version=3))
        command=build_command('scope-a',current,self.messages,selected)
        self.assertEqual((command.extent,command.context_kind,command.context_id,command.context_version),
                         ('current','travel','a'*32,3))
        self.assertEqual(parse_stored(command.raw),command)
        with self.assertRaises(CollectionUnavailable):build_command('scope-a',self.entry,self.messages,selected)

    def test_source_identity_stays_stable_while_changed_bytes_require_conflict(self):
        first=build_command('scope-a',self.entry,self.messages,None)
        changed=build_command('scope-a',replace(self.entry,text='I avoid spicy food'),self.messages,None)
        self.assertEqual((first.operation_id,first.item_id,first.source_id),
                         (changed.operation_id,changed.item_id,changed.source_id))
        self.assertNotEqual(first.raw,changed.raw)

    def test_inference_stays_inference_and_companion_is_not_rewritten_as_self(self):
        command=build_command('scope-a',replace(self.entry,kind='inference',subject='companion:one'),self.messages,None)
        self.assertEqual((command.kind,command.subject),('inference','companion:one'))
