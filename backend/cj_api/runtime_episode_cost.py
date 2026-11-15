"""Local episode accounting from native DUT, actor and associated background originals.

No dispatch or new ledger. The journal anchor starts before the first original;
coverage requires the exact journal delta and every original ACK/job/attempt.
"""
from dataclasses import asdict
from hashlib import sha256
from decimal import Decimal
from psycopg import Error as DatabaseError

from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_run.core import Denied as RunDenied
from cj_usage.authorization_budget import CNY_SCALE,LIMITS,_price_receipt,canonical
from cj_usage.codec import decode_stored
from cj_usage.metered_exit import BudgetUnknown
from runtime_adapter.contract import Unavailable,decode,encode
from .runtime_preparation_cost import PreparationCostInventory


class BackgroundCostOriginals:
    def __init__(self,jobs,originals):
        self.jobs,self.originals=jobs,originals

    def read(self,token,job_id,attempt_id):
        def read(context):
            store=self.jobs._store(context.scope);record=store.read(job_id,attempt_id)
            if record is None:raise Unavailable('EPISODE_BACKGROUND_ORIGINAL_MISSING')
            matches=[p for p in self.jobs.database.run_context.profiles if p.meter==record.config]
            if len(matches)!=1:raise Unavailable('EPISODE_BACKGROUND_PERIOD_UNAVAILABLE')
            with self.jobs.database.connect(context.scope,usage_profile=matches[0])as db:
                db.execute('SET TRANSACTION READ ONLY')
                row=db.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(record.ledger_scope,)).fetchone()
            meter=None if row is None else decode_stored(row[0],row[1]).attempts.get(record.command.attempt_id)
            try:
                fee=self.originals._financial(record.command.attempt_id)
            except Unavailable as error:
                if str(error)!='ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE':raise
                fee=None
            summary=record.summary()
            financial=None if fee is None else dict(attempt_id=record.command.attempt_id,
                ledger_id=self.originals.budget.ledger_id,kind=fee[0],
                actual_wire_input_sha256=fee[1],state=fee[2],receipt_utf8=fee[3])
            result=encode(dict(original=summary,meter=None if meter is None else asdict(meter),fee=financial))
            if store.read(job_id,attempt_id)!=record:
                raise Unavailable('EPISODE_BACKGROUND_ORIGINAL_CHANGED')
            return result
        try:return self.jobs.boundary.with_history_context(token,read)
        except (AccessBlocked,IdentityChanged):
            raise Unavailable('EPISODE_BACKGROUND_AUTH_UNAVAILABLE')from None
        except (RunDenied,DatabaseError,BudgetUnknown):
            raise Unavailable('EPISODE_BACKGROUND_ORIGINAL_UNAVAILABLE')from None


