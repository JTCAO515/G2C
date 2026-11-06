"""Six GETs of an existing synthetic RUN; transport evidence, never quality PASS.

No message submission, model SDK, financial journal or canonical phase access.
The original submit clock is unavailable: GET timings cannot fill answer latency.
"""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import re
import ssl
import stat
import subprocess
import time

import certifi
import httpx

BASE='https://api-beta.go2china.space'
MESSAGE='hk-api-smoke-20261106-06'
RUN='0d92e40a-847c-47e4-8b32-c483ee249724'
GENERATION='5c70ee0510434cc6a94bc9fe6de99767'
SAMPLES=6
BOUND=1048576


def save(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temporary.chmod(0o600);temporary.replace(path)


def bearer(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        meta=os.fstat(source.fileno())
        if not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode)!=0o600 or meta.st_uid!=os.getuid():
            raise ValueError('owned_0600_short_bearer_required')
        raw=source.read(16385)
    if len(raw)>16384:raise ValueError('bounded_bearer_required')
    token=raw.decode('ascii').strip()
    if re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',token) is None:
        raise ValueError('short_JWT_file_required')
    return token


def network_context():
    if platform.system()!='Darwin':raise ValueError('approved_Mac_client_required')
    result=dict(label='China-mainland Mac + VPN',location_basis='JT stated China mainland; VPN on',
        actual_egress_location='UNKNOWN',settings_changed=False)
    for key,args in (('default_interface',['route','-n','get','default']),
                     ('target_interface',['route','-n','get','47.83.147.176'])):
        observed=subprocess.run(args,capture_output=True,text=True)
        match=re.search(r'^\s*interface:\s*(\S+)',observed.stdout,re.M)
        result[key]=match[1] if observed.returncode==0 and match else 'UNKNOWN'
    observed=subprocess.run(['scutil','--proxy'],capture_output=True,text=True)
    result['proxy_flags']={k:int(v) for k,v in re.findall(
        r'^\s*(HTTPEnable|HTTPSEnable|SOCKSEnable|ProxyAutoConfigEnable|ProxyAutoDiscoveryEnable)\s*:\s*([01])\s*$',observed.stdout,re.M)}
    result['proxy_query_exit']=observed.returncode
    return result


def _pairs(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate_response_field')
        value[key]=item
    return value


def collect(client,output,network,*,clock=time.perf_counter):
    output.mkdir(parents=True,mode=0o700);(output/'raw').mkdir(mode=0o700)
    plan=dict(kind='target_network_read_diagnostic',endpoint=BASE,method='GET',
        message_id=MESSAGE,run_id=RUN,generation=GENERATION,planned_n=SAMPLES,
        source_origin='B public06; not a C smoke/full observation',network=network,
        serving_backend_expected='5348e7b0077b6c50323325f09d064aeac8bdbcd7',
        created_at=datetime.now(timezone.utc).isoformat(),collector_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        provider_dispatch_permitted=False,financial_ledger_access=False,canonical_phase_access=False,
        clock_scope='original GET to decoded response; original user POST clock unavailable',
        quality_release_decision='UNRUN',first_body_seconds='UNRUN',full_answer_seconds='UNRUN')
    save(output/'plan.json',plan);rows=[]
    for index in range(SAMPLES):
        started=clock();row=dict(attempt=index+1,method='GET',status='UNKNOWN',http_status=None,
            first_decoded_bytes_seconds=None,protected_read_seconds=None)
        try:
            with client.stream('GET',BASE+'/v1/run-display',params=dict(message_id=MESSAGE)) as response:
                row['http_status']=response.status_code;parts=[];size=0
                for part in response.iter_bytes():
                    if not part:continue
                    if row['first_decoded_bytes_seconds'] is None:row['first_decoded_bytes_seconds']=clock()-started
                    size+=len(part)
                    if size>BOUND:raise ValueError('response_bound_exceeded')
                    parts.append(part)
                raw=b''.join(parts);row['http_response_seconds']=clock()-started
                row['response_bytes']=size;row['response_sha256']=sha256(raw).hexdigest()
                if response.status_code!=200:
                    row.update(status='FAIL',error_kind='non_200_response')
                else:
                    data=json.loads(raw.decode('utf8'),object_pairs_hook=_pairs)
                    if type(data) is not dict or data.get('version')!='RUN-display.6' or type(data.get('snapshot')) is not dict:
                        raise ValueError('protected_display_version_required')
                    snap=data['snapshot']
                    if ((snap.get('run_id'),snap.get('message_id'),snap.get('generation'))!=(RUN,MESSAGE,GENERATION)
                            or snap.get('status')!='completed' or snap.get('text_state')!='complete'
                            or type(snap.get('text')) is not str or not snap['text'].strip()):
                        raise ValueError('same_original_complete_snapshot_required')
                    text=snap['text'].encode('utf8')
                    save(output/'raw'/f'{index+1:02d}.json',dict(version=data['version'],snapshot={
                        k:snap[k] for k in ('run_id','message_id','generation','status','text_state','text')}))
                    row.update(status='PASS',protected_read_seconds=row['http_response_seconds'],
                        text_bytes=len(text),text_sha256=sha256(text).hexdigest())
        except httpx.HTTPError as error:
            row['error_kind']=type(error).__name__  # Never persist headers, tokens or exception text.
            row['http_response_seconds']=clock()-started
        except (ValueError,UnicodeError,RecursionError) as error:
            row.update(status='FAIL',error_kind=type(error).__name__,http_response_seconds=clock()-started)
        rows.append(row);save(output/'observations.json',rows)
        if row['status']!='PASS':break  # No automatic retries or invalid-read loop.
    valid=sorted(r['protected_read_seconds'] for r in rows if r['status']=='PASS')
    result=dict(plan=plan,observations=rows,planned_n=SAMPLES,
        outcomes={s:sum(r['status']==s for r in rows) for s in ('PASS','FAIL','UNKNOWN')},
        unrun_n=SAMPLES-len(rows),valid_read_timing=dict(known_n=len(valid),planned_n=SAMPLES,
            p50=valid[math.ceil(.5*len(valid))-1] if valid else None,
            p95=valid[math.ceil(.95*len(valid))-1] if valid else None,max=max(valid) if valid else None),
        availability='FAIL' if any(r['status']=='FAIL' for r in rows) else 'PASS' if len(valid)==SAMPLES else 'UNKNOWN',
        quality_release_decision='UNRUN',
        submitted_messages=0,model_or_tool_dispatches=0,actual_paid_cost='UNKNOWN')
    save(output/'report.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bearer-file',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():print('READ_ONLY: existing observation retained; no request');return 0
    network=network_context();token=bearer(args.bearer_file)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.load_verify_locations(cafile=certifi.where())
    if context.keylog_filename is not None or not context.check_hostname or context.verify_mode!=ssl.CERT_REQUIRED:
        raise ValueError('verified_TLS_without_keylogging_required')
    with httpx.Client(headers={'Authorization':'Bearer '+token},verify=context,
                      trust_env=False,follow_redirects=False,timeout=45) as client:
        result=collect(client,args.output,network)
    print(json.dumps(dict(outcomes=result['outcomes'],unrun_n=result['unrun_n'],
        valid_read_timing=result['valid_read_timing'],quality_release_decision='UNRUN',new_dispatches=0)))
    return 0 if result['availability']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
