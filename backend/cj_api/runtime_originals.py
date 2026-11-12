"""Protected original bytes for runtime collection, never dispatch/recovery writes.

Every read uses the existing MESSAGE history AUTH lifetime and scoped runtime
database. Artifact references are resolved from original operation IDs, not paths
or URLs supplied by the adapter. Deleted input payloads cannot expose old files.
"""
from dataclasses import asdict
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
from cj_usage.codec import decode
from cj_usage.authorization_budget import canonical
from cj_usage.metered_exit import BudgetUnknown
from runtime_adapter.contract import Unavailable,decode as original_json,require
from .runtime_private import read_private,PrivateFileError


class RuntimeOriginals:
    def __init__(self,message_boundary,database,budget,artifact_directory):
        if type(message_boundary) is not Boundary:
            raise ValueError('original MESSAGE history boundary required')
        self.boundary,self.database,self.budget=message_boundary,database,budget
        self.directory=Path(artifact_directory)

    def _operations(self,scope,run_id):
        with self.database.connect(scope) as db:
            db.execute('SET TRANSACTION READ ONLY')
            state=db.execute('SELECT status,run_id FROM cj_run_record WHERE scope=%s AND run_id=%s',(scope,run_id)).fetchone()
            events=db.execute('SELECT sequence,kind,value FROM cj_run_event WHERE scope=%s AND run_id=%s ORDER BY sequence',(scope,run_id)).fetchall()
            operations=db.execute('SELECT operation_key,registration_id,kind,attempt_id,operation_id,ledger_scope,command_bytes,input_bytes FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s ORDER BY operation_key',(scope,run_id)).fetchall()
            period=db.execute('SELECT ledger_scope,unit,period_start,period_end FROM cj_run_metered_binding WHERE scope=%s AND run_id=%s',(scope,run_id)).fetchone()
        if state is None:raise Unavailable('ORIGINAL_RUN_UNAVAILABLE')
        return state,events,operations,period

    def _read(self,token,message_id,project):
        def operation(context):
            original=context.query_message(message_id)
            if original is None:raise Unavailable('ORIGINAL_MESSAGE_UNAVAILABLE')
            source=self._operations(context.scope,original.receipt.run_id)
            body=project(context.scope,original,source)
            # Storage/files/fee callbacks completed before the final same-source
            # check; Boundary then repeats canonical AUTH before bytes escape.
            if context.query_message(message_id)!=original or self._operations(context.scope,original.receipt.run_id)!=source:
                raise Unavailable('ORIGINAL_SNAPSHOT_CHANGED')
            return body
        try:return self.boundary.with_history_context(token,operation)
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

    def input(self,token,message_id,operation_id):
        return self._read(token,message_id,lambda scope,original,source:self._operation(scope,source,operation_id)[1].input_bytes)

    def meter(self,token,message_id,operation_id):
        def project(scope,original,source):
            row,usage=self._operation(scope,source,operation_id,allow_erased=True);period=source[3]
            if period is None:raise Unavailable('ORIGINAL_PERIOD_UNAVAILABLE')
            profiles=[p for p in self.database.run_context.profiles if
                (ledger_scope_for(scope,p.meter),p.meter.unit,p.meter.period_start,p.meter.period_end)==tuple(period)]
            if len(profiles)!=1 or row[5]!=period[0]:raise Unavailable('ORIGINAL_PERIOD_NOT_RETAINED')
            with self.database.connect(scope,usage_profile=profiles[0]) as db:
                db.execute('SET TRANSACTION READ ONLY')
                stored=db.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(row[5],)).fetchone()
            if stored is None:raise Unavailable('ORIGINAL_METER_UNAVAILABLE')
            attempt=decode(stored[0]).attempts.get(usage.command.attempt_id)
            if attempt is None:raise Unavailable('ORIGINAL_METER_ATTEMPT_UNAVAILABLE')
            return canonical(asdict(attempt))
        return self._read(token,message_id,project)

    def fee(self,token,message_id,operation_id):
        def project(scope,original,source):
            row,usage=self._operation(scope,source,operation_id,allow_erased=True)
            fee=self._financial(usage.command.attempt_id)
            return canonical(dict(attempt_id=usage.command.attempt_id,ledger_id=self.budget.ledger_id,
                kind=fee[0],actual_wire_input_sha256=fee[1],state=fee[2],receipt_utf8=fee[3]))
        return self._read(token,message_id,project)

    def artifact(self,token,message_id,operation_id,*,wire_input=False):
        def project(scope,original,source):
            row,usage=self._operation(scope,source,operation_id)
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
            fee=self._financial(usage.command.attempt_id)
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
                if fee[3] is None or original_json(fee[3])!=data['receipt']:
                    raise Unavailable('ORIGINAL_VENDOR_RECEIPT_CHANGED')
                receipt=data['receipt']
                output_hash=receipt.get('output_sha256') if usage.command.kind in ('model','memory') else receipt.get('response_sha256')
                if output_hash!=data['response_sha256']:
                    raise Unavailable('ORIGINAL_VENDOR_OUTPUT_HASH_UNAVAILABLE')
            return raw
        return self._read(token,message_id,project)
