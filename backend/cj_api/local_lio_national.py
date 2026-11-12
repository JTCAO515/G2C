"""Nationwide Lio planning intake over original MESSAGE/RUN/NEEDS authorities."""
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
import logging
import re
from zoneinfo import ZoneInfo

from cj_agent.provider import ProviderUnknown
from cj_agent.lio_intake_flow_schema import SYSTEM as FACTS_SYSTEM
from cj_message.demo_dialogue import LIO_VERSION
from cj_message.domain import Command,Unavailable
from cj_message.lio_context import answer_prompt
from cj_message.lio_plan_needs import BOUND_EFFECT
from cj_needs.domain import InvalidInput

from .lio_city import CityReference,forms,_normalize
from .lio_sourced_intake import BookingSourceUnclear
from .lio_flow_intake import parse_flow
from .lio_national_intake import NONPERSISTENT,fields_for,fixed_sources_complete,province_evidence,diagnostic_code,StartDateConflict,FixedTimezoneConflict
from .lio_planning_grounding import PlanningTurn,standalone_question
from .local_lio_planning import PlanningDetails,register

CONTEXT='lio_planning_context.1:'
CITY='lio_city_resolution.1:'
MAX_TURNS=8
CURRENT_SYSTEM=FACTS_SYSTEM
# This is a publication gate, not city/date extraction or the intent router.
# A model cannot turn an isolated date/party answer into a fresh save grant.
PUBLICATION_REQUEST=re.compile(r"计划|规划|安排|设计|保存|存到|存入|想去|要去|帮我做|"
    r"\b(?:plan(?:ning)?|save|store|build|create|make|design|organize|put together)\b|"
    r"\b(?:want|would like) to (?:go|visit|travel|spend)\b|"
    r"\b(?:i|we) would like\b[^.!?]{0,120}\b(?:itinerary|trip)\b|"
    r"去[^。！？?!.]{1,80}(?:玩|旅游|旅行|游)|排(?:个|一个|一份)?行程",re.I)


