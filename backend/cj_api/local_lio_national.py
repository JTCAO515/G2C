"""Nationwide Lio planning intake over original MESSAGE/RUN/NEEDS authorities."""
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
import re
from zoneinfo import ZoneInfo

from cj_agent.provider import ProviderUnknown
from cj_message.demo_dialogue import LIO_VERSION
from cj_message.domain import Command,Unavailable
from cj_message.lio_context import answer_prompt
from cj_message.lio_plan_needs import BOUND_EFFECT
from cj_needs.domain import InvalidInput

from .lio_city import CityReference,forms,_normalize
from .lio_national_intake import SYSTEM,NONPERSISTENT,fields_for,parse
from .lio_planning_grounding import PlanningTurn,standalone_question,FIXED
from .local_lio_planning import PlanningDetails,register

CONTEXT='lio_planning_context.1:'
CITY='lio_city_resolution.1:'
MAX_TURNS=8
# This is a publication gate, not city/date extraction or the intent router.
# A model cannot turn an isolated date/party answer into a fresh save grant.
PUBLICATION_REQUEST=re.compile(r"计划|规划|安排|设计|保存|存到|存入|想去|要去|帮我做|"
    r"\b(?:plan(?:ning)?|save|store|build|create|organize|put together)\b|"
    r"\b(?:want|would like) to (?:go|visit|travel)\b",re.I)


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
            pending=db.execute('SELECT m.message_id,e.value FROM cj_message_receipt m JOIN cj_run_event e USING(scope,run_id) '
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
        previous=(None if pending is None or pending[0] not in {ref['message_id'] for ref in refs}
                  else json.loads(pending[1].removeprefix(CONTEXT)))
        return (*reversed(turns),current),tuple(reversed(refs)),previous

    def answer_context(self,binding,messages):
        # This profile already classifies complete original user context. The
        # fallback tool path receives that same context and its source refs.
        current=PlanningTurn(messages[-1]['content'],datetime.now(ZoneInfo('Asia/Shanghai')).date())
        if standalone_question(current.text):return messages,()
        turns,refs,_=self.context(binding,current)
        return [*messages[:-1],*(dict(role='user',content=t.text) for t in turns)],refs

    def execute(self,worker,binding,state,text,original):
        if re.fullmatch(r'\s*(?:你是谁|你是什么|我是谁|你了解我什么|你能做什么|你有什么能力|who are you|what are you|who am i|what do you know about me|what can you do)[?？。.!！\s]*',text,re.I):return None
        today=original.question_day or datetime.now(ZoneInfo('Asia/Shanghai')).date()
        turns,refs,previous=self.context(binding,PlanningTurn(text,today))
        dates=', '.join(t.question_day.isoformat() for t in turns)
        messages=[dict(role='user',content=t.text) for t in turns]
        if worker.memory_run is not None:
            memory_messages=worker.memory_run.messages(text)
            messages=[*memory_messages[:-1],*messages]
        if worker.message_context is not None:messages=worker.message_context.answer_messages(binding,messages)
        system=answer_prompt(original.locale)+' '+SYSTEM+' Original traveler messages have source indices 0 through '+str(len(turns)-1)+'. Stored memory data is not an indexed traveler message. Original local China days in that order: '+dates
        raw=''.join(worker._registered_stream(binding,'model.lio_intake.0','model.lio_intake.1',
                    (messages,system,worker.provider),message_refs=refs))
        try:intake=parse(raw,turns)
        except (InvalidInput,ValueError,UnicodeError) as error:
            raise ProviderUnknown('nationwide structured intake unavailable') from error
        if intake.intent=='cancel':
            state=self._context(worker,binding,state,dict(authority='none',status='cancelled'))
            return self._answer(worker,binding,state,original.locale,'好，先不保存或修改行程。',"Okay, I won't save or change an itinerary.")
        if intake.intent=='consult' and not intake.needs_tools:
            state=self._context(worker,binding,state,dict(authority='none',status='consult'))
            return self._reply(worker,binding,state,intake.reply)
        if intake.city is None:
            if intake.intent=='consult' and intake.needs_tools:
                from .real_services import _lio_transit_request
                if _lio_transit_request(messages):
                    # Official China entry policy has no destination-city parameter.
                    self._context(worker,binding,state,dict(authority='none',status='consult'))
                    return None
            state=self._context(worker,binding,state,dict(authority='none' if intake.intent=='consult' else self._authority(intake,previous),status='needs_city'))
            return self._answer(worker,binding,state,original.locale,'想去哪个城市？','Which city would you like to visit?')
        resolution=self._previous_city(intake,previous,text)
        if resolution is None:resolution=worker.tools.resolve_city(worker,binding,intake.city)
        state=worker._event(binding,state,'effect_committed',CITY+json.dumps(resolution,ensure_ascii=False,separators=(',',':')))
        from cj_message.lio_context import LioCitation
        state=worker._event(binding,state,'effect_committed',LioCitation('city-resolution',
            '高德行政区划' if original.locale=='zh' else 'Amap Administrative Districts',None,
            resolution['source'].get('observed_at')).effect())
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
        from .lio_weather import CITY_EFFECT
        state=worker._event(binding,state,'effect_committed',CITY_EFFECT+json.dumps(asdict(city),ensure_ascii=False,separators=(',',':')))
        if intake.intent=='consult':
            self._context(worker,binding,state,dict(authority='none',status='consult',city=resolution))
            return None
        if intake.intent=='discuss' or NONPERSISTENT.search(text):
            state=self._context(worker,binding,state,dict(authority='none',status='discussion',city=resolution))
            return self._reply(worker,binding,state,intake.reply)
        try:
            fields,checked=fields_for(intake,city,message_id=binding.message_id,run_id=binding.run_id,
                                      source_text='\n'.join(t.text for t in turns))
        except (InvalidInput,ValueError) as error:
            raise ProviderUnknown('original nationwide planning fields unavailable') from error
        authority=self._authority(intake,previous)
        # A date mentioned for an earlier destination must not leak into a
        # later city correction. Missing-city clarification retains its dates.
        if intake.city['source_index']>0 and previous is not None and previous.get('city') is not None:
            old=previous['city']['candidates']
            if len(old)!=1 or old[0]['adcode']!=city.adcode:
                for edge in ('arrival','departure'):
                    evidence=intake.sources.get(edge+'.date',[])
                    if not evidence or all(r['source_index']<intake.city['source_index'] for r in evidence):
                        fields[edge]['date']=dict(state='missing')
        missing=[]
        for edge in ('arrival','departure'):
            if fields.get(edge,{}).get('date',{}).get('state')!='known':missing.append(edge+'.date')
        questions=[q for q in checked.get('questions',[]) if q['field']=='fixed_items']
        fixed_items=fields.get('fixed_items',[])
        incomplete_fixed=any(any(item[edge][part]['state']!='known' for edge in ('start','end')
                                 for part in ('date','time','timezone')) for item in fixed_items)
        omitted_fixed=not fixed_items and any(FIXED.search(t.text) for t in turns)
        if fields.get('party_size',{}).get('state')!='known':missing.append('party_size')
        if missing or questions or incomplete_fixed or omitted_fixed:
            state=self._context(worker,binding,state,dict(authority=authority,status='needs_details',city=resolution))
            if missing==['party_size']:
                zh='这趟旅行一共几个人？';en='How many people are traveling?'
            elif missing:
                zh='你打算哪天开始这趟行程？' if intake.duration_days else '你打算哪天开始、玩几天？'
                en='What date should this trip start?' if intake.duration_days else 'When should this trip start, and for how many days?'
            else:
                zh='需要保留的安排，谁参加、哪天以及开始和结束时间分别是什么？'
                en='For the fixed arrangement, who is attending, on which day, and at what start and end times?'
            return self._answer(worker,binding,state,original.locale,zh,en)
        if authority=='none':return self._reply(worker,binding,state,intake.reply)
        state=self._context(worker,binding,state,dict(authority='none',status='ready_to_publish',city=resolution))
        details=PlanningDetails(city.name,fields,None,refs)
        state=register(worker,binding,state,details)
        return self.plan_and_save(worker,binding,state,details,original.locale)

    @staticmethod
    def _previous_city(intake,previous,text):
        if previous is None or previous.get('city') is None:return None
        old=previous['city']
        if len(old['candidates'])!=1:return None
        city=old['candidates'][0]
        same=_normalize(intake.city['query']) in forms(city['name'],city['level'])
        confirmed=(old['status']=='confirmation_required' and re.fullmatch(
            r"\s*(?:yes|correct|that's right|confirm|是|是的|对|对的|没错|确认)[。.!！]?\s*",text,re.I) is not None)
        if old['status']=='resolved' and same or confirmed:
            return dict(old,status='resolved')
        return None

    @staticmethod
    def _authority(intake,previous):
        if intake.intent in ('consult','discuss','cancel') or NONPERSISTENT.search(intake.current_request):return 'none'
        if intake.intent in ('plan','save') and PUBLICATION_REQUEST.search(intake.current_request):return intake.intent
        if previous is not None and previous.get('status') in ('needs_city','needs_details','ambiguous','confirmation_required','not_found','needs_city'):
            return previous['authority']
        return 'none'

    @staticmethod
    def _context(worker,binding,state,value):
        return worker._event(binding,state,'effect_committed',CONTEXT+json.dumps(value,ensure_ascii=False,separators=(',',':')))

    @staticmethod
    def _reply(worker,binding,state,text):
        state=worker._event(binding,state,'text_delta',text)
        return worker._event(binding,state,'completed')

    def _answer(self,worker,binding,state,locale,zh,en):
        return self._reply(worker,binding,state,zh if locale=='zh' else en)
