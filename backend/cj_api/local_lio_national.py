"""Nationwide Lio planning intake over original MESSAGE/RUN/NEEDS authorities."""
from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from cj_agent.provider import ProviderUnknown
from cj_message.demo_dialogue import LIO_VERSION
from cj_message.domain import Command,Unavailable
from cj_message.lio_context import answer_prompt
from cj_message.lio_plan_needs import BOUND_EFFECT
from cj_needs.domain import InvalidInput

from .lio_city import CityReference
from .lio_national_intake import SYSTEM,NONPERSISTENT,fields_for,parse
from .lio_planning_grounding import PlanningTurn,standalone_question
from .local_lio_planning import PlanningDetails,register

CONTEXT='lio_planning_context.1:'
CITY='lio_city_resolution.1:'
MAX_TURNS=8


class NationalLioPlanning:
    def __init__(self,database,plan_and_save):
        self.database,self.plan_and_save=database,plan_and_save

    def context(self,binding,current):
        with self.database.connect(binding.scope) as db:
            rows=db.execute('SELECT m.message_id,m.sequence,m.raw_input,m.input_sha256,m.demo_question_day,r.status '
                'FROM cj_message_receipt m JOIN cj_run_record r USING(scope,run_id) '
                'WHERE m.scope=%s AND m.conversation_id=%s AND m.generation=%s '
                'AND m.demo_dialogue_protocol=%s AND m.sequence<%s ORDER BY m.sequence DESC LIMIT %s',
                (binding.scope,binding.conversation_id,binding.generation,LIO_VERSION,binding.message_sequence,MAX_TURNS)).fetchall()
            pending=db.execute('SELECT e.value FROM cj_message_receipt m JOIN cj_run_event e USING(scope,run_id) '
                "WHERE m.scope=%s AND m.conversation_id=%s AND m.generation=%s AND m.sequence<%s "
                "AND e.kind='effect_committed' AND e.value LIKE %s ORDER BY m.sequence DESC,e.sequence DESC LIMIT 1",
                (binding.scope,binding.conversation_id,binding.generation,binding.message_sequence,CONTEXT+'%')).fetchone()
        turns=[];refs=[]
        for mid,sequence,raw,digest,day,status in rows:
            if status!='completed':break
            if raw is None:raise Unavailable('original nationwide context was erased')
            command=Command.parse_original(bytes(raw))
            if command.conversation_id!=binding.conversation_id or command.message_id!=mid or sha256(command.raw).hexdigest()!=digest:
                raise Unavailable('original nationwide context differs')
            turns.append(PlanningTurn(json.loads(command.raw)['text'],day or current.question_day))
            refs.append(dict(conversation_id=binding.conversation_id,generation=binding.generation,message_id=mid,sequence=sequence,input_sha256=digest))
        previous=None if pending is None else json.loads(pending[0].removeprefix(CONTEXT))
        return (*reversed(turns),current),tuple(reversed(refs)),previous

    def answer_context(self,binding,messages):
        # This profile already classifies complete original user context. The
        # fallback tool path receives that same context and its source refs.
        current=PlanningTurn(messages[-1]['content'],datetime.now(ZoneInfo('Asia/Shanghai')).date())
        if standalone_question(current.text):return messages,()
        turns,refs,_=self.context(binding,current)
        return [*messages[:-1],*(dict(role='user',content=t.text) for t in turns)],refs

    def execute(self,worker,binding,state,text,original):
        if standalone_question(text):return None
        today=original.question_day or datetime.now(ZoneInfo('Asia/Shanghai')).date()
        turns,refs,previous=self.context(binding,PlanningTurn(text,today))
        dates=', '.join(t.question_day.isoformat() for t in turns)
        messages=[dict(role='user',content=t.text) for t in turns]
        system=answer_prompt(original.locale)+' '+SYSTEM+' Original local China days in order: '+dates
        raw=''.join(worker._registered_stream(binding,'model.lio_intake.0','model.answer',
                    (messages,system,worker.provider),message_refs=refs))
        try:intake=parse(raw,turns)
        except (InvalidInput,ValueError,UnicodeError) as error:
            raise ProviderUnknown('nationwide structured intake unavailable') from error
        if intake.intent=='cancel':
            state=self._context(worker,binding,state,dict(authority='none',status='cancelled'))
            return self._answer(worker,binding,state,original.locale,'好，先不保存或修改行程。',"Okay, I won't save or change an itinerary.")
        if intake.intent=='consult' and not intake.needs_tools:
            return self._reply(worker,binding,state,intake.reply)
        if intake.city is None:
            if intake.intent=='consult':
                return None
            state=self._context(worker,binding,state,dict(authority=self._authority(intake,previous),status='needs_city'))
            return self._answer(worker,binding,state,original.locale,'想去哪个城市？','Which city would you like to visit?')
        resolution=worker.tools.resolve_city(worker,binding,intake.city)
        state=worker._event(binding,state,'effect_committed',CITY+json.dumps(resolution,ensure_ascii=False,separators=(',',':')))
        if resolution['status']!='resolved':
            state=self._context(worker,binding,state,dict(authority=self._authority(intake,previous),status=resolution['status'],city=resolution))
            candidates=resolution['candidates']
            if candidates:
                options='；'.join(c['province']+' '+c['name'] for c in candidates)
                question=('你指的是哪个行政区：'+options+'？' if original.locale=='zh' else
                          'Which administrative destination do you mean: '+options+'?')
            else:question=('还没能确认这个城市，请补充省份和城市名称。' if original.locale=='zh' else
                           'I could not confirm that city. Please share its province and city name.')
            return self._reply(worker,binding,state,question)
        city=CityReference(**resolution['candidates'][0]);worker.lio_city_context=city
        if intake.intent=='consult':return None
        if intake.intent=='discuss' or NONPERSISTENT.search(text):
            state=self._context(worker,binding,state,dict(authority='none',status='discussion',city=resolution))
            return self._reply(worker,binding,state,intake.reply)
        try:
            fields,checked=fields_for(intake,city,message_id=binding.message_id,run_id=binding.run_id,
                                      source_text='\n'.join(t.text for t in turns))
        except (InvalidInput,ValueError) as error:
            raise ProviderUnknown('original nationwide planning fields unavailable') from error
        authority=self._authority(intake,previous)
        missing=[]
        for edge in ('arrival','departure'):
            if fields.get(edge,{}).get('date',{}).get('state')!='known':missing.append(edge+'.date')
        questions=[q for q in checked.get('questions',[]) if q['field']=='fixed_items']
        if missing or questions:
            state=self._context(worker,binding,state,dict(authority=authority,status='needs_details',city=resolution))
            if missing:
                zh='你打算哪天开始这趟行程？' if intake.duration_days else '你打算哪天开始、玩几天？'
                en='What date should this trip start?' if intake.duration_days else 'When should this trip start, and for how many days?'
            else:
                zh='需要保留的安排，谁参加、哪天以及开始和结束时间分别是什么？'
                en='For the fixed arrangement, who is attending, on which day, and at what start and end times?'
            return self._answer(worker,binding,state,original.locale,zh,en)
        if authority=='none':return self._reply(worker,binding,state,intake.reply)
        details=PlanningDetails(city.name,fields,None,refs)
        state=register(worker,binding,state,details)
        return self.plan_and_save(worker,binding,state,details,original.locale)

    @staticmethod
    def _authority(intake,previous):
        if NONPERSISTENT.search(intake.current_request):return 'none'
        if intake.intent in ('plan','save'):return intake.intent
        return 'none' if previous is None else previous.get('authority','none')

    @staticmethod
    def _context(worker,binding,state,value):
        return worker._event(binding,state,'effect_committed',CONTEXT+json.dumps(value,ensure_ascii=False,separators=(',',':')))

    @staticmethod
    def _reply(worker,binding,state,text):
        state=worker._event(binding,state,'text_delta',text)
        return worker._event(binding,state,'completed')

    def _answer(self,worker,binding,state,locale,zh,en):
        return self._reply(worker,binding,state,zh if locale=='zh' else en)
