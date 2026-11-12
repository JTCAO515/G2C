"""Deployment gate controls, no GitHub/SSH/configuration mutation."""
import pytest

from deploy.hk.application_checks import REQUIRED,require_exact_checks

SOURCE='a'*40


def inventory():
    rows=[dict(id=index,name=name,head_sha=SOURCE,status='completed',conclusion='success')
        for index,name in enumerate(sorted(REQUIRED),1)]
    return dict(total_count=len(rows),check_runs=rows)


def test_exact_head_latest_success_preserves_cancelled_history():
    data=inventory();old=dict(id=100,name='ios-app',head_sha=SOURCE,status='completed',conclusion='cancelled')
    new={**old,'id':101,'conclusion':'success'}
    data['check_runs'].extend((old,new));data['total_count']+=2
    assert require_exact_checks(SOURCE,data)['ios-app']['id']==101
    assert old['conclusion']=='cancelled' and len(data['check_runs'])==len(REQUIRED)+2


@pytest.mark.parametrize('change',[{'status':'queued','conclusion':None},{'conclusion':'failure'},{'conclusion':'cancelled'},{'conclusion':'skipped'}])
def test_newest_unfinished_or_unsuccessful_is_never_masked_by_old_green(change):
    data=inventory();data['check_runs'].append({**dict(id=200,name='ios-app',head_sha=SOURCE,status='completed',conclusion='success'),**change})
    data['total_count']+=1
    with pytest.raises(ValueError,match='latest exact-source'):require_exact_checks(SOURCE,data)


def test_missing_partial_wrong_source_and_duplicate_identity_fail_closed():
    data=inventory();data['check_runs'].pop();data['total_count']-=1
    with pytest.raises(ValueError,match='missing'):require_exact_checks(SOURCE,data)
    data=inventory();data['total_count']+=1
    with pytest.raises(ValueError,match='complete'):require_exact_checks(SOURCE,data)
    for field,value in (('head_sha','b'*40),('id',1)):
        data=inventory();data['check_runs'][-1][field]=value
        with pytest.raises(ValueError,match='identity'):require_exact_checks(SOURCE,data)
