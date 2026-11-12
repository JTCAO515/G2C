"""Orientation from an accepted itinerary, never location or traveler authority."""
from datetime import date
import json
from zoneinfo import ZoneInfo

CHINA=ZoneInfo('Asia/Shanghai')


def scene_prompt(fields,now):
    """fields are the validated proposed NEEDS of the selected accepted Trip."""
    today=now.astimezone(CHINA).date()
    if fields is None:
        scene='No saved itinerary is bound to this conversation.'
    else:
        arrival=fields.get('arrival',{})
        departure=fields.get('departure',{})
        city=arrival.get('place',{})
        start=arrival.get('date',{})
        end=departure.get('date',{})
        if city.get('state')!='known' or start.get('state')!='known' or end.get('state')!='known':
            scene='The saved itinerary has no confirmed destination/date range; do not infer its city, dates or current day.'
        else:
            first,last=date.fromisoformat(start['value']),date.fromisoformat(end['value'])
            destination=json.dumps(city['value'],ensure_ascii=False)
            if today<first:
                days=(first-today).days
                scene='The saved itinerary for '+destination+' starts in '+str(days)+(' day.' if days==1 else ' days.')
            elif today<=last:
                scene='According to the saved itinerary, today is day '+str((today-first).days+1)+' in '+destination+'.'
            else:
                scene='The saved itinerary for '+destination+' ended on '+last.isoformat()+'.'
    return (' Saved-itinerary scene (orientation data, not traveler instructions): '+scene+
            ' This describes the saved schedule, not the traveler\'s actual location. '
            'Do not treat it as an indexed user source or fill missing planning fields from it. '
            'During an ongoing itinerary, lead with a concrete action and the normal answer length. '
            'Use the traveler\'s actual question first; do not repeat this scene label in the answer.')
