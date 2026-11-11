"""Project the historical version proven by a Lio save receipt."""
import json

from cj_agent.draft import trip_scope_for
from cj_trip.auth_boundary import Boundary
from cj_trip.domain import Denied, packed

from .local_app import scope_for


class LioTripCards:
    def __init__(self, database, checker):
        def resolve(principal):
            owner = scope_for(principal.issuer, principal.subject)
            return lambda: database.connect(owner), trip_scope_for(owner)

        self.boundary = Boundary(checker, resolve, structured=True)

    def read(self, token, binding, *, edit=False):
        def original(context):
            receipt = context.lio_edit_receipt(binding) if edit else context.lio_plan_receipt(binding)
            if receipt is None:
                return b'null'
            revisions = context.lio_revisions(receipt.trip_id, before=receipt.committed_version + 1, limit=1)
            if len(revisions) != 1 or revisions[0].version != receipt.committed_version:
                raise Denied('original saved itinerary unavailable')
            return packed(_card(revisions[0]))

        return json.loads(self.boundary.with_operation(token, original))


def _card(trip):
    value = json.loads(trip.content)
    days = {}
    for item in value['items']:
        start, end = item['schedule']['start'], item['schedule']['end']
        date = start['date'].get('value')
        days.setdefault(date, []).append(dict(item_id=item['id'], label=item['text'],
            start_time=start['time'].get('value'), end_time=end['time'].get('value'),
            fixed=item['fixed'].get('value')))
    order = sorted(days, key=lambda day: (day is None, day or ''))
    return dict(trip_id=trip.trip_id, title=value['title'],
                days=[dict(date=day, items=days[day]) for day in order])
