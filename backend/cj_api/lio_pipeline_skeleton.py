"""Code-owned coverage/count projection before any POI request.

Counts come from protected profile/edge policy; model data supplies names only.
Capacity refusal is explicit, never a truncated or secretly lighter itinerary.
"""
from dataclasses import dataclass
from pydantic import ValidationError
from cj_message.lio_pipeline_schema import Skeleton
from cj_needs.domain import decode,InvalidInput


class SkeletonUnavailable(ValueError):pass
class CapacityExceeded(ValueError):pass


@dataclass(frozen=True)
class DayRecipe:
    day_index:int
    sights:int
    meals:tuple[str,...]


@dataclass(frozen=True)
class Stop:
    item_id:str
    day_index:int
    kind:str
    period:str|None
    name_zh:str
    name_en:str


@dataclass(frozen=True)
class ProposedSkeleton:
    title:str
    stops:tuple[Stop,...]
    areas:tuple[str,...]
    lodging_area:str
    hotels:tuple[tuple[str,str],...]


def recipes(day_count,pace,*,light_first,light_last):
    """Host edge flags are source-checked policy decisions, never model input."""
    if day_count==1 and light_first and light_last:
        raise SkeletonUnavailable('combined edge policy must establish a usable one-day window')
    sights={'relaxed':2,'moderate':3,'packed':4}[pace]
    return tuple(DayRecipe(day,1 if day==1 and light_first or day==day_count and light_last else sights,
        ()if day==day_count and light_last else('dinner',)if day==1 and light_first else('lunch','dinner'))
        for day in range(1,day_count+1))


def parse_skeleton(raw,expected,*,id_prefix,protected_item_count=0,transfer_item_count=0):
    try:value=Skeleton.model_validate(decode(raw))
    except (ValidationError,InvalidInput)as error:raise SkeletonUnavailable('complete typed skeleton required')from error
    if [day.day_index for day in value.days]!=[day.day_index for day in expected]:
        raise SkeletonUnavailable('all requested day ordinals must appear exactly once in order')
    stops=[]
    for day,recipe in zip(value.days,expected,strict=True):
        meals={meal.period:meal.place for meal in day.meals}
        if len(day.sights)!=recipe.sights or len(meals)!=len(day.meals)or set(meals)!=set(recipe.meals):
            raise SkeletonUnavailable('complete code-selected pace and meal periods required')
        proposed=[(place.name_zh,place.name_en)for place in day.sights]+[(place.name_zh,place.name_en)for place in meals.values()]
        if len(set(proposed))!=len(proposed):raise SkeletonUnavailable('distinct proposed stops required')
        for ordinal,place in enumerate(day.sights,1):
            stops.append(Stop(f'{id_prefix}-d{day.day_index}-s{ordinal}',day.day_index,'sight',None,place.name_zh,place.name_en))
        for period in recipe.meals:
            place=meals[period]
            stops.append(Stop(f'{id_prefix}-d{day.day_index}-{period}',day.day_index,'meal',period,
                              place.name_zh,place.name_en))
    # Structured4 has a frozen global60-item bound. Count actual proposed,
    # protected and transfer items, not a made-up global day limit.
    if len(stops)+protected_item_count+transfer_item_count>60:
        raise CapacityExceeded('complete plan exceeds the current representation capacity')
    return ProposedSkeleton(value.title,tuple(stops),tuple(day.area for day in value.days),value.lodging.area,
        tuple((place.name_zh,place.name_en)for place in value.lodging.recommendations))
