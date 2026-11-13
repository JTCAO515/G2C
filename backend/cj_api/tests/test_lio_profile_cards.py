import json
from types import SimpleNamespace
import unittest

from cj_message.domain import Unavailable
from cj_api.lio_exploration_profile import (CONTEXT,Original,parse_updates,merge,memory_prefill,snapshot)
from cj_api.lio_profile_cards import LioProfileCards


class ProfileCardsTests(unittest.TestCase):
    def state(self,*,memory=False,epoch=3):
        original=Original('mid',1,'轻松')
        updates=parse_updates(json.dumps(dict(version='LIO-profile-update.1',updates=[dict(
            factor_key='pace',value='relaxed',state='known',sources=[dict(source_index=0,quote='轻松')])])),(original,))
        profile=merge({},updates)
        if memory:
            payload=dict(version='MEMORY-RUN-CONSUME@2',items=[dict(subject='self',slot='travel.pace',
                source_id='manual-v2:original',source_version=1,version=1,text='I prefer slow travel.')])
            profile=merge({},(),memory_prefill(SimpleNamespace(payload=json.dumps(payload).encode())))
        return SimpleNamespace(status='completed',effects=(CONTEXT+json.dumps(snapshot(profile,memory_epoch=epoch)),))

    def fixture(self,epoch):
        stored=SimpleNamespace(raw=json.dumps(dict(text='轻松')).encode(),
            receipt=SimpleNamespace(conversation_id='cid',generation='gen',sequence=1))
        context=SimpleNamespace(query_lio_message=lambda mid:stored if mid=='mid' else None)
        binding=SimpleNamespace(message_id='mid',run_id='rid',conversation_id='cid',generation='gen')
        calls=[]
        def current(*args):calls.append(args);return json.dumps(dict(memory_epoch=epoch,candidates=[])).encode()
        return LioProfileCards(SimpleNamespace(read_current=current)),context,binding,stored,calls

    def test_current_epoch_and_original_sources_produce_localized_public_fields_only(self):
        for locale,word in (('zh','轻松'),('en','Relaxed')):
            cards,context,binding,stored,calls=self.fixture(3)
            rows=cards.project(context,'private-token',binding,self.state(),locale)
            self.assertEqual(len(rows),1)
            self.assertIn(word,rows[0]['display_text'])
            self.assertEqual(rows[0].keys(),{'factor_key','display_text','state'})
            self.assertEqual(len(calls),1)

    def test_changed_memory_epoch_hides_the_entire_cached_profile(self):
        for from_memory in (False,True):
            cards,context,binding,stored,calls=self.fixture(4)
            self.assertEqual(cards.project(context,'token',binding,self.state(memory=from_memory),'en'),[])

    def test_legacy_profile_without_memory_epoch_never_revives_memory_labels(self):
        cards,context,binding,stored,calls=self.fixture(3)
        self.assertEqual(cards.project(context,'token',binding,self.state(memory=True,epoch=None),'en'),[])
        self.assertEqual(calls,[])

    def test_wrong_original_source_owner_or_value_refuses_projection(self):
        for field,value in (('conversation_id','foreign'),('generation','other'),('sequence',2)):
            cards,context,binding,stored,calls=self.fixture(3)
            setattr(stored.receipt,field,value)
            with self.subTest(field=field),self.assertRaises(Unavailable):
                cards.project(context,'token',binding,self.state(),'en')
        cards,context,binding,stored,calls=self.fixture(3)
        stored.raw=json.dumps(dict(text='紧凑')).encode()
        with self.assertRaises(Unavailable):cards.project(context,'token',binding,self.state(),'en')

    def test_no_current_memory_reader_does_not_present_a_cached_epoch_as_current(self):
        cards,context,binding,stored,calls=self.fixture(3)
        with self.assertRaises(Unavailable):LioProfileCards(None).project(context,'token',binding,self.state(),'en')

    def test_no_profile_is_shown_for_unfinished_or_absent_run(self):
        cards,context,binding,stored,calls=self.fixture(3)
        self.assertEqual(cards.project(context,'token',binding,None,'en'),[])
        state=self.state();state.status='running'
        self.assertEqual(cards.project(context,'token',binding,state,'en'),[])
        self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
