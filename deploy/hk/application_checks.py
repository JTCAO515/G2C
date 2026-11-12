"""Exact-source application checks, preserving superseded CI history."""
import re

REQUIRED=frozenset({'changes','python','swift-packages','ios-app','swift','postgres','pr-lint',
                   *(f'postgres-shard ({index})' for index in range(4))})


def require_exact_checks(source,payload):
    """Validate a complete GitHub check-run response; never accept partial pages.

    The deployment operator reads commit statuses separately. Every latest
    returned check must pass, including external checks beyond REQUIRED.
    """
    if type(source) is not str or re.fullmatch('[a-f0-9]{40}',source) is None:
        raise ValueError('exact application source required')
    if (type(payload) is not dict or type(payload.get('check_runs')) is not list or
            type(payload.get('total_count')) is not int or payload['total_count']!=len(payload['check_runs'])):
        raise ValueError('complete exact-source check inventory required')
    latest={};identities=set()
    for check in payload['check_runs']:
        if (type(check) is not dict or type(check.get('id')) is not int or check['id']<=0 or check['id'] in identities or
                type(check.get('name')) is not str or not check['name'] or check.get('head_sha')!=source):
            raise ValueError('invalid exact-source check identity')
        identities.add(check['id'])
        if check['name']not in latest or check['id']>latest[check['name']]['id']:
            latest[check['name']]=check
    if not REQUIRED<=latest.keys():raise ValueError('required exact-source checks missing')
    if any(check.get('status')!='completed' or check.get('conclusion')!='success'for check in latest.values()):
        raise ValueError('latest exact-source checks must all succeed')
    return latest
