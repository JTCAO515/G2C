"""Read-only card facts from the validated proposal and its retained Needs."""
import json


def _known(observation):
    return observation.get('value')


def _wall_time(event):
    day, clock = _known(event['date']), _known(event['time'])
    if day is None or clock is None:
        return None
    return day + 'T' + clock + (_known(event['utc_offset']) or '')


def candidate_days(proposal, capture):
    """Project inside the protected discovery callback, after source validation."""
    document = json.loads(proposal.content)
    snapshot, _ = capture.records()
    confirmed_places = {item['item_id']: _known(item['start']['place'])
                        for item in snapshot.fields.get('fixed_items', ())}
    places = {source['id']: source['text'] for source in document['sources']
              if source['kind'] == 'place'}
    days = {}
    for item in document['items']:
        start, end = item['schedule']['start'], item['schedule']['end']
        start_zone, end_zone = _known(start['timezone']), _known(end['timezone'])
        time_zone = start_zone if start_zone == end_zone else None
        refs = item['source_refs']
        place = places.get(refs[0]) if refs else None
        place = confirmed_places.get(item['id']) or place
        days.setdefault(_known(start['date']), []).append(dict(
            item_id=item['id'], label=item['text'], place=place,
            starts_at=_wall_time(start), ends_at=_wall_time(end), time_zone=time_zone,
            source_ids=refs, fixed=_known(item['fixed'])))
    order = sorted(days, key=lambda day: (day is None, day or ''))
    return [dict(date=day, items=days[day]) for day in order]
