"""Scene packs (ADR-0010 domains: travel, business) and their switches (#1737).

Not the dialogue-stage ``Scene`` in ``lio_exploration_policy``: a scene pack is
the domain a task belongs to. Packs and switches are reviewed JSON under
``scene_packs/``; other tickets read them through this module and never edit
the format. Each pack states its knowledge sources, the tools it may use (ids
from the app's tool registry, #1724), flow templates, risk rules and what it
can commit to. Every switch for something new starts off; travel stays on so
build 57 behaviour is unchanged.

Validation fails closed: unknown keys, unknown tools or cities, missing
English/Chinese text or a switch for a pack that does not exist raise.
"""
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re

from cj_strict_json import reject_duplicates

DIRECTORY=Path(__file__).with_name('scene_packs')
PACKS=('travel','business')
# The app's tool registry ids (ios/.../LioToolRegistry.swift, #1724); a test keeps them equal.
KNOWN_TOOLS=frozenset({'arrival','attraction-booking','currency','hotels','local-support','menu-order','metro-guide',
    'nearby','payment-guide','return-hotel','roadbook','show-cards','taxi','translation','transport'})
KNOWN_CITIES=frozenset({'beijing','shanghai','guangzhou','shenzhen','chengdu','chongqing','guilin'})
_ID=re.compile(r'[a-z][a-z0-9-]{0,47}')


class ScenePackError(ValueError):
    pass


@dataclass(frozen=True)
class ScenePack:
    name:str
    title:dict
    languages:tuple
    cities:tuple
    knowledge:tuple
    tools:tuple
    flows:tuple
    risk_rules:tuple
    commitments:tuple


@dataclass(frozen=True)
class Switches:
    scene_packs:dict
    cities:dict
    human_service:bool
    payments:bool
    medical:bool


def _read(path):
    return json.loads(path.read_bytes(),object_pairs_hook=reject_duplicates(ScenePackError,'duplicate_scene_pack_key'))


def _require(condition,error):
    if not condition:raise ScenePackError(error)


def _words(value,error):
    _require(type(value) is dict and set(value)=={'en','zh'}
             and all(type(text) is str and 0<len(text)<=500 for text in value.values()),error)
    return dict(value)


def _ids(items,error):
    ids=[item['id'] for item in items]
    _require(all(type(i) is str and _ID.fullmatch(i) for i in ids) and len(set(ids))==len(ids),error)


def _knowledge(item):
    _require(type(item) is dict and set(item)=={'id','source','verified_on','review_by'}
             and type(item['source']) is str and item['source'].startswith('https://'),'scene_pack_knowledge_invalid')
    try:verified,review=date.fromisoformat(item['verified_on']),date.fromisoformat(item['review_by'])
    except (TypeError,ValueError):raise ScenePackError('scene_pack_knowledge_dates_invalid') from None
    _require(verified<review,'scene_pack_knowledge_dates_invalid')
    return dict(item)


def load_pack(name,directory=DIRECTORY):
    _require(name in PACKS,'unknown_scene_pack')
    data=_read(directory/(name+'.json'))
    _require(type(data) is dict and set(data)=={'version','scene_pack','title','note','languages','cities','knowledge',
        'tools','flows','risk_rules','commitments'} and data['version']=='g2c-scene-pack.1'
        and data['scene_pack']==name and type(data['note']) is str,'scene_pack_shape_invalid')
    title=_words(data['title'],'scene_pack_title_invalid')
    _require(data['languages']==['en','zh'],'scene_pack_languages_invalid')
    cities=data['cities']
    _require(type(cities) is list and len(set(cities))==len(cities) and set(cities)<=KNOWN_CITIES,'scene_pack_cities_invalid')
    tools=data['tools']
    _require(type(tools) is list and tools and len(set(tools))==len(tools) and set(tools)<=KNOWN_TOOLS,'scene_pack_tools_invalid')
    for key in ('knowledge','flows','risk_rules','commitments'):
        _require(type(data[key]) is list and all(type(item) is dict for item in data[key]),'scene_pack_'+key+'_invalid')
    knowledge=tuple(_knowledge(item) for item in data['knowledge'])
    _ids(knowledge,'scene_pack_knowledge_invalid')
    for flow in data['flows']:
        _require(set(flow)=={'id','title','steps'} and type(flow['steps']) is list and flow['steps'],'scene_pack_flows_invalid')
        _words(flow['title'],'scene_pack_flows_invalid')
        for step in flow['steps']:_words(step,'scene_pack_flows_invalid')
    _ids(data['flows'],'scene_pack_flows_invalid')
    for rule in data['risk_rules']:
        _require(set(rule)=={'id','rule'},'scene_pack_risk_rules_invalid');_words(rule['rule'],'scene_pack_risk_rules_invalid')
    _ids(data['risk_rules'],'scene_pack_risk_rules_invalid')
    _require(data['risk_rules'],'scene_pack_risk_rules_required')
    for item in data['commitments']:
        _require(set(item)=={'id','upto','evidence'},'scene_pack_commitments_invalid')
        _words(item['upto'],'scene_pack_commitments_invalid');_words(item['evidence'],'scene_pack_commitments_invalid')
    _ids(data['commitments'],'scene_pack_commitments_invalid')
    _require(data['commitments'],'scene_pack_commitments_required')
    return ScenePack(name,title,tuple(data['languages']),tuple(cities),knowledge,tuple(tools),
        tuple(data['flows']),tuple(data['risk_rules']),tuple(data['commitments']))


def load_switches(directory=DIRECTORY):
    data=_read(directory/'switches.json')
    _require(type(data) is dict and set(data)=={'version','note','scene_packs','cities','human_service','payments','medical'}
             and data['version']=='g2c-scene-switches.1','scene_switches_shape_invalid')
    _require(type(data['scene_packs']) is dict and set(data['scene_packs'])==set(PACKS)
             and all(type(value) is bool for value in data['scene_packs'].values()),'scene_switches_packs_invalid')
    _require(all(type(data[name]) is bool for name in ('human_service','payments','medical')),'scene_switches_flags_invalid')
    cities=data['cities']
    _require(type(cities) is dict and set(cities)<=set(PACKS),'scene_switches_cities_invalid')
    for pack,values in cities.items():
        _require(type(values) is dict and set(values)==set(load_pack(pack,directory).cities)
                 and all(type(value) is bool for value in values.values()),'scene_switches_cities_invalid')
    return Switches(dict(data['scene_packs']),{pack:dict(values) for pack,values in cities.items()},
        data['human_service'],data['payments'],data['medical'])


def active_packs(switches=None,directory=DIRECTORY):
    """Packs whose switch is on, in fixed order."""
    switches=switches or load_switches(directory)
    return tuple(load_pack(name,directory) for name in PACKS if switches.scene_packs[name])


def city_enabled(pack,city,switches=None,directory=DIRECTORY):
    """A pack without a city list is not city-gated; otherwise the pack and that city must both be on."""
    switches=switches or load_switches(directory)
    if not switches.scene_packs.get(pack.name):return False
    if not pack.cities:return True
    return city in pack.cities and switches.cities.get(pack.name,{}).get(city) is True
