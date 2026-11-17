"""#1036: content-free HK API access log (route template, status, timing, request ID, build)."""
from datetime import datetime,timedelta,timezone
import asyncio
import io
import json
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,StreamingResponse
from fastapi.testclient import TestClient

from deploy.hk import access_log
from deploy.hk.access_log import AccessLog,Sink

SECRET_PATH='trip-7f3a-secret-id'
TOKEN='Bearer sk-synthetic-should-never-appear'
BODY='{"text":"我对花生过敏 invitation INV-SECRET-CODE memory"}'
UUID='0f8fbb6e-3f07-4b8e-8f7e-0a6f3b1c2d4e'


def private_dir(tmp_path):
    directory=tmp_path/'access-log';directory.mkdir(mode=0o700);directory.chmod(0o700);return directory


def lines(directory, *, phase='finished'):
    records = [json.loads(line) for path in sorted(directory.glob('access-*.jsonl')) for line in path.read_text().splitlines()]
    return records if phase == 'all' else [row for row in records if row.get('phase', 'finished') == phase]


def application(sink,*,gate=None):
    app=FastAPI()

    @app.middleware('http')
    async def trace(request,call_next):
        response=await call_next(request);response.headers['X-Request-ID']=UUID;return response

    @app.middleware('http')
    async def deployment_gate(request,call_next):
        if request.url.path=='/health/live':return JSONResponse({'status':'alive'})
        if gate is not None:request.state.access_gate=gate
        if request.url.path=='/health/ready':
            return JSONResponse({'status':'ready'if gate is None else'unavailable'},status_code=200 if gate is None else 503)
        if gate is not None:return JSONResponse({'error':'deployment_unavailable'},status_code=503)
        return await call_next(request)

    @app.post('/v1/trips/{trip_id}/messages')
    async def message(trip_id:str,request:Request):
        await request.body();return JSONResponse({'echo':'not logged'},status_code=409 if trip_id.endswith('conflict')else 200)

    @app.get('/v1/stream/{run_id}')
    async def stream(run_id:str):
        async def chunks():
            yield b'data: one\n\n';yield b'data: two\n\n'
        return StreamingResponse(chunks(),media_type='text/event-stream')

    @app.get('/v1/boom')
    async def boom():raise RuntimeError('exception text with '+TOKEN)

    app.add_middleware(AccessLog,sink=sink)
    return app


def test_records_route_template_status_timing_request_id_and_build_without_content(tmp_path):
    directory=private_dir(tmp_path);sink=Sink(directory)
    client=TestClient(application(sink))
    response=client.post('/v1/trips/'+SECRET_PATH+'/messages?invite=INV-SECRET-CODE',content=BODY,
                         headers={'Authorization':TOKEN,'User-Agent':'G2C/43 CFNetwork/3826.400.120 Darwin/25.0.0',
                                  'Cookie':'session=secret-cookie'})
    assert response.status_code==200
    client.post('/v1/trips/x-conflict/messages',content=BODY,headers={'X-G2C-App-Build':'44'})
    first,second=lines(directory)
    assert set(first)=={'v','phase','exchange_id','ts','method','route','status','duration_ms','ttfb_ms','request_id','app_build','error_class','outcome'}
    assert first['v']=='G2C-HK-access-log.2' and first['route']=='/v1/trips/{trip_id}/messages'
    starts=lines(directory,phase='started')
    assert len(starts)==2 and starts[0]['exchange_id']==first['exchange_id']
    assert starts[1]['exchange_id']==second['exchange_id']!=first['exchange_id']
    assert all(row['route'] is None and row['request_id'] is None for row in starts)
    assert first['method']=='POST' and first['status']==200 and first['request_id']==UUID
    assert first['app_build']=='43' and first['error_class']is None and first['outcome']=='completed'
    assert first['duration_ms']>=first['ttfb_ms']>=0 and first['ts'].endswith('Z')
    assert second['status']==409 and second['error_class']=='conflict' and second['app_build']=='44'
    raw=''.join(p.read_text()for p in directory.iterdir())
    for forbidden in (SECRET_PATH,'x-conflict','INV-SECRET-CODE','sk-synthetic','secret-cookie','花生','memory',
                      'not logged','CFNetwork','127.0.0.1','testclient'):
        assert forbidden not in raw
    (path,)=directory.iterdir()
    assert path.name=='access-'+datetime.now(timezone.utc).strftime('%Y-%m-%d')+'.jsonl'
    assert oct(path.stat().st_mode&0o777)=='0o600'


