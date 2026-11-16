"""B-issued client for the fixed serialized host reader; never a sender.

Native facts are returned, not normalized PASS/qualification labels. C's
reviewed adapter must join them to actual A UI originals and judge them.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from cj_api.runtime_private import read_private
from cj_usage.authorization_budget import canonical
from cj_strict_json import reject_duplicates


def load(raw):return json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate App host field'))


def call(config,request):
    qraw=read_private(config['local_qualification'],131072)
    q=load(qraw)
    if hashlib.sha256(qraw).hexdigest()!=config['qualification_sha256']:
        raise ValueError('issued App qualification changed')
    if request['expected_source']!=q['source']or request['plan_sha256']!=q['plan_sha256']:
        raise ValueError('original App source/plan changed')
    locale=config['request_locale']
    if locale not in('zh','en'):raise ValueError('explicit original locale required')
    raw=read_private(config['token_files'][locale],16384)
    token=raw.decode('utf-8').strip()if config['token_format']=='jwt'else load(raw)['access_token']
    native=dict(request,token=token)
    command='python3 -B '+shlex.quote(config['remote_dispatcher'])+' '+shlex.quote(config['server_qualification'])
    envelope=dict(qualification_sha256=config['qualification_sha256'],request=native)
    result=subprocess.run(['ssh','-i',config['ssh_key_file'],'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
        config['host'],command],input=canonical(envelope),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
    if result.returncode:
        diagnostic=dict(version='G2C-App-smoke-client-failure.1',return_code=result.returncode,
            stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),phase='host_original_read')
        raise ValueError(json.dumps(diagnostic,sort_keys=True))
    if len(result.stdout)>4_500_000:raise ValueError('bounded native host response required')
    value=load(result.stdout)
    if(value.get('version')!='G2C-App-smoke-host-read.1'or value.get('qualification_sha256')!=config['qualification_sha256']):
        raise ValueError('original host response changed')
    if type(value.get('actual_roles'))is not dict or set(value['actual_roles'])!={'api','worker'}:
        raise ValueError('both actual App roles required')
    if any((v['source'],v['image'])!=(q['source'],q['image'])for v in value['actual_roles'].values()):
        raise ValueError('actual App image/source changed')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    raw=sys.stdin.buffer.read(524289)
    if len(raw)>524288:raise ValueError('bounded App reader request required')
    config=load(read_private(args.config,131072));request=load(raw)
    if 'token'in request:raise ValueError('client selects only its issued private credential file')
    print(canonical(call(config,request)).decode('utf-8'))


if __name__=='__main__':main()
