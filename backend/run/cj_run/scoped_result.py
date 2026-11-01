"""Original non-acceptable result effect; no Trip publication authority."""
import re

KINDS=frozenset({'clarification_required','expansion_required'})
_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',re.ASCII)


def effect(kind,result_id):
    if kind not in KINDS or type(result_id) is not str or _ID.fullmatch(result_id) is None:
        raise ValueError('unsupported original scoped result')
    return 'scoped_result:'+kind+':'+result_id


def parse(value):
    parts=value.split(':',2)
    if len(parts)!=3 or parts[0]!='scoped_result' or effect(parts[1],parts[2])!=value:
        raise ValueError('invalid stored scoped result')
    return parts[1],parts[2]


def descriptor(state,original):
    result=state.scoped_result
    if result is None:return None
    return dict(version='RUN-scoped-result.1',kind=result[0],result_id=result[1],
        message_id=state.binding.message_id,run_id=state.binding.run_id,
        input_sha256=original.receipt.input_sha256)
