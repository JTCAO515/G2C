"""Protected dynamic App-smoke originals and observed financial reconciliation.

No sends, account/limit changes or alternative authority. A control claim is
joined to the genuine receipt inside the existing MESSAGE history boundary.
"""
from dataclasses import asdict
from hashlib import sha256
import json
import re
import os

from cj_run.core import Binding
from cj_message.demo_dialogue import DialogueMessage
from cj_usage.authorization_budget import canonical,CNY_SCALE,LIMITS,_price_receipt,journal_state
from cj_api.runtime_private import read_private
from runtime_adapter.contract import Unavailable,decode


class SmokeOriginals:
    def __init__(self,controls,originals):
        self.controls,self.originals=controls,originals
        self.native_query=originals.query_original
        originals.query_original=self.query

    def query(self,context,mid):
        original=self.native_query(context,mid)
        claim=self.controls.claim(context.scope,mid)
        if original is None or claim is None:raise Unavailable('APP_SMOKE_ORIGINAL_UNAVAILABLE')
        r=original.receipt;b=Binding(context.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        if (asdict(b)!=claim['binding']or r.input_sha256!=claim['canonical_sha256']or
                sha256(original.raw).hexdigest()!=claim['canonical_sha256']):
            raise Unavailable('APP_SMOKE_ORIGINAL_BINDING_CHANGED')
        return original

    def _outer(self,scope,original,source):
        claim=self.controls.claim(scope,original.receipt.message_id)
        if claim is None:raise Unavailable('APP_SMOKE_ORIGINAL_CLAIM_MISSING')
        identity=sha256(canonical([scope,original.receipt.message_id,claim['input_sha256']])).hexdigest()
        with self.controls.directory()as directory:
            try:receipt=decode(read_private(identity+'.receipt.json',16384,directory_fd=directory))
            except FileNotFoundError:raise Unavailable('APP_SMOKE_HTTP_OUTER_PENDING')from None
            if receipt.get('status')!='CAPTURED':raise Unavailable('APP_SMOKE_HTTP_OUTER_CAPTURE_UNKNOWN')
            raw=read_private(identity+'.json',65536,directory_fd=directory)
        data=decode(raw)
        if (receipt.get('version')!='G2C-App-smoke-outer-receipt.1'or receipt.get('status')!='CAPTURED'
                or receipt.get('sha256')!=sha256(raw).hexdigest()
                or receipt.get('file')!=identity+'.json'
                or receipt.get('policy_sha256')!=self.controls.window['policy_sha256']
                or data.get('version')!='G2C-App-smoke-outer.1'
                or data.get('source_commit')!=self.controls.policy['source_commit']
                or data.get('policy_sha256')!=self.controls.window['policy_sha256']
                or data.get('binding')!=claim['binding']
                or data.get('canonical_sha256')!=claim['canonical_sha256']
                or data.get('input_sha256')!=claim['input_sha256']
                or type(data.get('outer_utf8'))is not str
                or sha256(data['outer_utf8'].encode()).hexdigest()!=claim['input_sha256']):
            raise Unavailable('APP_SMOKE_HTTP_OUTER_PROOF_CHANGED')
        routes={'/v1/lio/messages':'LIO-message.1','/v2/lio/messages':'LIO-message.2'}
        if data.get('method')!='POST'or data.get('route')not in routes or data.get('protocol')!=routes[data['route']]:
            raise Unavailable('APP_SMOKE_HTTP_ROUTE_CHANGED')
        command=DialogueMessage.parse(data['outer_utf8'].encode(),version=data['protocol'])
        inner=json.loads(original.raw)
        slot=next(x for x in self.controls.policy['slots']if x['slot_id']==claim['slot_id'])
        if(command.id!=original.receipt.message_id or command.text!=inner['text']
                or(command.locale,command.protocol)!=(slot['locale'],slot['protocol'])
                or not self.controls.permits(scope,command)):
            raise Unavailable('APP_SMOKE_HTTP_INPUT_CHANGED')
        self.controls.guard()
        return data

    def outer(self,token,mid):
        return self.originals._read(token,mid,lambda scope,original,source:canonical(self._outer(scope,original,source)))

    def message(self,token,mid):
        def project(scope,original,source):
            claim=self.controls.claim(scope,mid);outer=self._outer(scope,original,source)
            text=''.join(value for _,kind,value in source[1]if kind=='text_delta')
            r=original.receipt
            result=dict(message_id=mid,conversation_id=r.conversation_id,generation=r.generation,
                run_id=r.run_id,sequence=r.sequence,status=source[0][0],
                input_sha256=claim['input_sha256'],canonical_sha256=claim['canonical_sha256'],
                text=json.loads(original.raw)['text'],locale=DialogueMessage.parse(
                    outer['outer_utf8'].encode(),version=outer['protocol']).locale,
                answer=text,answer_sha256=sha256(text.encode()).hexdigest(),
                protocol=outer['protocol'],protocol_source='actual HTTP bytes plus native outer digest',
                producer_return=claim['producer_return'])
            return canonical(result)
        return self.originals._read(token,mid,project)

    def checkpoint(self):
        """Original C-line financial rows; a snapshot is not lifecycle closure."""
        budget=self.originals.budget
        with budget.connect()as db:
            db.execute('BEGIN');budget.require_producer(db)
            count,digest=journal_state(db)
            rows=db.execute('SELECT a.id,a.kind,a.input_sha,a.state,a.receipt FROM attempt a '
                "JOIN attempt_sublimit s ON s.attempt_id=a.id WHERE s.line='C' ORDER BY a.id").fetchall()
        return dict(ledger_id=budget.ledger_id,producer_id=budget.producer,
                    anchor=dict(count=count,sha256=digest),c_rows=[list(row)for row in rows])

    def _http_view(self,token):
        def project(context):
            scope=context.scope
            if scope not in self.controls.scopes:raise Unavailable('APP_SMOKE_HTTP_OWNER_CHANGED')
            with self.controls.directory()as directory:
                try:raw=read_private('http-attempts.jsonl',16*1024*1024,directory_fd=directory)
                except FileNotFoundError:raw=b''
                try:gap=decode(read_private('http-coverage-lost.json',16384,directory_fd=directory))
                except FileNotFoundError:gap=None
                if gap is not None and gap!=dict(version='G2C-App-smoke-HTTP-gap.1',policy_sha256=self.controls.window['policy_sha256']):
                    raise Unavailable('APP_SMOKE_HTTP_GAP_MARKER_CHANGED')
                incomplete=gap is not None or len(raw)>16*1024*1024-4096
                files=[]
                scope_hash=sha256(scope.encode()).hexdigest()
                for name in sorted(os.listdir(directory)):
                    if not name.endswith('.read.json.receipt'):continue
                    name=name.removesuffix('.receipt')
                    header=decode(read_private(name,600000,directory_fd=directory))
                    if header.get('scope_sha256')==scope_hash:files.append(name)
            lines=[decode(line)for line in raw.splitlines()]
            if any(x.get('policy_sha256')!=self.controls.window['policy_sha256']for x in lines):
                raise Unavailable('APP_SMOKE_HTTP_POLICY_CHANGED')
            raw=b''.join(canonical(row)+b'\n'for row in lines if row['scope_sha256']==scope_hash)
            return dict(log_utf8=raw.decode(),log_sha256=sha256(raw).hexdigest(),read_files=files,coverage_lost=incomplete)
        return self.originals.boundary.with_history_context(token,project)

    def http_checkpoint(self,token):
        value=self._http_view(token)
        raw=value['log_utf8'].encode()
        # The immutable prefix fence is small even after many actual polls.
        # Publication filenames are not request/step evidence.
        return dict(log_bytes=len(raw),log_sha256=sha256(raw).hexdigest())

    def http_observed(self,token,before):
        current=self._http_view(token);raw=current['log_utf8'].encode()
        offset=before['log_bytes']
        if len(raw)<offset or sha256(raw[:offset]).hexdigest()!=before['log_sha256']:
            raise Unavailable('APP_SMOKE_HTTP_LOG_REWRITTEN')
        def project(context):
            scope_hash=sha256(context.scope.encode()).hexdigest()
            rows=[decode(line)for line in raw[offset:].splitlines()]
            rows=[x for x in rows if x['scope_sha256']==scope_hash]
            return rows
        rows=self.originals.boundary.with_history_context(token,project)
        starts={row['exchange_id']:row for row in rows if row['method']=='GET'and row['phase']=='started'}
        finishes={row['exchange_id']:row for row in rows if row['method']=='GET'and row['phase']=='finished'}
        reads=[]
        for name in current['read_files']:
            with self.controls.directory()as directory:
                data_raw=read_private(name,600000,directory_fd=directory)
                try:receipt=decode(read_private(name+'.receipt',16384,directory_fd=directory))
                except FileNotFoundError:continue
            data=decode(data_raw)
            exchange=data.get('exchange_id')
            if exchange not in starts:continue
            finish=finishes.get(exchange);start=starts[exchange]
            if(finish is None or finish.get('route')!=data.get('route')or start.get('route')!=data.get('route')
                    or finish.get('selector')!=data.get('selector')or finish.get('status')!=200
                    or finish.get('body_fully_observed')is not True
                    or finish.get('response_sha256')!=data.get('response_sha256')):
                raise Unavailable('APP_SMOKE_ACTUAL_GET_EXCHANGE_CHANGED')
            def read(context):
                if data.get('scope_sha256')!=sha256(context.scope.encode()).hexdigest():return None
                if (data.get('version')!='G2C-App-smoke-read.1'or data.get('method')!='GET'or
                        data.get('policy_sha256')!=self.controls.window['policy_sha256']or
                        data.get('source_commit')!=self.controls.policy['source_commit']or
                        data.get('route')not in('/v1/lio/timeline','/v2/lio/timeline','/v2/lio/messages')or
                        receipt.get('version')!='G2C-App-smoke-read-receipt.1'or receipt.get('status')!='CAPTURED'or
                        receipt.get('source_commit')!=self.controls.policy['source_commit']or
                        receipt.get('policy_sha256')!=self.controls.window['policy_sha256']or
                        receipt.get('sha256')!=sha256(data_raw).hexdigest()or receipt.get('file')!=name or
                        sha256(data['response_utf8'].encode()).hexdigest()!=data['response_sha256']):
                    raise Unavailable('APP_SMOKE_ACTUAL_HTTP_READ_CHANGED')
                b=Binding(**data['binding']);original=self.query(context,b.message_id)
                r=original.receipt
                if (context.scope,r.conversation_id,r.generation,r.run_id,r.sequence)!=(
                        b.scope,b.conversation_id,b.generation,b.run_id,b.message_sequence):
                    raise Unavailable('APP_SMOKE_HTTP_READ_ANCHOR_CHANGED')
                return dict(data,artifact_sha256=sha256(data_raw).hexdigest(),artifact_file=name)
            result=self.originals.boundary.with_history_context(token,read)
            if result is not None:reads.append(result)
        self.controls.guard()
        unknown=[x['exchange_id']for x in rows if x['method']=='GET'and x['phase']=='capture_result'
                 and x['exchange_id']in starts and x.get('capture_status')=='UNKNOWN']
        outcomes={x['exchange_id']for x in rows if x['method']=='GET'and x['phase']=='capture_result'}
        pending=sorted(set(starts)-outcomes)
        observed_posts=sum(x['method']=='POST'and x['phase']=='started'for x in rows)
        return dict(post_count=None if current['coverage_lost']else observed_posts,
                    observed_post_count=observed_posts,http_coverage='UNKNOWN'if current['coverage_lost']else'OBSERVED',
                    post_exchanges=[x for x in rows if x['method']=='POST'],
                    read_exchanges=[x for x in rows if x['method']=='GET'],unknown_read_exchanges=unknown,
                    pending_read_exchanges=pending,http_coverage_lost=current['coverage_lost'],
                    read_coverage='UNKNOWN'if unknown or current['coverage_lost']else'PENDING'if pending else'OBSERVED',
                    actual_reads=reads,checkpoint=dict(log_bytes=len(raw),log_sha256=sha256(raw).hexdigest()))

    def accounting(self,token,mid,before,*,background_before,background_after):
        """Use all original ops, including failed/UNKNOWN, with exact C delta.

        The supplied background snapshots must be obtained by the qualified
        same-owner state reader; a changed job set remains UNKNOWN here. A
        future actor/native4 path needs its own actual lifecycle qualification.
        """
        native=self.originals
        inventory=decode(native.inventory(token,mid));tail=decode(native.cost_tail(token,mid))
        rows=[];missing=[];seen=set()
        for operation in inventory['operations']:
            op=operation['operation_id'];attempt=operation['attempt_id']
            if attempt in seen:raise Unavailable('APP_SMOKE_DUPLICATE_OPERATION_ATTEMPT')
            seen.add(attempt)
            try:fee=decode(native.fee(token,mid,op))
            except Unavailable as error:
                if str(error)!='ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE':raise
                if operation['registration_id']=='tool.visitor_fact':
                    # Registered local knowledge has no paid supplier attempt.
                    meter=decode(native.meter(token,mid,op))
                    if meter['state']!='settled':missing.append(dict(operation_id=op,field='local_fact_meter'))
                    continue
                missing.append(dict(operation_id=op,field='financial_original'));continue
            meter=decode(native.meter(token,mid,op));command=meter['command']
            if (fee['attempt_id']!=attempt or fee['ledger_id']!=native.budget.ledger_id or
                    (command['attempt_id'],command['operation_id'],command['run_id'])!=(attempt,op,inventory['run_id'])):
                raise Unavailable('APP_SMOKE_FINANCIAL_BINDING_CHANGED')
            if meter['state']!='settled'or meter['receipt']is None or fee['state']!='RECEIVED':
                missing.append(dict(operation_id=op,field='unsettled_original'))
            kind=fee['kind']
            if kind not in LIMITS:raise Unavailable('APP_SMOKE_UNKNOWN_FINANCIAL_KIND')
            if (command['kind']in('model','memory'))!=(kind=='model'):
                raise Unavailable('APP_SMOKE_FINANCIAL_KIND_CHANGED')
            receipt=None if fee['receipt_utf8']is None else decode(fee['receipt_utf8'])
            estimate=None if fee['state']!='RECEIVED'else _price_receipt(kind,fee['receipt_utf8'])
            charged=LIMITS[kind][1]*CNY_SCALE if estimate is None else estimate
            if type(fee['actual_wire_input_sha256'])is not str or re.fullmatch('[0-9a-f]{64}',fee['actual_wire_input_sha256'])is None:
                raise Unavailable('APP_SMOKE_ORIGINAL_WIRE_DIGEST_MISSING')
            rows.append(dict(ledger_id=fee['ledger_id'],attempt_id=attempt,operation_id=op,
                kind=kind,state=fee['state'],conservative_units=charged,
                actual_wire_input_sha256=fee['actual_wire_input_sha256'],native_binding_verified=True,
                receipt=receipt,priceable_tool_units=estimate if kind!='model'else None))
        def claim(context):
            value=self.controls.claim(context.scope,mid)
            if value is None:raise Unavailable('APP_SMOKE_ORIGINAL_CLAIM_MISSING')
            return value
        original_claim=native.boundary.with_history_context(token,claim)
        witness=original_claim['producer_return']
        if witness is None or witness['status']!=inventory['status']or tail['delivery_acknowledged']is not True:
            missing.append(dict(field='native_producer_return'))
        if any(x['state']not in('completed','cancelled')for x in tail['associated_history_jobs']):
            missing.append(dict(field='memory_history_producer_not_closed'))
        if background_before!=background_after:
            missing.append(dict(field='background_originals_changed_requires_full_native_reader'))
        after=self.checkpoint()
        if(before['ledger_id'],before['producer_id'])!=(after['ledger_id'],after['producer_id']):
            raise Unavailable('APP_SMOKE_ORIGINAL_LEDGER_CHANGED')
        old={r[0]:r for r in before['c_rows']};new={r[0]:r for r in after['c_rows']}
        financial_ids={r['attempt_id']for r in rows}
        if set(new)-set(old)!=financial_ids or any(new.get(k)!=v for k,v in old.items()):
            missing.append(dict(field='exact_C_financial_delta_coverage'))
        self.controls.guard()
        return dict(coverage='complete'if not missing else'UNKNOWN',
            producer_closure_verified=not missing,closure_ref=None if witness is None else sha256(canonical(
                dict(claim=original_claim,tail=tail,before=before,after=after))).hexdigest(),
            missing=missing,attempts=rows,ledger_before=before['anchor'],ledger_after=after['anchor'],
            actual_paid_cny=None,actual_paid_status='UNKNOWN_NO_INVOICE')
