"""Additive city-bound weather query; old FACT-query.1 remains unchanged."""
from dataclasses import asdict,dataclass
from datetime import date
import json
import re

from cj_fact.model import DateRange
from cj_fact.policy import FactFailure
from cj_strict_json import reject_duplicates
from cj_usage.authorization_budget import canonical
from .lio_city import CityReference

VERSION='LIO-weather-query.1'
CITY_EFFECT='lio_weather_city.1:'
PUBLIC_FORECASTS={
 '110000':'101010100','310000':'101020100','510100':'101270101','610100':'101110101',
 '450300':'101300501','440100':'101280101','330100':'101210101',
}


@dataclass(frozen=True)
class WeatherQuery:
 city:CityReference
 dates:DateRange
 fact_key:str='weather'

 @property
 def region(self):return self.city.adcode
 @property
 def conditions(self):return {'calendar_timezone':self.city.timezone}


def encode_query(city,start,end):
 return canonical(dict(version=VERSION,city=asdict(city),dates=dict(start=start,end=end)))


def decode_query(raw):
 if type(raw) is not bytes or not 0<len(raw)<=8192:raise FactFailure('bounded_city_weather_query_required')
 try:
  value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate city weather field'))
  if type(value) is not dict or value.keys()!={'version','city','dates'} or value['version']!=VERSION:
   raise ValueError('city weather version required')
  city=value['city']
  if type(city) is not dict or city.keys()!={'adcode','name','province','parent_city','level','timezone'}:
   raise ValueError('confirmed administrative city required')
  if type(city['adcode']) is not str or re.fullmatch('[0-9]{6}',city['adcode']) is None:
   raise ValueError('original administrative code required')
  for key in ('name','province','timezone'):
   if type(city[key]) is not str or not city[key] or len(city[key].encode())>256:
    raise ValueError('original city metadata required')
  if city['parent_city'] is not None and (type(city['parent_city']) is not str or not city['parent_city'] or len(city['parent_city'].encode())>256):
   raise ValueError('bounded parent city required')
  from zoneinfo import ZoneInfo
  ZoneInfo(city['timezone'])
  if city['level'] not in ('province','city','district'):raise ValueError('administrative destination level required')
  dates=value['dates']
  if type(dates) is not dict or dates.keys()!={'start','end'}:raise ValueError('explicit forecast dates required')
  return WeatherQuery(CityReference(**city),DateRange(date.fromisoformat(dates['start']),date.fromisoformat(dates['end'])))
 except (ValueError,TypeError,KeyError,UnicodeError) as error:
  raise FactFailure('invalid_city_weather_query') from error


def reference(adcode):
 code=PUBLIC_FORECASTS.get(adcode)
 return None if code is None else 'https://www.weather.com.cn/weather/'+code+'.shtml'
