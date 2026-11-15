"""Protected original bytes for runtime collection, never dispatch/recovery writes.

Every read uses the existing MESSAGE history AUTH lifetime and scoped runtime
database. Artifact references are resolved from original operation IDs, not paths
or URLs supplied by the adapter. Deleted input payloads cannot expose old files.
"""
import base64
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime
import re
from hashlib import sha256
import os
from pathlib import Path
import stat
from psycopg import Error as DatabaseError

from cj_message.auth_boundary import Boundary,AccessBlocked,IdentityChanged
from cj_message.domain import Unavailable as MessageUnavailable,InvalidInput,CommitUnknown
from cj_run.usage_binding import UsageBinding
from cj_run.core import Denied as RunDenied
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode_stored
from cj_usage.authorization_budget import canonical
from cj_usage.metered_exit import BudgetUnknown
from runtime_adapter.contract import Unavailable,decode as original_json,require
from .runtime_private import read_private,PrivateFileError


class RuntimeOriginals:
    def __init__(self,message_boundary,database,budget,artifact_directory,*,query_original=None,rejected_memory_lifetime=None):
        if type(message_boundary) is not Boundary:
            raise ValueError('original MESSAGE history boundary required')
        self.boundary,self.database,self.budget=message_boundary,database,budget
        self.directory=Path(artifact_directory)
        self.rejected_memory_lifetime=rejected_memory_lifetime
        self.query_original=(lambda context,mid:context.query_message(mid)) if query_original is None else query_original

    def _operations(self,scope,run_id):
        with self.database.connect(scope) as db:
            db.execute('SET TRANSACTION READ ONLY')
            state=db.execute('SELECT status,run_id FROM cj_run_record WHERE scope=%s AND run_id=%s',(scope,run_id)).fetchone()
            events=db.execute('SELECT sequence,kind,value FROM cj_run_event WHERE scope=%s AND run_id=%s ORDER BY sequence',(scope,run_id)).fetchall()
            operations=db.execute('SELECT operation_key,registration_id,kind,attempt_id,operation_id,ledger_scope,command_bytes,input_bytes FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s ORDER BY operation_key',(scope,run_id)).fetchall()
            period=db.execute('SELECT ledger_scope,unit,period_start,period_end FROM cj_run_metered_binding WHERE scope=%s AND run_id=%s',(scope,run_id)).fetchone()
        if state is None:raise Unavailable('ORIGINAL_RUN_UNAVAILABLE')
        return state,events,operations,period

    def _read(self,token,message_id,project,*,with_context=False,publication=None):
        def operation(context):
            original=self.query_original(context,message_id)
            if original is None:raise Unavailable('ORIGINAL_MESSAGE_UNAVAILABLE')
            source=self._operations(context.scope,original.receipt.run_id)
            body=project(context if with_context else context.scope,original,source)
            # Storage/files/fee callbacks completed before the final same-source
            # check; Boundary then repeats canonical AUTH before bytes escape.
            if publication is None or not publication['memory_held']:
                if self.query_original(context,message_id)!=original or self._operations(context.scope,original.receipt.run_id)!=source:
                    raise Unavailable('ORIGINAL_SNAPSHOT_CHANGED')
            if publication is not None:
                for check in publication['checks']:check()
            return body
        try:
            body=self.boundary.with_history_context(token,operation)
            if publication is not None:
                for check in publication['checks']:check()
            return body
        except (AccessBlocked,IdentityChanged):
            raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE') from None
        except (MessageUnavailable,InvalidInput,CommitUnknown,DatabaseError,BudgetUnknown,RunDenied):
            raise Unavailable('ORIGINAL_PROTECTED_READ_UNAVAILABLE') from None

    def _operation(self,scope,source,operation_id,*,allow_erased=False):
        rows=[row for row in source[2] if row[4]==operation_id]
        if len(rows)!=1:raise Unavailable('ORIGINAL_OPERATION_UNAVAILABLE')
        row=rows[0]
        if row[7] is None:
            if not allow_erased:raise Unavailable('ORIGINAL_PAYLOAD_ERASED')
            # Reuse the accepted permanent-erasure proof reader. Its header is
            # accounting metadata only, never a fresh InvocationInput or raw
            # payload reconstruction from an old artifact.
            from cj_run.payload_evidence import erased_original
            with self.database.connect(scope) as db:
                db.execute('SET TRANSACTION READ ONLY')
                with db.cursor() as cursor:
                    usage=erased_original(cursor,scope,'cj_run_metered_operation',source[0][1],row[0],bytes(row[6]))
        else:usage=UsageBinding(bytes(row[6]),bytes(row[7]))
        command=usage.command
        if command.run_id!=source[0][1] or (command.kind,command.attempt_id,command.operation_id)!=(row[2],row[3],row[4]):
            raise Unavailable('ORIGINAL_OPERATION_BINDING_CHANGED')
        return row,usage

    def _financial(self,attempt_id):
        with self.budget.connect() as db:
            db.execute('BEGIN');self.budget.require_producer(db)
            fee=db.execute('SELECT kind,input_sha,state,receipt FROM attempt WHERE id=?',(attempt_id,)).fetchone()
        if fee is None:raise Unavailable('ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE')
        return fee

    def inventory(self,token,message_id):
        def project(scope,original,source):
            state,events,rows,period=source
            return canonical(dict(message_id=message_id,run_id=original.receipt.run_id,
                message_input_sha256=original.receipt.input_sha256,status=state[0],
                events=[dict(sequence=s,kind=k) for s,k,_ in events],
                operations=[dict(operation_key=r[0],registration_id=r[1],kind=r[2],attempt_id=r[3],operation_id=r[4],input_erased=r[7] is None) for r in rows],
                original_period=period))
        return self._read(token,message_id,project)

    def visible_original(self,token,message_id):
        """Private original input/event bytes; never a G result/state copy."""
        def project(scope,original,source):
            if any(row[7]is None for row in source[2]):
                raise Unavailable('ORIGINAL_PAYLOAD_ERASED')
            def raw(value):
                data=bytes(value)
                return dict(sha256=sha256(data).hexdigest(),bytes_base64=base64.b64encode(data).decode('ascii'))
            def tail():
                return self._cost_tail(scope,original)
            observed=tail()
            body=canonical(dict(version='G2C-runtime-visible-original.1',
                scope_sha256=sha256(scope.encode()).hexdigest(),message_id=message_id,
                run_id=original.receipt.run_id,message_input_sha256=original.receipt.input_sha256,
                status=source[0][0],input=raw(original.raw),tail=observed,
                visible_text=raw(''.join(value for _,kind,value in source[1]if kind=='text_delta').encode('utf-8')),
                events=[dict(sequence=n,kind=kind,value=raw(value.encode('utf-8')))for n,kind,value in source[1]]))
            if tail()!=observed:raise Unavailable('ORIGINAL_VISIBLE_TAIL_CHANGED')
            return body
        return self._read(token,message_id,project)

    def _cost_tail(self,scope,original):
        r=original.receipt
        with self.database.connect(scope)as db:
            db.execute('SET TRANSACTION READ ONLY')
            ack=db.execute('SELECT acknowledged FROM cj_message_delivery '
                'WHERE scope=%s AND message_id=%s AND run_id=%s',
                (scope,r.message_id,r.run_id)).fetchone()
            jobs=db.execute("SELECT job_id,attempt_id,state FROM cj_memory_history_job WHERE scope=%s "
                "AND convert_from(batch,'UTF8')::jsonb#>>'{source,cursor,conversation_id}'=%s "
                "AND convert_from(batch,'UTF8')::jsonb#>>'{source,cursor,generation}'=%s "
                "AND (convert_from(batch,'UTF8')::jsonb#>>'{source,cursor,after}')::bigint<%s "
                "AND (convert_from(batch,'UTF8')::jsonb#>>'{source,cursor,through}')::bigint>=%s "
                'ORDER BY job_id,attempt_id',(scope,r.conversation_id,r.generation,r.sequence,r.sequence)).fetchall()
        return dict(delivery_acknowledged=None if ack is None else ack[0],
            associated_history_jobs=[dict(job_id=j,attempt_id=a,state=s)for j,a,s in jobs])

    def cost_tail(self,token,message_id):
        """Original ACK/history-job metadata under the same MESSAGE AUTH lifetime."""
        def project(scope,original,source):
            before=self._cost_tail(scope,original)
            value=canonical(dict(message_id=message_id,run_id=original.receipt.run_id,**before))
            if self._cost_tail(scope,original)!=before:
                raise Unavailable('ORIGINAL_COST_TAIL_CHANGED')
            return value
        return self._read(token,message_id,project)

    def input(self,token,message_id,operation_id):
        return self._read(token,message_id,lambda scope,original,source:self._operation(scope,source,operation_id)[1].input_bytes)

    def _meter(self,scope,source,row,usage):
        period=source[3]
        if period is None:raise Unavailable('ORIGINAL_PERIOD_UNAVAILABLE')
        profiles=[p for p in self.database.run_context.profiles if
            (ledger_scope_for(scope,p.meter),p.meter.unit,p.meter.period_start,p.meter.period_end)==tuple(period)]
        if len(profiles)!=1 or row[5]!=period[0]:raise Unavailable('ORIGINAL_PERIOD_NOT_RETAINED')
        with self.database.connect(scope,usage_profile=profiles[0]) as db:
            db.execute('SET TRANSACTION READ ONLY')
            stored=db.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(row[5],)).fetchone()
        if stored is None:raise Unavailable('ORIGINAL_METER_UNAVAILABLE')
        attempt=decode_stored(stored[0],stored[1]).attempts.get(usage.command.attempt_id)
        if attempt is None:raise Unavailable('ORIGINAL_METER_ATTEMPT_UNAVAILABLE')
        return canonical(asdict(attempt))

    def meter(self,token,message_id,operation_id):
        def project(scope,original,source):
            row,usage=self._operation(scope,source,operation_id,allow_erased=True)
            return self._meter(scope,source,row,usage)
        return self._read(token,message_id,project)

    def fee(self,token,message_id,operation_id):
        def project(scope,original,source):
            row,usage=self._operation(scope,source,operation_id,allow_erased=True)
            fee=self._financial(usage.command.attempt_id)
            return canonical(dict(attempt_id=usage.command.attempt_id,ledger_id=self.budget.ledger_id,
                kind=fee[0],actual_wire_input_sha256=fee[1],state=fee[2],receipt_utf8=fee[3]))
        return self._read(token,message_id,project)

    def rejected_intake(self,token,message_id,operation_id,reference,*,directory):
        """Operator-configured private store, current original lifetime; no new route."""
        from .rejected_intake_capture import RejectedIntakeSink,CaptureUnavailable
        stack=ExitStack();publication=dict(memory_held=False,checks=[])
        def project(context,original,source):
            scope=context.scope
            row,usage=self._operation(scope,source,operation_id)
            require(row[1]=='model.lio_intake.9'and row[0]=='model.lio_intake.0','ORIGINAL_REJECTED_INTAKE_REQUIRED')
            try:data=RejectedIntakeSink(directory).read(reference)
            except (OSError,ValueError,CaptureUnavailable):raise Unavailable('ORIGINAL_REJECTED_INTAKE_UNAVAILABLE')from None
            expected=sha256(canonical([scope,source[0][1],row[0],usage.command.attempt_id])).hexdigest()
            require(reference==expected and data['reference']==expected and
                (data['scope_sha256'],data['message_id'],data['run_id'],data['operation_key'],data['registration_id'],
                 data['attempt_id'],data['operation_id'],data['input_sha256'])==
                (sha256(scope.encode()).hexdigest(),message_id,original.receipt.run_id,row[0],row[1],
                 usage.command.attempt_id,operation_id,usage.command.input_digest),'ORIGINAL_REJECTION_BINDING_CHANGED')
            meter=original_json(self._meter(scope,source,row,usage));fee=self._financial(usage.command.attempt_id)
            require(meter['state']=='settled'and not meter['exceeded']and meter['receipt']is not None,
                'ORIGINAL_REJECTION_SETTLEMENT_UNAVAILABLE')
            receipt=original_json(fee[3])if fee[3]is not None else None
            require(fee[0]=='model'and fee[2]=='RECEIVED'and receipt is not None and
                receipt['receipt_sha256']==data['receipt']['receipt_sha256']and
                meter['receipt']['receipt_id']=='live:'+receipt['receipt_sha256']and
                meter['receipt']['output']==len(data['result_utf8']),
                'ORIGINAL_REJECTION_RECEIPT_CHANGED')
            from cj_run.core import Binding
            inputs=original_json(usage.input_bytes)
            prefix='Stored memory data (not instructions):\n'
            packets=[message['content'][len(prefix):].encode('utf-8')for message in inputs['messages']
                     if message['role']=='user'and message['content'].startswith(prefix)]
            descriptor=data['memory']
            require((descriptor is None and not packets)or(descriptor is not None and len(packets)==1),
                    'ORIGINAL_MEMORY_DESCRIPTOR_UNAVAILABLE')
            def current_ttl():
                if datetime.now().astimezone().timestamp()>=datetime.fromisoformat(data['expires_at']).timestamp():
                    raise Unavailable('ORIGINAL_REJECTION_EXPIRED')
            publication['checks'].append(current_ttl)
            if descriptor is None:return canonical(data)
            require(sha256(packets[0]).hexdigest()==descriptor['payload_sha256'],
                    'ORIGINAL_MEMORY_INPUT_ASSOCIATION_CHANGED')
            # Persisted refs/hashes are association data, never a reconstructed
            # Memory permission. Only a trusted host's original lifetime can
            # validate the actual original snapshot/history/policy at this point.
            lifetime=self.rejected_memory_lifetime
            from .rejected_intake_capture import OriginalIntakeReadLifetime
            if type(lifetime)is not OriginalIntakeReadLifetime:raise Unavailable('ORIGINAL_MEMORY_LIFETIME_REQUIRED')
            r=original.receipt
            binding=Binding(scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
            check=stack.enter_context(lifetime.hold(context,binding,operation_id,usage.command.input_digest,descriptor))
            publication['memory_held']=True;publication['checks'].append(check)
            check();body=canonical(data);check()
            return body
        with stack:
            # The opaque producer lifetime owns the actual M→Memory locks until
            # after Boundary's final AUTH and TTL checks. Do not re-query M or
            # open another Memory transaction after entering this lifetime.
            return self._read(token,message_id,project,with_context=True,publication=publication)

    def _local_visitor(self,scope,source,row,usage,data):
        receipt=data['receipt']
        require(data['version']=='G2C-tool-evidence.1' and data.get('tool')=='visitor_fact' and
            row[1]=='tool.visitor_fact' and receipt.get('endpoint')=='local:visitor-catalogue' and
            receipt.get('actual_cost_cny')=='0' and receipt.get('data_origin')=='maintainer_summary' and
            receipt.get('response_sha256')==data['response_sha256'],'ORIGINAL_LOCAL_VISITOR_SOURCE')
        logical=original_json(usage.input_bytes);result=original_json(data['result_utf8'])
        require(type(logical) is dict and logical.get('name')=='visitor_fact' and
            type(result) is dict and result.get('version')=='FACT-result.2' and
            type(result.get('catalogue_sha256')) is str and re.fullmatch('[a-f0-9]{64}',result['catalogue_sha256']) is not None and
            result.get('query')==logical.get('query') and result.get('request_ref')==logical.get('request_ref') and
            result.get('data_origin')=='maintainer_summary' and type(result.get('evaluated_at')) is str,
            'ORIGINAL_LOCAL_VISITOR_RESULT')
        try:observed=datetime.fromisoformat(result['evaluated_at'])
        except ValueError:raise Unavailable('ORIGINAL_LOCAL_VISITOR_OBSERVATION_TIME') from None
        require(observed.tzinfo is not None,'ORIGINAL_LOCAL_VISITOR_OBSERVATION_TIME')
        meter=original_json(self._meter(scope,source,row,usage));settled=meter['receipt']
        if (meter['state']!='settled' or settled is None or settled['attempt_id']!=row[3] or
                settled['receipt_id']!='visitor-local:'+data['response_sha256'] or settled['actual']!=1 or
                settled['output']!=len(data['result_utf8'])):
            raise Unavailable('ORIGINAL_LOCAL_VISITOR_METER_RECEIPT')

    def artifact(self,token,message_id,operation_id,*,wire_input=False):
        def project(scope,original,source):
            row,usage=self._operation(scope,source,operation_id)
            try:fee=self._financial(usage.command.attempt_id)
            except Unavailable as error:
                if str(error)!='ORIGINAL_FINANCIAL_ATTEMPT_UNAVAILABLE' or wire_input or usage.command.kind!='tool':raise
                # A separately versioned fixture is not a missing vendor
                # receipt fallback: it must prove NOT_SENT and bind the real
                # settled Meter receipt before any original bytes are returned.
                if row[1]=='tool.weather':
                    from .runtime_weather_fault import read_artifact
                    return read_artifact(self,scope,original,source,row,usage)
                if row[1]!='tool.visitor_fact':raise
                fee=None
            if row[1]=='tool.visitor_fact' and fee is not None:
                raise Unavailable('ORIGINAL_LOCAL_VISITOR_HAS_FINANCIAL_ATTEMPT')
            parts=[scope,original.receipt.run_id,row[0],usage.command.attempt_id]
            if wire_input:parts.append('model_wire_input')
            name=sha256(canonical(parts)).hexdigest()+'.json'
            directory=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                info=os.fstat(directory)
                if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
                    raise Unavailable('ORIGINAL_ARTIFACT_DIRECTORY_AUTHORITY')
                try:raw=read_private(name,1_048_576,directory_fd=directory)
                except PrivateFileError as error:
                    raise Unavailable('ORIGINAL_ARTIFACT_BOUND' if error.reason=='bound' else 'ORIGINAL_ARTIFACT_AUTHORITY') from None
            finally:os.close(directory)
            data=original_json(raw)
            common={'version','message_id','run_id','attempt_id','operation_id','registration_id','scope_sha256'}
            require(type(data) is dict and common<=data.keys(),'ORIGINAL_ARTIFACT_FIELDS')
            if wire_input:
                require(data['version']=='G2C-model-wire-input.1' and
                    {'logical_input_sha256','wire_input_utf8','wire_input_sha256'}<=data.keys() and
                    type(data['wire_input_utf8']) is str and usage.command.kind in ('model','memory'),
                    'ORIGINAL_WIRE_ARTIFACT_FIELDS')
            else:
                require(data['version'] in ('G2C-tool-evidence.1','G2C-lio-intake-evidence.1','G2C-model-evidence.1') and
                    {'input_sha256','result_utf8','response_sha256','receipt'}<=data.keys() and
                    type(data['result_utf8']) is str and type(data['receipt']) is dict and
                    ('input_utf8' not in data or type(data['input_utf8']) is str),
                    'ORIGINAL_RESULT_ARTIFACT_FIELDS')
                require((data['version']=='G2C-tool-evidence.1')==(usage.command.kind=='tool'),
                    'ORIGINAL_ARTIFACT_KIND_CHANGED')
            if (data['message_id'],data['run_id'],data['attempt_id'],data['operation_id'],data['registration_id'])!=(message_id,original.receipt.run_id,row[3],row[4],row[1]) or data['scope_sha256']!=sha256(scope.encode()).hexdigest():
                raise Unavailable('ORIGINAL_ARTIFACT_BINDING_CHANGED')
            if wire_input:
                if (data['logical_input_sha256']!=usage.command.input_digest or
                        sha256(data['wire_input_utf8'].encode()).hexdigest()!=data['wire_input_sha256'] or
                        data['wire_input_sha256']!=fee[1]):
                    raise Unavailable('ORIGINAL_WIRE_HASH_CHANGED')
            else:
                if (data['input_sha256']!=usage.command.input_digest or
                        'input_utf8' in data and data['input_utf8'].encode()!=usage.input_bytes or
                        sha256(data['result_utf8'].encode()).hexdigest()!=data['response_sha256']):
                    raise Unavailable('ORIGINAL_RESULT_HASH_CHANGED')
                if fee is None:
                    self._local_visitor(scope,source,row,usage,data)
                else:
                    if fee[3] is None or original_json(fee[3])!=data['receipt']:
                        raise Unavailable('ORIGINAL_VENDOR_RECEIPT_CHANGED')
                    receipt=data['receipt']
                    output_hash=receipt.get('output_sha256') if usage.command.kind in ('model','memory') else receipt.get('response_sha256')
                    if output_hash!=data['response_sha256']:
                        raise Unavailable('ORIGINAL_VENDOR_OUTPUT_HASH_UNAVAILABLE')
            return raw
        return self._read(token,message_id,project)