def test_gate_503_unmatched_404_and_exception_are_classified(tmp_path):
    directory=private_dir(tmp_path)
    gated=TestClient(application(Sink(directory),gate='worker_heartbeat_stale'))
    assert gated.get('/v1/stream/abc').status_code==503
    assert gated.get('/health/ready').status_code==503
    client=TestClient(application(Sink(directory)),raise_server_exceptions=False)
    assert client.get('/v1/unknown/'+SECRET_PATH).status_code==404
    assert client.get('/v1/boom').status_code==500
    assert client.get('/health/ready').status_code==200 and client.get('/health/live').status_code==200
    gate,ready,missing,boom=lines(directory)
    # The gate rejects before routing: no template, no request ID, the gate reason is the class.
    assert (gate['route'],gate['status'],gate['error_class'],gate['request_id'])==(None,503,'deployment_worker_heartbeat_stale',None)
    assert (ready['route'],ready['status'])==('/health/ready',503)
    assert (missing['route'],missing['status'],missing['error_class'])==(None,404,'not_found')
    assert boom['route']=='/v1/boom' and boom['status']is None and boom['error_class']=='exception'
    assert boom['outcome']=='exception'
    raw=''.join(p.read_text()for p in directory.iterdir())
    assert SECRET_PATH not in raw and 'sk-synthetic' not in raw and 'exception text' not in raw


def test_streaming_duration_covers_the_whole_body(tmp_path):
    directory=private_dir(tmp_path);client=TestClient(application(Sink(directory)))
    assert client.get('/v1/stream/run-1').text=='data: one\n\ndata: two\n\n'
    (row,)=lines(directory)
    assert row['route']=='/v1/stream/{run_id}' and row['outcome']=='completed' and row['status']==200


def test_arrival_is_durable_before_response_and_cancellation_does_not_hide_it(tmp_path):
    directory=private_dir(tmp_path)

    async def scenario():
        entered=asyncio.Event()
        async def held(scope,receive,send):
            entered.set()
            await asyncio.Event().wait()
        async def never_read():
            raise AssertionError('logger must not read the request body')
        async def send(message):
            raise AssertionError('held application sends no response')
        scope={'type':'http','method':'POST','path':'/private/'+SECRET_PATH,
               'query_string':b'invite=INV-SECRET-CODE',
               'headers':[(b'authorization',TOKEN.encode()),(b'x-request-id',b'client-controlled'),
                          (b'x-g2c-app-build',b'45')]}
        task=asyncio.create_task(AccessLog(held,Sink(directory))(scope,never_read,send))
        await entered.wait()
        (arrival,)=lines(directory,phase='all')
        assert arrival['phase']=='started' and arrival['outcome']=='in_flight'
        assert arrival['status'] is None and arrival['route'] is None and arrival['request_id'] is None
        assert arrival['app_build']=='45' and access_log._REQUEST_ID.fullmatch(arrival['exchange_id'])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        start,end=lines(directory,phase='all')
        assert start==arrival and end['phase']=='finished'
        assert end['exchange_id']==start['exchange_id'] and end['outcome']=='exception'
        assert end['status'] is None
        raw=''.join(p.read_text()for p in directory.iterdir())
        for forbidden in (SECRET_PATH,'INV-SECRET-CODE','sk-synthetic','client-controlled'):
            assert forbidden not in raw
    asyncio.run(scenario())


