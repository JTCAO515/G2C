import json,unittest
from cj_message.source import SourceQuery
from cj_message.travel import Selection
from cj_run.background_store import JobRequest
from cj_run.background_store_v3 import JobRequestV3


class BackgroundV3InputChecks(unittest.TestCase):
    def request(self,digest='a'*64,**changes):
        raw=json.dumps(dict(system='fixed',messages=[dict(role='user',content=json.dumps(dict(
            version='MEMORY-EXTRACT-DATA@3',decision_source_sha256='a'*64)))])).encode()
        values=dict(job_id='job',attempt_id='attempt',query=SourceQuery('chat','gen',0,0,1,1,1),travel=None,
                    prepared_input=raw,decision_source_sha256=digest);values.update(changes)
        return JobRequestV3(**values)

    def test_explicit_v3_and_digest_bind_the_original_envelope(self):
        req=self.request();raw=req.envelope('owner','run');value=json.loads(raw)
        self.assertEqual((value['version'],value['registration_id'],value['decision_source_sha256']),
                         ('RUN-BACKGROUND@3','memory.accepted-decision.1','a'*64))
        self.assertNotEqual(raw,JobRequest(req.job_id,req.attempt_id,req.query,None,req.prepared_input).envelope('owner','run'))
        self.assertNotEqual(raw,req.envelope('other-owner','run'))

    def test_wrong_digest_role_data_version_or_travel_fails_before_dispatch(self):
        with self.assertRaises(ValueError):self.request('b'*64)
        with self.assertRaises(ValueError):self.request(travel=Selection('trip',1))
        for version,role in (('MEMORY-EXTRACT-DATA@2','user'),('MEMORY-EXTRACT-DATA@3','tool')):
            raw=json.dumps(dict(system='fixed',messages=[dict(role=role,content=json.dumps(dict(version=version,decision_source_sha256='a'*64)))])).encode()
            with self.subTest(version=version,role=role),self.assertRaises(ValueError):self.request(prepared_input=raw)


if __name__=='__main__':unittest.main()