class EpisodeCostInventory:
    def __init__(self,dut,actor,dut_originals,actor_originals,background,
                 authority,binding,pins,token_supplier,*,deadline,host_unavailable):
        self.dut,self.actor=dut,actor
        self.dut_originals,self.actor_originals=dut_originals,actor_originals
        self.background,self.authority,self.binding,self.pins=background,authority,binding,pins
        self.token_supplier,self.host_unavailable=token_supplier,host_unavailable
        self.last_report=None
        self._guard(deadline)
        if dut.originals or actor.originals:
            raise Unavailable('EPISODE_ACCOUNTING_MUST_START_BEFORE_ORIGINALS')
        self.before=self._journal()

    def _guard(self,deadline):
        self.authority.require(binding=self.binding,pins_sha256=self.pins.key,
            purpose='query',deadline=deadline,read_only=True)
        if (self.dut_originals.budget.ledger_id,self.dut_originals.budget.producer)!=(self.binding.ledger_id,self.binding.producer_id):
            raise Unavailable('EPISODE_ORIGINAL_LEDGER_CHANGED')
        if sha256(self.token_supplier().encode()).hexdigest()!=self.binding.auth_session_id:
            raise Unavailable('EPISODE_ORIGINAL_SESSION_CHANGED')

    def _journal(self):
        budget=self.dut_originals.budget
        with budget.connect()as db:
            db.execute('BEGIN');budget.require_producer(db)
            rows=db.execute('SELECT id,kind,input_sha,state,receipt FROM attempt ORDER BY id').fetchall()
        return dict(rows=rows,anchor=dict(count=len(rows),sha256=sha256(canonical(rows)).hexdigest()))

    def _selection(self):
        return (tuple(x['step_id']for x in self.dut.originals),
                tuple(x.argument.binding.message_id for x in self.actor.originals))

    def _role(self,reader,mids,role,deadline):
        if not mids:return dict(attempts=[],missing=[])
        value=decode(PreparationCostInventory(reader,self.authority,self.binding,self.pins,
            self.token_supplier,mids).collect(deadline=deadline))
        for row in value['attempts']:row['role']=role
        for message in value['messages']:
            if message['status']not in('completed','failed','cancelled','context_invalid','budget_exhausted'):
                value['missing'].append(dict(message_id=message['message_id'],field='native_terminal_run'))
        return value

    def _read(self,selection,deadline):
        token=self.token_supplier();dut_ids,actor_ids=selection
        reports=[self._role(self.dut_originals,dut_ids,'dut',deadline),
                 self._role(self.actor_originals,actor_ids,'actor',deadline)]
        entries=[row for report in reports for row in report['attempts']]
        missing=[row for report in reports for row in report['missing']]
        tails=[decode(self.dut_originals.cost_tail(token,mid))for mid in dut_ids]
        jobs={}
        for tail in tails:
            if tail['delivery_acknowledged']is not True:
                missing.append(dict(message_id=tail['message_id'],field='delivery_acknowledgement'))
            for job in tail['associated_history_jobs']:
                key=(job['job_id'],job['attempt_id'])
                if key in jobs and jobs[key]!=job:
                    raise Unavailable('EPISODE_HISTORY_JOB_CHANGED')
                jobs[key]=job
        for key,job in sorted(jobs.items()):
            try:value=decode(self.background.read(token,*key))
            except Unavailable as error:
                if str(error)!='EPISODE_BACKGROUND_ORIGINAL_MISSING':raise
                missing.append(dict(job_id=key[0],attempt_id=key[1],field='background_original'));continue
            original,fee,meter=value['original'],value['fee'],value['meter']
            attempt=original['meter_attempt_id']
            if fee is not None and (fee['attempt_id']!=attempt or fee['ledger_id']!=self.binding.ledger_id or fee['kind']not in LIMITS):
                raise Unavailable('EPISODE_BACKGROUND_FEE_BINDING_CHANGED')
            estimate=None if fee is None or fee['state']!='RECEIVED'else _price_receipt(fee['kind'],fee['receipt_utf8'])
            hold=None if fee is None else 0 if estimate is not None else LIMITS[fee['kind']][1]*CNY_SCALE
            settled=(fee is not None and fee['state']=='RECEIVED'and meter is not None and meter['state']=='settled'and meter['receipt']is not None)
            entries.append(dict(role='background',job_id=key[0],job_attempt_id=key[1],
                attempt_id=attempt,operation_id=original['meter_operation_id'],
                registration_id=original['registration_id'],accounting_settled=settled,
                financial_state=None if fee is None else fee['state'],
                meter_state=None if meter is None else meter['state'],
                estimated_cny_1e7=estimate,parent_conservative_hold_cny_1e7=hold,
                original_sha256=sha256(encode(value)).hexdigest()))
            if fee is None or meter is None or original['state']not in('completed','cancelled','budget_exhausted')or job['state']not in('completed','cancelled'):
                missing.append(dict(job_id=key[0],attempt_id=key[1],field='background_completion_or_accounting'))
        ids=[row['attempt_id']for row in entries]
        if len(set(ids))!=len(ids):raise Unavailable('EPISODE_DUPLICATE_ORIGINAL_ATTEMPT')
        return dict(attempts=entries,missing=missing,tails=tails)

    def collect(self,*,deadline):
        self._guard(deadline);selection=self._selection();observed=self._read(selection,deadline)
        if self._read(selection,deadline)!=observed or self._selection()!=selection:
            raise Unavailable('EPISODE_ACCOUNTING_SOURCE_CHANGED')
        after=self._journal();self._guard(deadline)
        before_rows={row[0]:row for row in self.before['rows']};after_rows={row[0]:row for row in after['rows']}
        ids={row['attempt_id']for row in observed['attempts']}
        delta=set(after_rows)-set(before_rows)
        covered=(delta==ids and all(after_rows.get(k)==v for k,v in before_rows.items()))
        missing=observed['missing']
        if not covered:missing.append(dict(field='episode_journal_delta_coverage'))
        entries=observed['attempts'];complete=not missing
        priced=all(row['estimated_cny_1e7']is not None for row in entries)
        holds=all(row['parent_conservative_hold_cny_1e7']is not None for row in entries)
        estimated=sum(row['estimated_cny_1e7']or 0 for row in entries)
        conservative=estimated+sum(row['parent_conservative_hold_cny_1e7']or 0 for row in entries)
        money=lambda n:format(Decimal(n)/Decimal(CNY_SCALE),'f')
        result=dict(version='G2C-simulator-episode-cost.1',binding_sha256=self.binding.key,
            episode_before=self.before['anchor'],episode_after=after['anchor'],
            coverage_scope='NATIVE_DUT_ACTOR_ASSOCIATED_BACKGROUND_AND_JOURNAL_DELTA',
            **observed,coverage_status='COMPLETE'if complete else'UNKNOWN',
            accounting_status='SETTLED'if complete and all(r['accounting_settled']for r in entries)else'UNKNOWN',
            cost=dict(conservative_cny=money(conservative)if complete and holds else None,
                token_estimate_cny=money(estimated)if complete and priced else None,actual_paid_cny=None),
            known_estimated_cny_1e7=estimated,known_conservative_cny_1e7=conservative,
            actual_supplier_paid='UNKNOWN',new_charge_attempts=0)
        self.last_report=result
        return result

    def __call__(self):
        try:return self.collect(deadline=self.actor.clock()+30)['cost']
        except Unavailable as error:
            raise self.host_unavailable('original episode accounting unavailable; query only')from error
