"""RUN-BACKGROUND@3: explicit Pub3/decision digest on the original single engine."""
import json
from cj_strict_json import reject_duplicates
from .background import BackgroundJobsV2,_read_original
from .background_store import JobStore,ABI_V3,sha
from .core import Conflict

PUBLICATION='MEMORY-PUBLICATION-result@3'


def read_original_v3(database,boundary,token,jid,attempt):
    return _read_original(database,boundary,token,jid,attempt,protocol=ABI_V3)


class BackgroundJobsV3(BackgroundJobsV2):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        if self.collection.consumer_version!=ABI_V3 or self.collection.publication_version!=PUBLICATION:
            raise ValueError('explicit BG3 / Pub3 collection adapter required')

    def _store(self,scope):return JobStore(self.database.run_repository(scope),protocol=ABI_V3)

    def prepare(self,token,request):
        if request.protocol!=ABI_V3:raise ValueError('explicit original BG3 request required')
        return super().prepare(token,request)

    def _processing_policy(self,args):
        return self.collection.processing_policy(*args,max_payload_bytes=self.max_payload_bytes,consumer_version=ABI_V3)

    def _publication_policy(self,args,output,commit_guard):
        return self.collection.publication_policy(*args,output,sha(output),max_payload_bytes=self.max_payload_bytes,
            before_commit=commit_guard,consumer_version=ABI_V3)

    def query_original(self,token,jid,attempt):
        return read_original_v3(self.database,self.boundary,token,jid,attempt)

    def _publication(self,raw,record):
        value=json.loads(raw,object_pairs_hook=reject_duplicates(Conflict,'duplicate Pub3 field'))
        fields={'version','job_id','attempt_id','enqueue_input_sha256','prepared_input_sha256',
                'model_output_sha256','receipts','decision_source_sha256'}
        if (type(value) is not dict or set(value)!=fields or value['version']!=PUBLICATION or record.protocol!=ABI_V3
            or (value['job_id'],value['attempt_id'],value['prepared_input_sha256'],value['model_output_sha256'],value['decision_source_sha256'])
            !=(record.job_id,record.attempt_id,record.prepared_input_sha256,record.output_sha256,record.decision_source_sha256)):
            raise Conflict('actual original typed Pub3/decision digest required')
        enqueue=value['enqueue_input_sha256']
        if type(enqueue) is not str or len(enqueue)!=64 or any(c not in '0123456789abcdef' for c in enqueue):
            raise Conflict('actual original C enqueue digest required')
        return sha(raw)
