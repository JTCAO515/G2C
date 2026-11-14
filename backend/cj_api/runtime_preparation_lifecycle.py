"""Original financial interval and native MESSAGE closure for fixture preparation.

This controller journals a read-only start/close around B's native preparation.
It dispatches nothing. Financial coverage is checked against every new attempt
of the original producer scope, rather than inferred from a successful subset.
Manual Trip action and final definition/use publication remain separate proofs.
"""
from hashlib import sha256
import os
from pathlib import Path

from cj_usage.authorization_budget import journal_state
from cj_usage.sublimits import scope_hash
from runtime_adapter.contract import decode,encode,require,Unavailable
from .runtime_private import private_directory,read_private

VERSION='G2C-preparation-lifecycle.1'


class PreparationLifecycle:
    def __init__(self,directory,costs):
        self.directory,self.costs=Path(directory),costs
        with self._directory()as fd:
            info=os.fstat(fd);self.identity=(info.st_dev,info.st_ino)

    def _directory(self):
        return private_directory(self.directory,Unavailable('PREPARATION_LIFECYCLE_DIRECTORY_AUTHORITY'))

    def _identity(self,fd):
        info=os.fstat(fd)
        if(info.st_dev,info.st_ino)!=self.identity:
            raise Unavailable('PREPARATION_LIFECYCLE_DIRECTORY_CHANGED')

    def _guard(self,deadline):
        self.costs._guard(deadline)
        token=self.costs.token_supplier()
        if sha256(token.encode()).hexdigest()!=self.costs.binding.auth_session_id:
            raise Unavailable('PREPARATION_ORIGINAL_SESSION_CHANGED')
        return token

    def _snapshot(self):
        budget=self.costs.originals.budget
        with budget.connect()as db:
            db.execute('BEGIN');budget.require_producer(db)
            count,digest=journal_state(db)
            prefix='g2c1-'+scope_hash(self.costs.binding.scope)+'-'
            # No provider/owner data outside this exact registered scope leaves
            # the original store; the global anchor is only count/hash.
            rows=db.execute('SELECT id,kind,input_sha,state,receipt FROM attempt '
                'WHERE substr(id,1,?)=? ORDER BY id',(len(prefix),prefix)).fetchall()
        return dict(ledger=dict(count=count,sha256=digest),attempts=[dict(
            attempt_id=a,kind=k,input_sha256=i,state=s,
            receipt_sha256=None if r is None else sha256(r.encode()).hexdigest())for a,k,i,s,r in rows])

    def _read(self,name):
        with self._directory()as fd:
            self._identity(fd)
            try:raw=read_private(name,1048576,directory_fd=fd)
            except FileNotFoundError:raise Unavailable('PREPARATION_LIFECYCLE_NOT_RECORDED')from None
        value=decode(raw)
        require(type(value)is dict and encode(value)==raw,'PREPARATION_LIFECYCLE_CANONICAL')
        return value

    def _write(self,name,value):
        with self._directory()as fd:
            self._identity(fd)
            out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
            with os.fdopen(out,'wb')as target:
                target.write(encode(value));target.flush();os.fsync(target.fileno())
            os.fsync(fd)

    def begin(self,*,deadline):
        self._guard(deadline);snapshot=self._snapshot();self._guard(deadline)
        record=dict(version=VERSION,kind='start',binding_sha256=self.costs.binding.key,
            selection_sha256=self.costs.selection_sha256,snapshot=snapshot)
        # Existing or partial starts are never replaced to reset the interval.
        self._write('start.json',record)
        self._guard(deadline)
        return encode(record)

    def _start(self):
        value=self._read('start.json')
        require(set(value)=={'version','kind','binding_sha256','selection_sha256','snapshot'}
            and value['version']==VERSION and value['kind']=='start'
            and value['binding_sha256']==self.costs.binding.key
            and value['selection_sha256']==self.costs.selection_sha256,'PREPARATION_LIFECYCLE_START_BINDING')
        snapshot=value['snapshot']
        require(type(snapshot)is dict and set(snapshot)=={'ledger','attempts'}
            and type(snapshot['attempts'])is list,'PREPARATION_LIFECYCLE_START_FIELDS')
        rows=snapshot['attempts']
        require(all(type(row)is dict and set(row)=={'attempt_id','kind','input_sha256','state','receipt_sha256'}for row in rows)
            and len({row['attempt_id']for row in rows})==len(rows),'PREPARATION_LIFECYCLE_START_FIELDS')
        return value

    def close(self,*,deadline):
        token=self._guard(deadline);start=self._start();before=self._snapshot()
        cost_raw=self.costs.collect(deadline=deadline);cost=decode(cost_raw)
        tails=[]
        for mid in self.costs.message_ids:
            visible_raw=self.costs.originals.visible_original(token,mid);visible=decode(visible_raw)
            require(visible['message_id']==mid,'PREPARATION_LIFECYCLE_MESSAGE_BINDING')
            tails.append(dict(message_id=mid,status=visible['status'],tail=visible['tail'],
                visible_original_sha256=sha256(visible_raw).hexdigest()))
        after=self._snapshot();self._guard(deadline)
        if before['attempts']!=after['attempts']:
            raise Unavailable('PREPARATION_LIFECYCLE_SCOPE_CHANGED')
        old={row['attempt_id']:row for row in start['snapshot']['attempts']}
        current={row['attempt_id']:row for row in after['attempts']}
        if not old.keys()<=current.keys()or any(
                (current[key]['kind'],current[key]['input_sha256'])!=(row['kind'],row['input_sha256'])
                for key,row in old.items()):
            raise Unavailable('PREPARATION_LIFECYCLE_ORIGINAL_HISTORY_CHANGED')
        new_ids=current.keys()-old.keys();selected={row['attempt_id']for row in cost['attempts']}
        missing=sorted(new_ids-selected);outside=sorted(selected-new_ids)
        closed=all(row['status']in('completed','failed','cancelled')
            and row['tail']['delivery_acknowledged']is True
            and not row['tail']['associated_history_jobs']for row in tails)
        record=dict(version=VERSION,kind='close',binding_sha256=self.costs.binding.key,
            start_sha256=sha256(encode(start)).hexdigest(),snapshot=after,cost_inventory=cost,
            message_closure=tails,unmapped_original_attempt_ids=missing,
            selected_attempts_outside_interval=outside,
            coverage='ORIGINAL_SCOPE_FINANCIAL_INTERVAL_AND_DECLARED_MESSAGES',
            evidence_status='COMPLETE'if not missing and not outside and closed
                and cost['accounting_status']=='SETTLED'else'UNKNOWN',
            manual_trip_action_coverage='UNRUN',new_charge_attempts=0)
        self._write('close.json',record)
        return self.read(deadline=deadline)

    def read(self,*,deadline):
        token=self._guard(deadline);start=self._start();record=self._read('close.json')
        require(set(record)=={'version','kind','binding_sha256','start_sha256','snapshot','cost_inventory',
            'message_closure','unmapped_original_attempt_ids','selected_attempts_outside_interval',
            'coverage','evidence_status','manual_trip_action_coverage','new_charge_attempts'}
            and record['version']==VERSION and record['kind']=='close'
            and record['binding_sha256']==self.costs.binding.key
            and record['start_sha256']==sha256(encode(start)).hexdigest(),'PREPARATION_LIFECYCLE_CLOSE_BINDING')
        self.costs.verify_frozen(encode(record['cost_inventory']),deadline=deadline)
        current={row['attempt_id']:row for row in self._snapshot()['attempts']}
        old_ids={row['attempt_id']for row in start['snapshot']['attempts']}
        # Later independent preparations do not rewrite this closed interval.
        for row in record['snapshot']['attempts']:
            actual=current.get(row['attempt_id'])
            if actual is None or (actual['kind'],actual['input_sha256'])!=(row['kind'],row['input_sha256']):
                raise Unavailable('PREPARATION_LIFECYCLE_ORIGINAL_CHANGED')
            if row['attempt_id']not in old_ids and actual!=row:
                raise Unavailable('PREPARATION_LIFECYCLE_ORIGINAL_CHANGED')
        for row in record['message_closure']:
            raw=self.costs.originals.visible_original(token,row['message_id'])
            if sha256(raw).hexdigest()!=row['visible_original_sha256']:
                raise Unavailable('PREPARATION_LIFECYCLE_MESSAGE_CHANGED')
            actual=decode(raw)
            require(row==dict(message_id=actual['message_id'],status=actual['status'],tail=actual['tail'],
                visible_original_sha256=sha256(raw).hexdigest()),'PREPARATION_LIFECYCLE_CLOSURE_INTEGRITY')
        require(tuple(row['message_id']for row in record['message_closure'])==self.costs.message_ids
            and record['coverage']=='ORIGINAL_SCOPE_FINANCIAL_INTERVAL_AND_DECLARED_MESSAGES'
            and record['manual_trip_action_coverage']=='UNRUN'
            and type(record['new_charge_attempts'])is int and record['new_charge_attempts']==0,
            'PREPARATION_LIFECYCLE_COVERAGE')
        new_ids={row['attempt_id']for row in record['snapshot']['attempts']}-old_ids
        selected={row['attempt_id']for row in record['cost_inventory']['attempts']}
        require(record['unmapped_original_attempt_ids']==sorted(new_ids-selected)
            and record['selected_attempts_outside_interval']==sorted(selected-new_ids),
            'PREPARATION_LIFECYCLE_ACCOUNTING_COVERAGE')
        closed=all(row['status']in('completed','failed','cancelled')
            and row['tail']['delivery_acknowledged']is True
            and not row['tail']['associated_history_jobs']for row in record['message_closure'])
        expected='COMPLETE'if new_ids==selected and closed and record['cost_inventory']['accounting_status']=='SETTLED'else'UNKNOWN'
        require(record['evidence_status']==expected,'PREPARATION_LIFECYCLE_STATUS_INTEGRITY')
        self._guard(deadline)
        return encode(record)
