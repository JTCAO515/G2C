"""Actual long ended conversation segments; no model, queue storage or Meter claim."""
import base64,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_message.source import SourceQuery,EndQuery
from cj_memory_jobs.codec import decode_v2,Unavailable
from cj_memory_jobs.ending_source import EndingSegment,read_ending_segment
from cj_memory_jobs.local_app import create_local_history_app

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate,pg_suites


def exercise(conninfo,auth):
    dev_auth.init(auth,['alice','bob'])
    tokens={who:dev_auth.token(auth,who,30) for who in ('alice','bob')}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    app=create_local_history_app(conninfo_path=conninfo,auth_dir=auth);host=app.state.memory_history
    def expected(response,code=200):
        assert response.status_code==code,(response.status_code,response.text)
        return response.json()
    with TestClient(app) as client:
        head=expected(client.put('/v1/conversations',params={'conversation_id':'long'},headers=headers['alice']))
        def post(path,value):return expected(client.post(path,content=json.dumps(value).encode(),headers=headers['alice']))
        for index in range(101):
            post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='long',message_id=f'm{index}',text=f'Committed message {index}',
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=index))
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='long',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        end=EndQuery('long',head['generation'],0,101)
        query=SourceQuery('long',head['generation'],0,0,100,1,1,'conversation_end')
        first=EndingSegment(query,end)
        def read(segment,who='alice'):
            token=tokens[who]
            return read_ending_segment(host.boundary,token,segment,lambda context:host.service.source_policy(context,token))
        from cj_message.domain import Unavailable as MessageUnavailable
        try:read(first)
        except (Unavailable,MessageUnavailable):pass
        else:raise AssertionError('unended conversation produced an ending segment')
        ended=post('/internal/v1/conversation-end',dict(version='MESSAGE-SOURCE@1',conversation_id='long',generation=head['generation'],
            epoch=0,through=101,conversation_type='travel'))['end']
        raw=read(first);value=json.loads(raw)
        source,rows,mode=decode_v2(base64.b64decode(value['batch_utf8_base64']))
        assert (source.cursor.after,source.cursor.through,mode,len(rows))==(0,100,'conversation_end',100)
        assert value['end']==ended and read(first)==raw
        tail=EndingSegment(SourceQuery('long',head['generation'],0,100,101,1,1,'conversation_end'),end)
        last=json.loads(read(tail));_,tail_rows,_=decode_v2(base64.b64decode(last['batch_utf8_base64']))
        assert [row.receipt.message_id for row in rows+tail_rows]==[f'm{i}' for i in range(101)]
        assert last['end']==ended
        try:read(first,'bob')
        except (Unavailable,MessageUnavailable):pass
        else:raise AssertionError('other account read a private ending segment')
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='disable',operation='disable',conversation_id='long',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=1))
        try:read(first)
        except (Unavailable,MessageUnavailable):pass
        else:raise AssertionError('withdrawn ending source was readable')
        print('PASS actual 101 committed messages: real immutable end required, exact 100+1 segments/replay share its end ID, no truncation/Trip, other account and withdrawn source denied')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='ending-source-') as tmp:
        with pg_suites.cluster('ending_source',port=55516,role='cj_ending_source',socket=f'/tmp/cj-ending-source-{os.getpid()}') as config:
            with psycopg.connect(**config,autocommit=True) as conn:migrate.up(conn,migrate.load(),migrate.load()[-1]['version'])
            root=Path(tmp);path=root/'conninfo.json';path.write_text(json.dumps(config))
            exercise(path,root/'auth')
