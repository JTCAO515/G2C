"""Project the historical version proven by a Lio save receipt."""
import json
from hashlib import sha256

from cj_trip.auth_boundary import Boundary
from cj_trip.domain import Denied, packed
from cj_message.demo_dialogue import LIO_VERSION, LIO_VERSION_V3

from .local_app import trip_resolver


class LioTripCards:
    def __init__(self, database, checker,*,calendar=False):
        resolve = trip_resolver(database)
        self.database,self.calendar=database,calendar
        self.boundary = Boundary(checker, resolve, structured=True,calendar=calendar)

    def read(self, token, binding, *, edit=False,protocol=LIO_VERSION,conversion=False):
        def original(context):
            if protocol==LIO_VERSION_V3 and not self.calendar:
                raise Denied('calendar message requires new Lio reader')
            if conversion:
                from cj_trip.calendar_conversion import DateConvert
                with self.database.connect(binding.scope) as connection:
                    row=connection.execute('SELECT a.original_input FROM cj_trip_needs_action a '
                        'JOIN cj_trip_needs_basis b USING(scope,proposal_id) WHERE a.scope=%s AND a.action_id=%s '
                        'AND b.message_scope=%s AND b.run_id=%s',
                        (context.metadata.scope,'lio-date-'+binding.run_id,binding.scope,binding.run_id)).fetchone()
                if row is None:return b'null'
                receipt=context.calendar_conversion_receipt(DateConvert.parse(bytes(row[0])))
                if receipt is None or receipt['committed'] is not True:return b'null'
                trip_id,version=receipt['trip_id'],receipt['trip_version']
            else:
                if protocol==LIO_VERSION_V3:
                    receipt=context.calendar_edit_receipt(binding) if edit else context.calendar_plan_receipt(binding)
                else:
                    receipt=context.lio_edit_receipt(binding) if edit else context.lio_plan_receipt(binding)
                if receipt is None:return b'null'
                trip_id,version=receipt.trip_id,receipt.committed_version
            revisions = context.lio_revisions(trip_id, before=version + 1, limit=1)
            if len(revisions) != 1 or revisions[0].version != version:
                raise Denied('original saved itinerary unavailable')
            return packed(calendar_card(revisions[0]) if self.calendar else _card(revisions[0]))

        return json.loads(self.boundary.with_operation(token, original))


def _card(trip):
    value = json.loads(trip.content)
    if value.get('content_version') == 'structured.3':
        raise Denied('calendar itinerary requires the new Lio reader')
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


def calendar_card(trip):
    """Project an already protected, validated revision without losing empty days."""
    value = json.loads(trip.content)
    if value['content_version'] == 'structured.3':
        days = [dict(day, items=[]) for day in value['days']]
        for item in value['items']:
            start, end = item['schedule']['start'], item['schedule']['end']
            days[start['day_index'] - 1]['items'].append(dict(
                item_id=item['id'], label=item['text'], start_time=start['time'].get('value'),
                end_time=end['time'].get('value'), fixed=item['fixed'].get('value')))
        calendar, checks = value['calendar'], value['date_checks']
    else:
        days = _card(trip)['days']
        calendar = checks = None
    return dict(version='LIO-trip-card.2', trip_id=trip.trip_id, trip_version=trip.version,
                content_version=value['content_version'], content_sha256=sha256(trip.content).hexdigest(),
                title=value['title'], calendar=calendar, days=days, date_checks=checks)