def intake_prompt(locale,turns):
    dates=', '.join(turn.question_day.isoformat() for turn in turns)
    return answer_prompt(locale)+' '+CURRENT_SYSTEM+' Original traveler messages have source indices 0 through '+str(len(turns)-1)+'. Stored memory data is not an indexed traveler message. Original local China days in that order: '+dates


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
            continuous=[]
            for row in rows:
                if row[-1]!='completed':break
                continuous.append(row)
            previous=(None if pending is None or pending[0]not in {row[0]for row in continuous}
                      else json.loads(pending[1].removeprefix(CONTEXT)))
            anchors=set()if previous is None else {ref['message_id']for fact in previous.get('facts',{}).values()for ref in fact['sources']}
            older=anchors-{row[0]for row in continuous}
            if older:
                # Keep the originals backing already answered facts even after
                # they leave the recent window. Scope/generation/erasure and
                # completed status remain the original protected read fence.
                saved=db.execute('SELECT m.message_id,m.sequence,m.raw_input,m.input_sha256,m.demo_question_day,r.status '
                    'FROM cj_message_receipt m JOIN cj_run_record r USING(scope,run_id) '
                    'WHERE m.scope=%s AND m.conversation_id=%s AND m.generation=%s '
                    'AND m.demo_dialogue_protocol=%s AND m.sequence<%s AND m.message_id=ANY(%s)',
                    (binding.scope,binding.conversation_id,binding.generation,LIO_VERSION,binding.message_sequence,list(older))).fetchall()
                if {row[0]for row in saved}!=older or any(row[-1]!='completed'for row in saved):
                    raise Unavailable('original nationwide fact source unavailable')
                continuous=sorted([*continuous,*saved],key=lambda row:row[1],reverse=True)
        turns=[];refs=[]
        for mid,sequence,raw,digest,day,status in continuous:
            if raw is None:raise Unavailable('original nationwide context was erased')
            command=Command.parse_original(bytes(raw))
            if command.conversation_id!=binding.conversation_id or command.message_id!=mid or sha256(command.raw).hexdigest()!=digest:
                raise Unavailable('original nationwide context differs')
            turns.append(PlanningTurn(json.loads(command.raw)['text'],day or current.question_day))
            refs.append(dict(conversation_id=binding.conversation_id,generation=binding.generation,message_id=mid,sequence=sequence,input_sha256=digest))
        return (*reversed(turns),current),tuple(reversed(refs)),previous

    def answer_context(self,binding,messages):
        # This profile already classifies complete original user context. The
        # fallback tool path receives that same context and its source refs.
        current=PlanningTurn(messages[-1]['content'],datetime.now(ZoneInfo('Asia/Shanghai')).date())
        if standalone_question(current.text):return messages,()
        turns,refs,_=self.context(binding,current)
        return [*messages[:-1],*(dict(role='user',content=t.text) for t in turns)],refs

    def execute(self,worker,binding,state,text,original):
        if re.fullmatch(r'\s*(?:你是谁|你是什么|我是谁|你了解我什么|你能做什么|你能干啥|你有什么能力|who are you|what are you|who am i|what do you know about me|what can you do)[?？。.!！\s]*',text,re.I):return None
        today=original.question_day or datetime.now(ZoneInfo('Asia/Shanghai')).date()
        turns,refs,previous=self.context(binding,PlanningTurn(text,today))
        messages=[dict(role='user',content=t.text) for t in turns]
        if worker.memory_run is not None:
            memory_messages=worker.memory_run.messages(text)
            messages=[*memory_messages[:-1],*messages]
        if worker.message_context is not None:messages=worker.message_context.answer_messages(binding,messages)
        system=intake_prompt(original.locale,turns)
        raw=''.join(worker._registered_stream(binding,'model.lio_intake.0','model.lio_intake.8',
                    (messages,system,worker.provider,len(turns)-1),message_refs=refs))
        booking_unclear=False;question_fields=[];facts={}
        try:intake,question_fields,facts=parse_flow(raw,turns,refs,binding.message_id,previous)
        except BookingSourceUnclear as error:
            intake=error.control;booking_unclear=True
        except (InvalidInput,ValueError,UnicodeError) as error:
            logging.getLogger('cj_usage.audit').warning('LIO_INTAKE_REJECTED run_id=%s code=%s output_sha256=%s output_bytes=%s',
                binding.run_id,diagnostic_code(error),sha256(raw.encode('utf-8','surrogatepass')).hexdigest(),len(raw.encode('utf-8','surrogatepass')))
            raise ProviderUnknown('nationwide structured intake unavailable') from error
        def context(worker,binding,state,value):
            return self._context(worker,binding,state,dict(value,facts=facts))
        authority=self._authority(intake,previous,current_index=len(turns)-1)
        if intake.intent=='cancel':
            state=context(worker,binding,state,dict(authority='none',status='cancelled'))
            return self._answer(worker,binding,state,original.locale,'好，先不保存或修改行程。',"Okay, I won't save or change an itinerary.")
        # Facts choose the planning flow; advisory intent/needs_tools cannot
        # discard a clarification and send an incomplete plan to native tools.
        supplied=any(ref['source_index']==len(turns)-1 for sources in intake.sources.values()for ref in sources)
        city_reply=(previous is not None and previous.get('status')=='needs_city'and intake.city is not None
                    and intake.city['source_index']==len(turns)-1)
        planning=authority!='none'and (intake.intent in ('plan','save')or supplied or city_reply)
        if intake.publication_hold or NONPERSISTENT.search(text) or not planning and intake.intent=='discuss':
            state=context(worker,binding,state,dict(authority='none',status='discussion'))
            return self._reply(worker,binding,state,intake.reply)
        if planning and not booking_unclear:
            missing=[]
            if intake.city is None:missing.append('city')
            if intake.duration_days is None:
                fields={}if intake.extraction is None else intake.extraction['fields']
                if fields.get('departure',{}).get('date',{}).get('state')!='known':missing.append('duration_days')
            if intake.start_date is None or intake.start_date['state']!='known':missing.append('start_date')
            if intake.extraction['fields'].get('party_size',{}).get('state')!='known':missing.append('party_size')
            if missing:
                state=context(worker,binding,state,dict(authority=authority,status='needs_details',
                    **({'city':previous['city']}if previous is not None and previous.get('city')is not None else {})))
                return self._clarify(worker,binding,state,original.locale,intake.reply,question_fields,missing,
                    arrival=intake.extraction['fields'].get('arrival',{}).get('date'))
        if not planning and intake.intent=='consult' and not intake.needs_tools:
            state=context(worker,binding,state,previous if authority!='none'else dict(authority='none',status='consult'))
            return self._reply(worker,binding,state,intake.reply,collect_memory=True)
        if intake.city is None:
            if not planning and intake.intent=='consult' and intake.needs_tools:
                from .real_services import _lio_transit_request
                if _lio_transit_request(messages):
                    context(worker,binding,state,dict(authority='none',status='consult'))
                    return None
            state=context(worker,binding,state,dict(authority=authority,status='needs_city'))
            return self._clarify(worker,binding,state,original.locale,intake.reply,question_fields,['city'])
        resolution=self._previous_city(intake,previous,text)
        if resolution is None:resolution=worker.tools.resolve_city(worker,binding,intake.city)
        state=worker._event(binding,state,'effect_committed',CITY+json.dumps(resolution,ensure_ascii=False,separators=(',',':')))
        from cj_message.lio_context import LioCitation
        state=worker._event(binding,state,'effect_committed',LioCitation('city-resolution',
            '高德行政区划' if original.locale=='zh' else 'Amap Administrative Districts',None,
            resolution['source'].get('observed_at')).effect())
        if resolution['status']!='resolved':
            state=context(worker,binding,state,dict(authority=self._authority(intake,previous,current_index=len(turns)-1),status=resolution['status'],city=resolution))
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
        if not planning and intake.intent=='consult':
            context(worker,binding,state,previous if authority!='none'else dict(authority='none',status='consult',city=resolution))
            return None
        if not planning and intake.intent=='discuss':
            state=context(worker,binding,state,dict(authority='none',status='discussion',city=resolution))
            return self._reply(worker,binding,state,intake.reply)
        authority=self._authority(intake,previous,current_index=len(turns)-1)
        if booking_unclear:
            state=context(worker,binding,state,dict(authority=authority,status='needs_details',city=resolution))
            return self._answer(worker,binding,state,original.locale,
                '请明确每项固定安排的名称、日期、时间、谁参加，以及哪一项确实已经预约；尚未保存。',
                'Please name each fixed arrangement, its date, time, participants, and which reservation is confirmed; nothing has been saved.')
        if intake.fixed_detail_ambiguous:
            state=context(worker,binding,state,dict(authority=authority,status='needs_details',city=resolution))
            return self._answer(worker,binding,state,original.locale,
                '请说明这条补充针对哪一项固定安排，并使用该安排的名称；尚未保存。',
                'Please name the fixed arrangement this clarification applies to; nothing has been saved.')
        try:
            fields,checked=fields_for(intake,city,message_id=binding.message_id,run_id=binding.run_id,
                                      source_text='\n'.join(t.text for t in turns))
        except StartDateConflict:
            state=context(worker,binding,state,dict(authority=authority,status='needs_details',city=resolution))
            return self._answer(worker,binding,state,original.locale,
                '行程开始日与已给的到达日不同，行程范围应从哪一天算起？',
                'The trip start and arrival dates differ. Which date should define the itinerary range?')
        except FixedTimezoneConflict:
            state=context(worker,binding,state,dict(authority=authority,status='needs_details',city=resolution))
            return self._answer(worker,binding,state,original.locale,
                '这项固定安排的时区与目的地不同或不明确，请确认应使用哪个时区；尚未保存。',
                'The fixed arrangement has a different or unclear timezone. Please confirm which timezone to use; nothing has been saved.')
        except (InvalidInput,ValueError) as error:
            raise ProviderUnknown('original nationwide planning fields unavailable') from error
        if not self.plan_and_save.supports_destination(binding,city):
            state=context(worker,binding,state,dict(authority='none',status='different_destination',city=resolution))
            return self._answer(worker,binding,state,original.locale,
                '这个对话已有另一座城市的行程。请新开对话来规划这趟旅行，保留原行程。',
                'This conversation already has an itinerary for another destination. Start a new conversation for this trip to keep the original itinerary.')
        # Refining an unresolved destination preserves that original request's
        # dates. Changing an already resolved destination does not, even when
        # the model reuses an older homonymous city quote.
        date_boundary=intake.city['source_index']
        prior_city=None if previous is None else previous.get('city')
        if prior_city is not None:
            same_target=any(candidate['adcode']==city.adcode or
                candidate['level']=='province' and candidate['name']==city.province
                for candidate in prior_city['candidates'])
            date_boundary=0 if same_target else len(turns)-1
        elif previous is not None and previous.get('status')=='needs_city':
            date_boundary=0
        if date_boundary:
            for edge in ('arrival','departure'):
                evidence=intake.sources.get(edge+'.date',[])
                if edge=='departure' and not evidence and intake.duration_days is not None:
                    evidence=intake.sources.get('arrival.date',[])
                if evidence and all(ref['source_index']<date_boundary for ref in evidence):
                    fields[edge]['date']=dict(state='missing')
        missing=[]
        if intake.start_date is not None and intake.start_date['state']!='known':missing.append('start_date')
        for edge in ('arrival','departure'):
            if fields.get(edge,{}).get('date',{}).get('state')!='known':missing.append(edge+'.date')
        questions=[q for q in checked.get('questions',[]) if q['field']=='fixed_items']
        complete_fixed=fixed_sources_complete(intake,fields,turns,city)
        if fields.get('party_size',{}).get('state')!='known':missing.append('party_size')
        if missing or questions or not complete_fixed:
            state=context(worker,binding,state,dict(authority=authority,status='needs_details',city=resolution))
            required=[]
            if any(field in missing for field in ('start_date','arrival.date')):required.append('start_date')
            if 'departure.date'in missing and intake.duration_days is None:required.append('duration_days')
            if 'party_size'in missing:required.append('party_size')
            if questions or not complete_fixed:required.append('fixed_items')
            return self._clarify(worker,binding,state,original.locale,intake.reply,question_fields,required)
        if authority=='none':return self._reply(worker,binding,state,intake.reply)
        state=context(worker,binding,state,dict(authority='none',status='ready_to_publish',city=resolution))
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
        province=intake.city['province']
        same_province=(province is None or _normalize(province) in forms(city['province'],'province'))
        if province_evidence(forms(city['province'],'province'),(text,)) is False:same_province=False
        if old['status']=='resolved' and same and same_province or confirmed:
            return dict(old,status='resolved')
        return None

    @staticmethod
    def _authority(intake,previous,*,current_index=None):
        if intake.intent=='cancel' or intake.publication_hold or NONPERSISTENT.search(intake.current_request):return 'none'
        # Publication still requires a traveler request, not a model label.
        # The semantic request is separate from facts mentioned in consultation.
        explicit=PUBLICATION_REQUEST.search(intake.current_request)is not None
        denied=previous is not None and previous.get('status')in ('discussion','cancelled','ready_to_publish','different_destination')
        fresh_fact=any(ref['source_index']==current_index for ref in intake.sources.get('duration_days',[]))
        current_trip=(intake.city is not None and intake.duration_days is not None and fresh_fact)
        requested=(intake.planning_request_index==current_index and current_index is not None)
        if requested and (explicit or current_trip)and (not denied or explicit):
            return 'save'if intake.intent=='save'else'plan'
        if previous is not None and previous.get('status')in ('needs_city','needs_details','ambiguous','confirmation_required','not_found'):
            return previous['authority']
        return 'none'

    def _clarify(self,worker,binding,state,locale,reply,question_fields,missing,*,arrival=None):
        # Preserve the model's natural wording when it asks exactly what is
        # missing. The host repairs omissions/repeated known fields, not style.
        if set(question_fields)==set(missing):return self._reply(worker,binding,state,reply)
        zh={'city':'想去哪个城市？','duration_days':'你打算玩几天？','start_date':'你打算哪天开始？','party_size':'一共几个人出行？',
            'fixed_items':'固定安排谁参加、哪天以及开始和结束时间分别是什么？'}
        en={'city':'Which city would you like to visit?','duration_days':'For how many days?',
            'start_date':'What date should this trip start?','party_size':'How many people are traveling?',
            'fixed_items':'For the fixed arrangement, who is attending, on which day, and at what start and end times?'}
        if arrival is not None and arrival['state']=='known':
            zh['start_date']='已记录你在'+arrival['value']+'到达，行程也从这天开始吗？'
            en['start_date']='You specified arrival on '+arrival['value']+'. Should the itinerary start on that same day?'
        prompts=zh if locale=='zh'else en
        return self._reply(worker,binding,state,(''if locale=='zh'else' ').join(prompts[field]for field in missing))

    @staticmethod
    def _context(worker,binding,state,value):
        return worker._event(binding,state,'effect_committed',CONTEXT+json.dumps(value,ensure_ascii=False,separators=(',',':')))

    @staticmethod
    def _reply(worker,binding,state,text,*,collect_memory=False):
        state=worker._event(binding,state,'text_delta',text)
        publish_memory=(worker.lio_memory.extract(worker,binding)
                        if collect_memory and worker.lio_memory is not None else None)
        state=worker._event(binding,state,'completed')
        if publish_memory is not None:publish_memory()
        return state

    def _answer(self,worker,binding,state,locale,zh,en):
        return self._reply(worker,binding,state,zh if locale=='zh' else en)
