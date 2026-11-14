"""Read original preparation accounting without dispatching or charging it again.

Coverage is the frozen declared MESSAGE list. A preparation controller must prove
that list exhaustive and retain its actual before/after anchors separately.
"""
from hashlib import sha256
import os
from pathlib import Path

from cj_usage.authorization_budget import CNY_SCALE,LIMITS,_price_receipt,journal_state
from runtime_adapter.contract import decode,encode,label,require,Unavailable
from .runtime_private import private_directory,read_private


VERSION='G2C-preparation-cost-inventory.1'
MISSING=frozenset({'ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE','ORIGINAL_METER_UNAVAILABLE',
    'ORIGINAL_METER_ATTEMPT_UNAVAILABLE'})


class PreparationCostInventory:
    def __init__(self,originals,authority,binding,pins,token_supplier,message_ids):
        require(type(message_ids)is tuple and 0<len(message_ids)<=32,'PREPARATION_MESSAGE_SELECTION')
        for mid in message_ids:label(mid)
        require(len(set(message_ids))==len(message_ids),'PREPARATION_MESSAGE_SELECTION')
        self.originals,self.authority,self.binding,self.pins=originals,authority,binding,pins
        self.token_supplier,self.message_ids=token_supplier,message_ids
        self.selection_sha256=sha256(encode(list(message_ids))).hexdigest()

    def _guard(self,deadline):
        self.authority.require(binding=self.binding,pins_sha256=self.pins.key,
            purpose='query',deadline=deadline,read_only=True)
        if(self.originals.budget.ledger_id,self.originals.budget.producer)!=(
                self.binding.ledger_id,self.binding.producer_id):
            raise Unavailable('PREPARATION_ORIGINAL_LEDGER_CHANGED')

    def _anchor(self):
        budget=self.originals.budget
        with budget.connect()as db:
            db.execute('BEGIN');budget.require_producer(db)
            count,digest=journal_state(db)
        return dict(count=count,sha256=digest)

    @staticmethod
    def _component(read):
        try:raw=read()
        except Unavailable as error:
            if str(error)not in MISSING:raise
            return None,None
        return decode(raw),sha256(raw).hexdigest()

    def _read(self,token):
        messages=[];entries=[];missing=[];seen=set()
        for mid in self.message_ids:
            raw=self.originals.inventory(token,mid);inventory=decode(raw)
            require(inventory['message_id']==mid,'PREPARATION_ORIGINAL_MESSAGE_CHANGED')
            messages.append(dict(message_id=mid,run_id=inventory['run_id'],status=inventory['status'],
                inventory_sha256=sha256(raw).hexdigest()))
            for operation in inventory['operations']:
                op=operation['operation_id'];attempt=operation['attempt_id']
                require(attempt not in seen,'PREPARATION_DUPLICATE_ORIGINAL_ATTEMPT');seen.add(attempt)
                # Read the fee even when Meter evidence is missing. No artifact
                # or successful-result filter can drop a failed attempt's cost.
                fee,fee_sha=self._component(lambda:self.originals.fee(token,mid,op))
                meter,meter_sha=self._component(lambda:self.originals.meter(token,mid,op))
                if fee is None:missing.append(dict(attempt_id=attempt,field='financial_original'))
                if meter is None:missing.append(dict(attempt_id=attempt,field='meter_original'))
                if fee is not None:
                    require(fee['attempt_id']==attempt and fee['ledger_id']==self.binding.ledger_id
                        and fee['kind']in LIMITS,'PREPARATION_ORIGINAL_FINANCIAL_BINDING')
                estimate=None if fee is None or fee['state']!='RECEIVED'else _price_receipt(fee['kind'],fee['receipt_utf8'])
                hold=None if fee is None else 0 if estimate is not None else LIMITS[fee['kind']][1]*CNY_SCALE
                settled=(fee is not None and fee['state']=='RECEIVED'and meter is not None
                    and meter['state']=='settled'and meter['receipt']is not None)
                entries.append(dict(message_id=mid,run_id=inventory['run_id'],operation_id=op,
                    attempt_id=attempt,registration_id=operation['registration_id'],kind=operation['kind'],
                    fee_kind=None if fee is None else fee['kind'],financial_original_sha256=fee_sha,
                    meter_original_sha256=meter_sha,financial_state=None if fee is None else fee['state'],
                    meter_state=None if meter is None else meter['state'],accounting_settled=settled,
                    estimated_cny_1e7=estimate,parent_conservative_hold_cny_1e7=hold))
        return dict(messages=messages,attempts=entries,missing=missing)

    def collect(self,*,deadline):
        self._guard(deadline);token=self.token_supplier()
        if sha256(token.encode()).hexdigest()!=self.binding.auth_session_id:
            raise Unavailable('PREPARATION_ORIGINAL_SESSION_CHANGED')
        before=self._anchor();observed=self._read(token)
        if self._read(token)!=observed:raise Unavailable('PREPARATION_ACCOUNTING_SOURCE_CHANGED')
        after=self._anchor();self._guard(deadline)
        entries=observed['attempts']
        return encode(dict(version=VERSION,binding_sha256=self.binding.key,
            declared_message_selection_sha256=self.selection_sha256,
            coverage_scope='DECLARED_PREPARATION_MESSAGES_NOT_WHOLE_LIFECYCLE',
            observed_ledger_before=before,observed_ledger_after=after,**observed,
            totals=dict(attempts=len(entries),settled=sum(e['accounting_settled']for e in entries),
                known_estimated_cny_1e7=sum(e['estimated_cny_1e7']for e in entries if e['estimated_cny_1e7']is not None),
                unpriced_attempts=sum(e['estimated_cny_1e7']is None for e in entries),
                known_parent_conservative_hold_cny_1e7=sum(e['parent_conservative_hold_cny_1e7']for e in entries if e['parent_conservative_hold_cny_1e7']is not None),
                unknown_hold_attempts=sum(e['parent_conservative_hold_cny_1e7']is None for e in entries)),
            accounting_status='SETTLED'if not observed['missing']and all(e['accounting_settled']for e in entries)else'UNKNOWN',
            actual_supplier_paid='UNKNOWN',new_charge_attempts=0))

    def verify_frozen(self,raw,*,deadline):
        """Requalify selected originals without replacing historical anchors.

        Unrelated consumer fees may advance the shared ledger. A transition of
        any selected preparation original instead requires explicit new
        reconciliation; this method never rewrites or recharges it.
        """
        saved=decode(raw)
        require(type(saved)is dict and set(saved)=={'version','binding_sha256',
            'declared_message_selection_sha256','coverage_scope','observed_ledger_before',
            'observed_ledger_after','messages','attempts','missing','totals','accounting_status',
            'actual_supplier_paid','new_charge_attempts'}and encode(saved)==raw,
            'PREPARATION_FROZEN_FIELDS')
        require(saved['version']==VERSION and saved['binding_sha256']==self.binding.key
            and saved['declared_message_selection_sha256']==self.selection_sha256,
            'PREPARATION_FROZEN_BINDING')
        current=decode(self.collect(deadline=deadline))
        for key in ('observed_ledger_before','observed_ledger_after'):
            current[key]=saved[key]
        if encode(current)!=raw:
            raise Unavailable('PREPARATION_FROZEN_SOURCE_CHANGED_RECONCILE_ORIGINAL')
        return raw


