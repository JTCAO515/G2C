"""B-only append of approved manual-test scopes to the original A allocation."""
import argparse
import json
import os
from pathlib import Path
import re
import stat

from cj_api.local_app import ISSUER,scope_for
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import AuthorizationBudget,HK_JOURNAL_ROOT,HK_PRODUCER
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.sublimits import scope_hash,snapshot
from .configuration import authorization,beta_subjects,load_secret_environment


def allocate_manual_tests(budget,subjects,invited,*,apply=False):
    if (type(subjects) is not list or not 1<=len(subjects)<=198
            or any(type(s) is not str or re.fullmatch(r'm4-synthetic-demo-[a-f0-9]{12}',s) is None
                   or s not in invited for s in subjects) or len(set(subjects))!=len(subjects)):
        raise ValueError('explicit_admitted_unique_manual_test_subjects_required')
    keys=sorted(scope_hash(scope_for(ISSUER,s))for s in subjects)
    budget.check_date()
    with (budget.mutation() if apply else budget.connect()) as db:
        if not apply:
            db.execute('BEGIN');budget.require_producer(db)
        if snapshot(db) is None or db.execute("SELECT 1 FROM sublimit WHERE line='A'").fetchone()!=(1,):
            raise BudgetUnknown('existing_manual_allocation_required')
        missing=[]
        for key in keys:
            row=db.execute('SELECT line FROM scope_sublimit WHERE scope_hash=?',(key,)).fetchone()
            if row is None:missing.append(key)
            elif row!=('A',):raise BudgetUnknown('existing_scope_allocation_cannot_be_reassigned')
        if apply:
            db.executemany("INSERT INTO scope_sublimit(scope_hash,line) VALUES(?,'A')",[(key,)for key in missing])
    return dict(version='G2C-manual-test-allocation.1',line='A',requested=len(keys),
        existing_before=len(keys)-len(missing),unbound_before=len(missing),
        added=len(missing)if apply else 0,applied=apply)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    fd=os.open(args.manifest,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb')as source:
        meta=os.fstat(source.fileno())
        if not stat.S_ISREG(meta.st_mode)or meta.st_uid!=os.getuid()or stat.S_IMODE(meta.st_mode)!=0o600:
            raise ValueError('owned_0600_allocation_manifest_required')
        raw=source.read(65537)
    if len(raw)>65536:raise ValueError('bounded_allocation_manifest_required')
    value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate allocation field'))
    if type(value) is not dict or set(value)!={'version','subjects'}or value['version']!='G2C-manual-test-allocation.1':
        raise ValueError('explicit_manual_test_allocation_manifest_required')
    load_secret_environment('worker');authorization()
    if os.environ.get('CJ_M4_BUDGET_PRODUCER')!=HK_PRODUCER:raise ValueError('original_hk_producer_required')
    _,invited=beta_subjects()
    budget=AuthorizationBudget(HK_JOURNAL_ROOT,authorization_guard=authorization,demo=True)
    print(json.dumps(allocate_manual_tests(budget,value['subjects'],invited,apply=args.apply),sort_keys=True))


if __name__=='__main__':main()
