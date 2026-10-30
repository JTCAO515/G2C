from copy import deepcopy
import pytest
from test_structured import document
from cj_trip.structured import validate_document as old
from cj_trip.structured_v2 import validate_document as new
from cj_trip.domain import Proposal,packed


def test_new_minute_precision_preserved_and_old_version_not_relaxed():
    value=document();value['content_version']='structured.2'
    value['items'][0]['schedule']['start']['time']={'state':'known','value':'09:30'}
    new(value)
    candidate=Proposal('p2','trip2',0,'needs-run-synthetic',9999999999,packed(value))
    assert b'09:30"' in candidate.content and b'09:30:00' not in candidate.content
    legacy=deepcopy(value);legacy['content_version']='structured.1'
    with pytest.raises(ValueError):old(legacy)


def test_new_still_rejects_text_time_extra_owner_duplicate_id():
    for mutate in (lambda d:d['items'].append(deepcopy(d['items'][0])),
                   lambda d:d.update(owner='client'),
                   lambda d:d['items'][0]['schedule']['start'].update(time={'state':'known','value':'tomorrow'})):
        value=document();value['content_version']='structured.2';mutate(value)
        with pytest.raises(ValueError):new(value)