def test_query_keeps_v1_completion_counts_and_exposes_v2_arrivals_on_request(tmp_path):
    directory=private_dir(tmp_path);sink=Sink(directory)
    now=datetime.now(timezone.utc)
    for row in ({'v':'G2C-HK-access-log.1','status':200},
                {'v':access_log.VERSION,'phase':'started','status':None},
                {'v':access_log.VERSION,'phase':'finished','status':503}):
        sink.write(dict(row,ts=access_log._stamp(now.timestamp()),route=None))
    start=now-timedelta(seconds=1);end=now+timedelta(seconds=1)
    assert access_log.query(directory,start,end,out=io.StringIO())==2
    assert access_log.query(directory,start,end,phase='started',out=io.StringIO())==1
    out=io.StringIO()
    assert access_log.query(directory,start,end,phase='all',out=out)==3
    assert json.loads(out.getvalue().splitlines()[-1])['by_status']=={'200':1,'503':1,'None':1}


@pytest.mark.parametrize('later_days', [0, 1, 3])
@pytest.mark.parametrize('offset', [timezone.utc, timezone(timedelta(hours=8))])
def test_query_finds_original_start_window_in_later_write_buckets(tmp_path, later_days, offset):
    directory = private_dir(tmp_path)
    started = datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc)
    clock = [started.timestamp()]
    sink = Sink(directory, clock=lambda: clock[0])
    common = dict(v=access_log.VERSION, ts=access_log._stamp(started.timestamp()),
                  exchange_id='original-exchange')
    sink.write(dict(common, phase='started', status=None, route=None))
    clock[0] = (started + timedelta(days=later_days, seconds=2)).timestamp()
    sink.write(dict(common, phase='finished', status=503, route='/v2/demo-invite-sessions'))
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    since = (started - timedelta(seconds=1)).astimezone(offset)
    until = (started + timedelta(microseconds=500000)).astimezone(offset)
    out = io.StringIO()
    assert access_log.query(directory, since, until, phase='all', out=out) == 2
    rows = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [row['phase'] for row in rows[:-1]] == ['started', 'finished']
    assert {row['exchange_id'] for row in rows[:-1]} == {'original-exchange'}
    assert rows[-1]['by_status'] == {'503': 1, 'None': 1}
    assert access_log.query(directory, since, until, out=io.StringIO()) == 1
    assert access_log.query(directory, since, until, phase='started', out=io.StringIO()) == 1
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_query_later_buckets_keep_filename_symlink_and_timestamp_boundaries(tmp_path):
    directory = private_dir(tmp_path)
    (directory / 'access-2026-11-14.jsonl').write_text('outside old bucket, not read')
    (directory / 'access-not-a-date.jsonl').write_text('not an access bucket')
    (directory / 'access-2026-99-99.jsonl').write_text('not a calendar date')
    outside = tmp_path / 'outside.jsonl'
    outside.write_text('symlink target must not be read')
    (directory / 'access-2026-11-18.jsonl').symlink_to(outside)
    stamp = datetime(2026, 11, 15, 23, 59, 59, tzinfo=timezone.utc)
    sink = Sink(directory, clock=lambda: (stamp + timedelta(days=2)).timestamp())
    for at, status in ((stamp - timedelta(seconds=2), 401), (stamp, 503),
                       (stamp + timedelta(seconds=2), 200)):
        sink.write(dict(ts=access_log._stamp(at.timestamp()), status=status, route='/v1/x'))
    out = io.StringIO()
    assert access_log.query(directory, stamp - timedelta(seconds=1), stamp + timedelta(seconds=1),
                            min_status=400, route='/v1/x', out=out) == 1
    assert json.loads(out.getvalue().splitlines()[0])['status'] == 503
    assert outside.read_text() == 'symlink target must not be read'


def test_build_parsing_accepts_only_bounded_numbers():
    assert access_log.client_build([(b'user-agent',b'Lio%20Beta/44.1 CFNetwork/3826.400.120 Darwin/25.0.0')])=='44.1'
    assert access_log.client_build([(b'user-agent',b'Mozilla/5.0 (iPhone) Safari')])is None
    assert access_log.client_build([(b'user-agent',b'G2C/43 CFNetwork/1 Darwin/2 extra')])is None
    assert access_log.client_build([(b'x-g2c-app-build',b'44; drop table')])is None
    assert access_log.client_build([(b'x-g2c-app-build',b'45'),(b'user-agent',b'G2C/43 CFNetwork/1 Darwin/2')])=='45'


