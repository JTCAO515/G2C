"""BG3 accepted-decision comparison data; C phase holders grant authority."""
from dataclasses import asdict,dataclass,field
import base64,json
from typing import ClassVar
from cj_usage.background_exit import ModelInput
from cj_strict_json import reject_duplicates
from .background_store import JobRequest,ABI_V3,REGISTRATION_V3,pack,sha


@dataclass(frozen=True,repr=False)
class JobRequestV3(JobRequest):
    protocol:ClassVar[str]=ABI_V3
    registration_id:ClassVar[str]=REGISTRATION_V3
    decision_source_sha256:str=field()

    def __post_init__(self):
        super().__post_init__()
        digest=self.decision_source_sha256
        if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('exact decision source digest required')
        if self.travel is not None:raise ValueError('decision source uses the actual C Trip holder')
        model=ModelInput.parse(self.prepared_input)
        if len(model.messages)!=1:raise ValueError('one explicit decision data message required')
        data=json.loads(model.messages[0][1],object_pairs_hook=reject_duplicates(ValueError,'duplicate decision model field'))
        if type(data) is not dict or data.get('version')!='MEMORY-EXTRACT-DATA@3' or data.get('decision_source_sha256')!=digest:
            raise ValueError('original Data3 decision source digest required')

    def envelope(self,scope,run_id):
        return pack(dict(version=self.protocol,registration_id=self.registration_id,run_id=run_id,scope_digest=sha(scope.encode()),
            job_id=self.job_id,attempt_id=self.attempt_id,source=asdict(self.query),travel=None,
            prepared_input_base64=base64.b64encode(self.prepared_input).decode('ascii'),decision_source_sha256=self.decision_source_sha256))
