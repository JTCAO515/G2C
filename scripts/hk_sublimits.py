"""B-only original-journal sublimit activation/readback; never a provider call."""
import argparse
import json
import os
from pathlib import Path
import stat

from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import AuthorizationBudget,HK_JOURNAL_ROOT,HK_PRODUCER,CNY_SCALE
from cj_usage.sublimits import activate,read,scope_hash
from cj_api.local_app import ISSUER,scope_for
from deploy.hk.configuration import authorization,beta_subjects,load_secret_environment


def grants():
    def limit(cap,*,active=None,model=None,tools=None,calls=None,model_calls=None,tool_calls=None):
        return dict(cap=None if cap is None else cap*CNY_SCALE,
            active_cap=None if cap is None else (cap if active is None else active)*CNY_SCALE,
            model_cap=None if model is None else model*CNY_SCALE,
            tool_cap=None if tools is None else tools*CNY_SCALE,max_calls=calls,
            model_calls=model_calls,tool_calls=tool_calls)
    return dict(A=limit(None),B=limit(None),L=limit(50),C=limit(100),
        E=limit(50,model=50,tools=5,calls=400,tool_calls=50),
        F=limit(15,active=5,model=3,tools=2,calls=320,model_calls=160,tool_calls=160))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['activate','read'])
    parser.add_argument('--subjects',type=Path)
    args=parser.parse_args()
    load_secret_environment('worker');authorization()
    if os.environ.get('CJ_M4_BUDGET_PRODUCER')!=HK_PRODUCER:
        raise ValueError('existing HK producer required')
    budget=AuthorizationBudget(HK_JOURNAL_ROOT,authorization_guard=authorization,demo=True)
    if args.command=='activate':
        if args.subjects is None:raise ValueError('owned subject allocation manifest required')
        fd=os.open(args.subjects,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as source:
            info=os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
                raise ValueError('owned0600 subject allocation manifest required')
            raw=source.read(65537)
        if len(raw)>65536:raise ValueError('subject manifest bound exceeded')
        data=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate allocation subject'))
        if type(data) is not dict or set(data)!=set(grants()):raise ValueError('explicit A/B/L/C/E/F subjects required')
        invited,_=beta_subjects();bindings={}
        for line,subjects in data.items():
            if type(subjects) is not list or not subjects or any(type(s) is not str or s not in invited for s in subjects):
                raise ValueError('existing admitted synthetic subjects required')
            for subject in subjects:
                key=scope_hash(scope_for(ISSUER,subject))
                if key in bindings:raise ValueError('one original subject cannot borrow another line allocation')
                bindings[key]=line
        activate(budget,grants(),bindings)
    print(json.dumps(dict(version='G2C-original-sublimits.1',lines=read(budget),
        actual_paid_cny='UNKNOWN',f_phase='allocated15; first3model+2tools active until original D/R stage gate',
        old_holds='retained in parent; no reset or release'),sort_keys=True))


if __name__=='__main__':main()
