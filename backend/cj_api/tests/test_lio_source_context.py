"""Human history and cached execution authority have different lifetimes."""
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace
import unittest

from cj_api.local_lio_national import NationalLioPlanning,CONTEXT
from cj_api.lio_planning_grounding import PlanningTurn
from cj_message.domain import Unavailable

DAY=date(2026,11,15)


def row(mid,sequence,text,status='completed',day=DAY):
    raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id=mid,
        text=text,trip_id=None,creation_intent='none')).encode()
    return mid,sequence,raw,sha256(raw).hexdigest(),day,status


class SourceContext(unittest.TestCase):
    def context(self,rows,previous=None,*,native=True,denied=False):
        calls=[]
        class Database:
            @contextmanager
            def connect(self,scope):
                assert scope=='owner';yield self
            def execute(self,sql,args):
                if 'LIMIT %s'in sql:return SimpleNamespace(fetchall=lambda:rows)
                if 'LIMIT 1'in sql:return SimpleNamespace(fetchone=lambda:previous)
                return SimpleNamespace(fetchall=lambda:[r for r in rows if r[0]in args[-1]])
        class Sources:
            active=False
            @contextmanager
            def hold_for_effect(self,binding):
                self.active=True
                try:yield SimpleNamespace(reference=SimpleNamespace(message_version='MESSAGE-send.2'))
                finally:self.active=False
            def active_source_original(self,binding,mid):
                assert self.active
                calls.append(mid)
                if denied:raise Unavailable('original source holder unavailable')
                r=next(r for r in rows if r[0]==mid)
                return SimpleNamespace(stored=SimpleNamespace(raw=r[2]),reference=SimpleNamespace(input_sha256=r[3]))
        planner=NationalLioPlanning(Database(),None,message_context=Sources()if native else None)
        binding=SimpleNamespace(scope='owner',conversation_id='chat',generation='generation',message_sequence=4)
        return planner.context(binding,PlanningTurn('具体的行程呢',DAY)),calls

    def test_failed_human_original_is_retained_without_inheriting_failed_effects(self):
        for status in ('unknown','failed'):
            with self.subTest(status=status):
                rows=[row('failed',2,'去成都玩三天',status),row('earlier',1,'你好')]
                (turns,refs,previous),calls=self.context(rows)
                self.assertEqual([t.text for t in turns],['你好','去成都玩三天','具体的行程呢'])
                self.assertEqual([r['message_id']for r in refs],['earlier','failed'])
                self.assertEqual(previous['authority'],'none');self.assertEqual(previous['facts'],{})
                self.assertEqual(previous['uncompleted_request_message_ids'],['failed'])
                self.assertEqual(calls,['failed','earlier'])
                (legacy,_,_),calls=self.context(rows,native=False)
                self.assertEqual(len(legacy),1);self.assertEqual(calls,[])

    def test_completed_denials_survive_failure_but_allow_and_cached_facts_do_not(self):
        rows=[row('failed',3,'继续','unknown'),row('hold',2,'先不保存'),row('old',1,'规划成都三天')]
        old=dict(authority='plan',status='discussion',facts={'duration_days':dict(value=3,sources=[])},
            date_boundary_message_id='old',nonplanning_message_ids=['hold'])
        (_,_,previous),_=self.context(rows,('hold',CONTEXT+json.dumps(old)))
        self.assertEqual(previous['authority'],'none');self.assertEqual(previous['facts'],{})
        self.assertEqual(previous['authority_barrier_message_id'],'hold')
        self.assertEqual(previous['nonplanning_message_ids'],['hold'])
        self.assertEqual(previous['date_boundary_message_id'],'old')

    def test_unknown_original_no_save_text_only_denies_and_never_grants(self):
        rows=[row('failed',2,'不要保存这个行程','unknown'),row('old',1,'规划成都三天')]
        (_,_,previous),_=self.context(rows)
        self.assertEqual(previous['authority'],'none');self.assertEqual(previous['authority_barrier_message_id'],'failed')

    def test_failed_root_never_grants_but_its_data_can_support_a_new_explicit_request(self):
        previous=dict(authority='none',status='consult',facts={},uncompleted_request_message_ids=['failed'])
        turns=(PlanningTurn('规划成都三天',DAY),PlanningTurn('请继续规划三天',DAY))
        intake=SimpleNamespace(intent='plan',publication_hold=False,current_request=turns[-1].text,
            planning_request_index=0,city=dict(source_index=0,query='成都'),duration_days=3,
            sources={'duration_days':[dict(source_index=0)]})
        self.assertEqual(NationalLioPlanning._authority(intake,previous,current_index=1,
            turns=turns,source_ids=['failed','current']),'none')
        intake.planning_request_index=1
        self.assertEqual(NationalLioPlanning._authority(intake,previous,current_index=1,
            turns=turns,source_ids=['failed','current']),'plan')

    def test_source_holder_and_original_day_fail_closed(self):
        rows=[row('failed',2,'去成都玩三天','unknown')]
        with self.assertRaises(Unavailable):self.context(rows,denied=True)
        with self.assertRaises(Unavailable):self.context([row('failed',2,'下周二开始','unknown',day=None)])


if __name__=='__main__':unittest.main()