def test_retention_prunes_only_expired_own_files_and_cap_drops_with_alert(tmp_path,capsys):
    directory=private_dir(tmp_path)
    now=datetime(2026,11,30,12,tzinfo=timezone.utc)
    for days in (0,13,14,40):
        old=directory/('access-'+(now-timedelta(days=days)).strftime('%Y-%m-%d')+'.jsonl');old.write_text('');old.chmod(0o600)
    (directory/'unrelated.txt').write_text('kept')
    sink=Sink(directory,clock=now.timestamp,daily_cap=60)
    sink.write({'a':'x'*10})
    names=sorted(p.name for p in directory.iterdir())
    assert names==['access-2026-11-17.jsonl','access-2026-11-30.jsonl','unrelated.txt']
    sink.write({'a':'x'*80})
    assert len(lines(directory))==1
    assert 'ALERT access_log_daily_cap_reached_2026-11-30' in capsys.readouterr().err


@pytest.mark.parametrize('mode',[0o755,None])
def test_unqualified_or_absent_directory_falls_back_to_stderr(tmp_path,mode):
    directory=tmp_path/'access-log'
    if mode is not None:directory.mkdir();directory.chmod(mode)
    out=io.StringIO();sink=Sink(directory,fallback=out)
    assert not sink.enabled
    sink.write({'route':None})
    assert out.getvalue().startswith('ACCESS {')
    assert mode is None or not list(directory.iterdir())


def test_write_failure_never_changes_the_response(tmp_path,monkeypatch):
    directory=private_dir(tmp_path);sink=Sink(directory,fallback=io.StringIO())
    monkeypatch.setattr(access_log.os,'write',lambda *a:(_ for _ in ()).throw(OSError('disk full')))
    assert TestClient(application(sink)).post('/v1/trips/a/messages',content=b'{}').status_code==200


def test_query_bounds_window_and_filters(tmp_path):
    directory=private_dir(tmp_path)
    clock=[datetime(2026,11,15,13,40,tzinfo=timezone.utc).timestamp()]
    sink=Sink(directory,clock=lambda:clock[0])
    for minute,status in ((40,200),(43,503),(50,401),(59,200)):
        clock[0]=datetime(2026,11,15,13,minute,tzinfo=timezone.utc).timestamp()
        sink.write({'ts':access_log._stamp(clock[0]),'status':status,'route':'/v1/x'})
    out=io.StringIO()
    since=datetime.fromisoformat('2026-11-15T21:41:00+08:00');until=datetime.fromisoformat('2026-11-15T21:55:00+08:00')
    assert access_log.query(directory,since,until,min_status=400,out=out)==2
    *rows,summary=[json.loads(x)for x in out.getvalue().splitlines()]
    assert [r['status']for r in rows]==[503,401] and summary['by_status']=={'503':1,'401':1}
    with pytest.raises(ValueError):access_log.query(directory,until,since)
    with pytest.raises(SystemExit):access_log.main(['query','--since','2026-11-15T21:41:00','--until','2026-11-15T22:00:00+08:00'])


def test_hk_api_installs_access_log_outermost(monkeypatch):
    from deploy.hk import entrypoint
    app=FastAPI();captured={}
    runtime=SimpleNamespace(app=lambda:app,database=lambda:None)
    monkeypatch.setattr(entrypoint,'ready',lambda database,runtime:None)
    import uvicorn
    monkeypatch.setattr(uvicorn,'run',lambda app,**kw:captured.update(app=app,**kw))
    entrypoint.api(runtime)
    assert captured['access_log']is False
    assert app.user_middleware[0].cls is AccessLog
    assert type(app.user_middleware[0].kwargs['sink'])is Sink