class FrozenPreparationCost:
    """One retained preparation-close original; never regenerates on query.

    The controller owns an isolated directory for this fixture revision. A
    partial/unknown write remains there and is query-only; there is no delete,
    reset, settlement retry or financial dispatch in this component.
    """
    def __init__(self,directory,inventory):
        self.directory,self.inventory=Path(directory),inventory
        with self._directory()as fd:
            info=os.fstat(fd);self.identity=(info.st_dev,info.st_ino)

    def _directory(self):
        return private_directory(self.directory,Unavailable('PREPARATION_COST_DIRECTORY_AUTHORITY'))

    def _identity(self,fd):
        info=os.fstat(fd)
        if(info.st_dev,info.st_ino)!=self.identity:
            raise Unavailable('PREPARATION_COST_DIRECTORY_CHANGED')

    def freeze(self,*,deadline):
        raw=self.inventory.collect(deadline=deadline)
        with self._directory()as fd:
            self._identity(fd)
            try:out=os.open('cost.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
            except FileExistsError:pass
            else:
                with os.fdopen(out,'wb')as target:
                    target.write(raw);target.flush();os.fsync(target.fileno())
                os.fsync(fd)
        return self.read(deadline=deadline)

    def read(self,*,deadline):
        with self._directory()as fd:
            self._identity(fd)
            try:raw=read_private('cost.json',1048576,directory_fd=fd)
            except FileNotFoundError:
                raise Unavailable('PREPARATION_COST_NOT_FROZEN')from None
        return self.inventory.verify_frozen(raw,deadline=deadline)
