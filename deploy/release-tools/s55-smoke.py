"""Build 55 copy: spaced taxi search (DiDi rate limit) plus English place names (locale=en)."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import runpy
import sys

from cj_strict_json import compact


HERE = Path(__file__).resolve().parent
PROGRAM = """
from datetime import datetime,timezone
import json,sys,time
from urllib.parse import parse_qs,urlsplit
from uuid import uuid4
from cj_api.nearby_tools import SEARCH as NEARBY, VERSION as NEAR_VERSION
from cj_api.taxi_tools import LINK, SEARCH as TAXI, VERSION as TAXI_VERSION
from deploy.hk.server_smoke import request,SmokeResult

packet=json.load(sys.stdin)
deadline=datetime.fromisoformat(packet['ends_at'])
def call(route,body):
    assert (deadline-datetime.now(timezone.utc)).total_seconds()>30
    return request(packet['credential'],route,document=body,content_type='application/json',timeout=18)[0]

def taxi():
    cities=(('北京市',('天安门','故宫','北京西站')),
            ('上海市',('外滩','东方明珠','上海虹桥站')),
            ('成都市',('宽窄巷子','春熙路','成都东站')))
    endpoints=[]
    for city,queries in cities:
        for query in queries:
            time.sleep(2)  # stay under DiDi's short-window rate limit
            value=call(TAXI,dict(version=TAXI_VERSION,city=city,query=query))
            assert value['version']==TAXI_VERSION and value['items']
            for row in value['items']:
                assert row['city']==city and row['coordinate_system']=='GCJ-02'
                assert row['name_zh'].strip()
                assert type(row['lat']) in (int,float) and type(row['lng']) in (int,float)
            if city=='北京市' and query!='北京西站':
                point=value['items'][0]
                endpoints.append({k:point[k] for k in ('lat','lng','coordinate_system')})
            print(json.dumps(dict(case=query,items=len(value['items']),status='PASS'),ensure_ascii=False),flush=True)
    assert len(endpoints)==2
    value=call(LINK,dict(version=TAXI_VERSION,origin=endpoints[0],destination=endpoints[1]))
    parsed=urlsplit(value['url'])
    assert value['version']==TAXI_VERSION and parsed.scheme=='https' and parsed.hostname=='v.didi.cn'
    points=parse_qs(parsed.query)
    assert set(points)=={'slat','slng','dlat','dlng'}
    print(json.dumps(dict(kind='taxi_search_to_link',status='PASS',checks=9)),flush=True)

def english():
    cases=(('广州市','Canton Tower'),('广州市','Tianhecheng'),('北京市','天安门'))
    for city,query in cases:
        time.sleep(2)
        value=call(TAXI,dict(version=TAXI_VERSION,city=city,query=query,locale='en'))
        assert value['version']==TAXI_VERSION and value['items']
        named=[row for row in value['items'] if 'name_en' in row]
        for row in value['items']:
            assert row['name_zh'].strip() and row['coordinate_system']=='GCJ-02'
        sample=named[0] if named else None
        print(json.dumps(dict(case=query,items=len(value['items']),english=len(named),
            sample_zh=None if sample is None else sample['name_zh'],
            sample_en=None if sample is None else sample['name_en'],
            sample_address_en=None if sample is None else sample.get('address_en'),
            status='PASS' if named else 'NO_ENGLISH'),ensure_ascii=False),flush=True)
        assert named
    time.sleep(2)
    again=call(TAXI,dict(version=TAXI_VERSION,city='广州市',query='Canton Tower',locale='en'))
    print(json.dumps(dict(kind='english_cache_repeat',english=sum('name_en' in r for r in again['items']))),flush=True)
    print(json.dumps(dict(kind='english',status='PASS',checks=3)),flush=True)

def nearby():
    body=dict(version=NEAR_VERSION,request_id=str(uuid4()),
        center=dict(lat=39.9151,lng=116.3907,coordinate_system='WGS-84'),
        categories=['sights'],radius_m=500,sort='distance')
    result=call(NEARBY,body)
    assert result['version']==NEAR_VERSION and result['items']
    assert all(row['coordinate_system']=='GCJ-02' and row['name_zh'].strip() for row in result['items'])
    print(json.dumps(dict(kind='nearby',status='PASS',items=len(result['items']))),flush=True)

try:
    dict(taxi=taxi,nearby=nearby,english=english)[packet['feature']]()
except SmokeResult as error:
    print(json.dumps(dict(kind=packet['feature'],status=error.status,reason=error.reason)),flush=True)
    raise SystemExit(1) from None
except (AssertionError,KeyError,TypeError,ValueError):
    print(json.dumps(dict(kind=packet['feature'],status='FAIL',reason='response_structure')),flush=True)
    raise SystemExit(2) from None
"""


def main():
    run,feature=sys.argv[1:]
    assert re.fullmatch(r'b-smoke-20261118-[3-9][0-9]',run) and feature in ('taxi','nearby','english')
    quick=runpy.run_path(str(HERE/'s-build52-quick.py'))
    private=quick['private']
    assert sha256(private(quick['OPERATOR'])).hexdigest()==quick['EXPECTED_OPERATOR']
    auth=runpy.run_path(str(quick['ORIGINAL']))
    ops=runpy.run_path(str(quick['OPERATOR']))
    gate=json.loads(private(HERE/(run+'-forward-gate.json')))
    source,image=gate['source'],gate['image_id']
    assert any(review['pr_number'] in (1440,1443) for review in (gate,*gate['related_reviews']))
    assert json.loads(private(HERE/(run+'-batch-chat-verdict.json')))['status']=='PASS'
    assert json.loads(private(HERE/(run+'-smoke-restore.stdout')))==dict(kind='budget_restore',status='PASS')
    login=auth['login']
    old=login.__globals__['LOGIN']
    anchor="invite_code=packet['code']))"
    assert old.count('configured_plugin_subjects')==2 and old.count(anchor)==1
    login.__globals__['LOGIN']=old.replace('configured_plugin_subjects','configured_translation_subjects').replace(
        anchor,"invite_code=packet['code'], consent=True))")
    now=datetime.now(timezone.utc)
    envelope=dict(source=source,image=image,starts_at=now.isoformat(),
                  ends_at=(now+timedelta(minutes=5)).isoformat())
    grant=login(auth['SAMPLES']/'group-g2c.invite',envelope,ops,expected_member=True)
    name=run+'-s55-'+feature
    ops['save'](HERE/(name+'-intent.json'),compact(envelope))
    output=ops['captured'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',auth['ROLES'],source,image,PROGRAM],
                           compact(dict(feature=feature,ends_at=envelope['ends_at'],**grant)),name=name,timeout=240)
    for line in output.stdout.splitlines():
        print(json.dumps(json.loads(line),ensure_ascii=False))
    return output.returncode


if __name__=='__main__':
    raise SystemExit(main())
