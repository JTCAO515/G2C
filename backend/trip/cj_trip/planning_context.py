"""Actual current Trip selection and reuse of its manual fixed/scope checks."""
from dataclasses import dataclass
from copy import deepcopy
from hashlib import sha256
import json
from .domain import Trip,Denied,Conflict,packed
from .manual_needs import EditV2,prepare


@dataclass(frozen=True,repr=False)
class TripContext:
    trip:Trip
    proposed:bytes


def read_current(repository,needs_scope,needs_id):
    with repository.transaction() as cur:
        return current_in_tx(cur,repository,needs_scope,needs_id)


def current_in_tx(cur,repository,needs_scope,needs_id):
    cur.execute('SELECT c.trip_id,c.trip_version,r.version,r.content FROM cj_trip_needs_current c '
        'JOIN cj_trip_record r ON (r.scope,r.trip_id)=(c.scope,c.trip_id) '
        'WHERE c.scope=%s AND c.needs_scope=%s AND c.needs_id=%s',(repository.scope,needs_scope,needs_id))
    row=cur.fetchone()
    if row is None:return None
    if row[1]!=row[2]:raise Denied('current selected Trip version mismatch')
    trip=Trip(row[0],row[2],repository._content(bytes(row[3])))
    from .needs_lineage import current_origin
    origin=current_origin(cur,repository,trip)
    if (origin['needs_scope'],origin['needs_id'])!=(needs_scope,needs_id):raise Denied('selected source identity mismatch')
    return TripContext(trip,origin['proposed'])


def protect_model(original,document):
    """Model cannot turn local fixed intent into an edit authorization."""
    before=json.loads(original.content);old={item['id']:item for item in before['items']}
    new={item['id']:item for item in document['items']}
    if not set(old)<=set(new):raise Conflict('model removed adopted current Trip item')
    changes=[]
    for item_id,item in old.items():
        proposed=new[item_id]
        if proposed['fixed']!=item['fixed']:raise Conflict('model changed adopted fixed intent')
        for field in ('text','schedule'):
            if proposed[field]!=item[field]:changes.append(dict(item_id=item_id,field=field,value=proposed[field]))
    order=[item['id'] for item in document['items'] if item['id'] in old]
    old_order=[item['id'] for item in before['items']]
    # The original manual validator is the single local fixed/selected guard.
    if not changes and order==old_order:return
    raw=packed(dict(version='TRIP-manual-edit.2',request_id='planning-scope-check',trip_id=original.trip_id,
        expected_version=original.version,original_hash=sha256(original.content).hexdigest(),
        title=None,changes=changes,order=order if order!=old_order else None))
    prepare(original,EditV2.parse(raw))
