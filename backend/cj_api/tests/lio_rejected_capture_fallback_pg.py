"""Joint a+c: genuine intake capture before the guarded general/Memory path.

Two fresh signed private PG accounts use active Memory and fixture HTTP only.
No production identity, provider request or historical JT replay is involved.
"""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import httpx
from cj_api import rejected_intake_capture as capture_module
from cj_api.rejected_intake_capture import RejectedIntakeSink,use_rejected_intake_sink,TTL_SECONDS
import lio_cross_language_pg as native


def main():
    original_exercise=native.exercise
    original_persist=RejectedIntakeSink.persist
    original_http=httpx.MockTransport.handle_request
    captures=[];general=[];groups=[]
    def http(transport,request):
        body=json.loads(request.content)
        if 'LIO-planning-intake.8'in body['messages'][0]['content']:
            assert capture_module._current.get()is not None
        else:
            # No rejected raw buffer/lifetime may encompass the subsequent
            # real general model or its already-enabled Memory extraction.
            assert capture_module._current.get()is None
            general.append(body['messages'][0]['content'].startswith('MEMORY-EXTRACT@2'))
        return original_http(transport,request)
    def persist(sink,operation,raw,metadata,memory,code,check):
        receipt=original_persist(sink,operation,raw,metadata,memory,code,check)
        # Check storage only while the real producer's own source/M/Memory
        # lifetime is held by reject(). This is not a historical read grant.
        check();stored=sink.read(receipt.reference);check()
        assert receipt.status=='CAPTURED'
        assert stored['result_utf8'].encode()==raw
        assert stored['output_sha256']==sha256(raw).hexdigest()and stored['output_bytes']==len(raw)
        assert stored['message_id']==operation.binding.message_id and stored['run_id']==operation.binding.run_id
        assert stored['attempt_id']==operation.command.attempt_id
        assert stored['code']==code and code=='field_source_binding'
        assert (datetime.fromisoformat(stored['expires_at'])-datetime.fromisoformat(stored['captured_at'])).total_seconds()==TTL_SECONDS
        assert (sink.directory/(receipt.reference+'.json')).stat().st_mode&0o777==0o600
        captures.append((operation.binding.run_id,receipt.reference))
        return receipt
    def exercise(root,conninfo,**kwargs):
        directory=root/'rejected';directory.mkdir(mode=0o700)
        before=len(captures);before_general=len(general)
        with use_rejected_intake_sink(RejectedIntakeSink(directory)):
            original_exercise(root,conninfo,**kwargs)
        assert capture_module._current.get()is None
        assert len(captures)==before+2
        assert len(list(directory.iterdir()))==2
        denied=kwargs['max_steps']==1
        assert len(general)==before_general+(0 if denied else 4)
        groups.append(denied)
    with patch.object(native,'exercise',exercise),patch.object(RejectedIntakeSink,'persist',persist), \
            patch.object(httpx.MockTransport,'handle_request',http):
        for mode in ('buffered','compact','stream'):
            native.main(basic_memory=True,fallback_only=True,native_mode=mode)
            native.main(basic_memory=True,fallback_only=True,max_steps=1,native_mode=mode)
    assert groups==[False,True]*3 and len(captures)==len(set(captures))==12
    print('PASS signed ZH/EN a+c BUFFERED/compact/STREAM: 12 exact private original captures at actual settled intake ACK; full budget generic+Memory outside capture, one-step budget denies before next supplier; original receipts/active Memory preserved, zero NEEDS/Trip; fixture HTTP only',flush=True)


if __name__=='__main__':main()
