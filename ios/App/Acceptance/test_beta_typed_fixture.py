"""Synthetic input-boundary checks; no credentials, network or device."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from beta_typed_fixture import operator_typed_fixture, OWNER, ORIGIN


class BetaTypedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ids = ['a'*32, 'b'*32]
        self.config = dict(owner=OWNER, status='PREPARED_NOT_DEPLOYED', server_context_version=1,
            server_context_versions={v: 1 for v in self.ids},
            G2C_DEV_TRAVEL_PROFILE=dict(version='app-travel.1', travel_ids=self.ids),
            G2C_DEV_TYPED_MEMORY_PROFILE=dict(version='app-memory.2', subjects=['self'],
                slots={'preference': dict(kind='preference', collection_allowed=True, semantic_resolved=True)},
                extents=['long_term', 'current']), G2C_DEV_TYPED_MEMORY_URL=ORIGIN)
        items = []
        for index, context in enumerate([None, *[dict(kind='travel', id=v, expected_version=1) for v in self.ids]]):
            items.append(dict(item_id='synthetic-item-'+str(index), operation_id='synthetic-operation-'+str(index),
                subject='self', slot='preference', kind='preference', text='SYNTHETIC "中文" e\u0301\n'+str(index),
                occurred_at='time unknown', extent='long_term' if context is None else 'current', context=context,
                source_id='synthetic-source-'+str(index), source_version=1, version=3 if index==0 else 1,
                status='active', recorded_at='2026-11-06T00:00:00Z'))
        self.records = dict(owner=OWNER, source_capture_sha256='c'*64,
            captured_state='synthetic fixture only', items=items, budget=[0,0], worker_memory='UNRUN')

    def write(self, name, value):
        path=self.root/name;path.write_text(json.dumps(value,ensure_ascii=False));os.chmod(path,0o600)
        return path

    def load(self, config=None, records=None):
        return operator_typed_fixture(self.write('config.json', self.config if config is None else config),
                                      self.write('records.json', self.records if records is None else records))

    def test_choices_are_strings_and_seed_bytes_unchanged_without_authorizing_runtime(self):
        before=copy.deepcopy(self.records)
        fixture,proof=self.load()
        self.assertEqual(fixture['owner'],OWNER)
        self.assertEqual(set(fixture['environment']),{'G2C_DEV_TRAVEL_PROFILE','G2C_DEV_TYPED_MEMORY_PROFILE','G2C_DEV_TYPED_MEMORY_URL'})
        self.assertTrue(all(type(v) is str for v in fixture['environment'].values()))
        self.assertEqual(json.loads(fixture['environment']['G2C_DEV_TRAVEL_PROFILE'])['travel_ids'],self.ids)
        self.assertEqual(fixture['seeds'],self.records['items']);self.assertEqual(self.records,before)
        self.assertEqual(proof['model_recall'],'UNRUN');self.assertEqual(proof['source_status'],'PREPARED_NOT_DEPLOYED')

    def test_foreign_owner_or_origin_cannot_be_packaged(self):
        for field,value in [('owner','m4-synthetic-beta-a'),('G2C_DEV_TYPED_MEMORY_URL',ORIGIN+'/other'),
                            ('G2C_DEV_TYPED_MEMORY_URL','https://evil.invalid')]:
            with self.subTest(field=field,value=value):
                config=copy.deepcopy(self.config);config[field]=value
                with self.assertRaises(ValueError):self.load(config=config)
        records=copy.deepcopy(self.records);records['owner']='m4-synthetic-beta-a'
        with self.assertRaises(ValueError):self.load(records=records)

    def test_collection_flags_cannot_be_numbers_or_expand_the_policy(self):
        for value in [1,0,False]:
            config=copy.deepcopy(self.config);config['G2C_DEV_TYPED_MEMORY_PROFILE']['slots']['preference']['collection_allowed']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.load(config=config)
        config=copy.deepcopy(self.config);config['G2C_DEV_TYPED_MEMORY_PROFILE']['slots']['another']=dict(kind='preference',collection_allowed=True,semantic_resolved=True)
        with self.assertRaises(ValueError):self.load(config=config)

    def test_duplicate_or_unregistered_Travel_cannot_replace_the_two_original_scopes(self):
        config=copy.deepcopy(self.config);config['G2C_DEV_TRAVEL_PROFILE']['travel_ids']=[self.ids[0]]*2
        with self.assertRaises(ValueError):self.load(config=config)
        for field,value in [('id','d'*32),('kind','legacy'),('expected_version',True),('expected_version',0)]:
            records=copy.deepcopy(self.records);records['items'][1]['context'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.load(records=records)

    def test_nonactive_or_different_subject_kind_slot_seeds_are_not_mutation_inputs(self):
        for field,value in [('status','withdrawn'),('subject','another'),('kind','inference'),('slot','another'),
                            ('version',True),('source_version',0)]:
            records=copy.deepcopy(self.records);records['items'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.load(records=records)

    def test_missing_scope_or_duplicate_item_refuses_before_any_execution(self):
        records=copy.deepcopy(self.records);records['items'].pop()
        with self.assertRaises(ValueError):self.load(records=records)
        records=copy.deepcopy(self.records);records['items'][2]['item_id']=records['items'][1]['item_id']
        with self.assertRaises(ValueError):self.load(records=records)

    def test_operator_inputs_must_remain_owned_private_regular_files(self):
        config=self.write('config.json',self.config);records=self.write('records.json',self.records)
        os.chmod(config,0o644)
        with self.assertRaises(ValueError):operator_typed_fixture(config,records)
        os.chmod(config,0o600);link=self.root/'link.json';link.symlink_to(config)
        with self.assertRaises(ValueError):operator_typed_fixture(link,records)


if __name__=='__main__':unittest.main()
