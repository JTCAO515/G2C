"""Code-owned scene/question/exit policies for #922 §3.3–3.4, opt-in native4."""
from dataclasses import dataclass
from enum import Enum
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from cj_message.lio_exploration_schema import QuestionGroup as ModelQuestionGroup

from .lio_exploration_factors import BY_KEY, FACTORS
from cj_message.lio_context import display_answer


class Scene(str,Enum):
    EXPLORATION='exploration'
    ADJUSTMENT='adjustment'
    TODAY='today'
    PRACTICAL='practical'
    EMERGENCY='emergency'


def choose_scene(intent, saved_phase):
    """Intent is parsed data; saved_phase comes from the protected #845 context.

    A saved current-day itinerary is orientation, never a GPS/presence claim.
    """
    if intent=='emergency':return Scene.EMERGENCY
    if intent=='practical':return Scene.PRACTICAL
    if saved_phase=='on_trip':return Scene.TODAY
    if saved_phase in ('before_trip','undated') and intent=='adjust':return Scene.ADJUSTMENT
    return Scene.EXPLORATION


def next_question_count(previous_count, answered_count, *, volunteered=False, short=False, plan_now=False):
    if plan_now:return 0
    if previous_count is None:return 4
    if volunteered:return min(4,previous_count+1)
    # The specific one-answer/short-answer case takes priority when a small
    # previous group also happens to make one answer at least half the group.
    if answered_count==1 or short:return max(0,previous_count-1)
    if previous_count and answered_count*2>=previous_count:return min(4,previous_count+1)
    return previous_count


def candidates(profile,count,*,stage='exploration'):
    phase={'exploration':0,'refinement':1,'adjustment':2}[stage]
    eligible=[factor for factor in FACTORS if factor.key not in profile or
              profile[factor.key].state=='default']
    return tuple(sorted(eligible,key=lambda factor:-factor.weights[phase])[:count])


_CONTROL=re.compile(r'[\x00-\x1f\x7f-\x9f\u2028\u2029]')
_ACTION_CLAIM=re.compile(r'已(?:经)?(?:被|为你|帮你)?(?:记住|记下|保存|预订|付款)|保存成功|'
    r"\b(?:I|we)(?: have|'ve)?\s+(?:saved|booked|paid|remembered)\b|"
    r"\b(?:is|are|was|were|has been|have been)\s+(?:saved|booked|paid|remembered)\b",re.I)


class _DTO(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')


class _Option(_DTO):
    id:str=Field(min_length=1,max_length=128)
    display_text:str=Field(min_length=1,max_length=400)
    send_text:str=Field(min_length=1,max_length=400)


class _Group(_DTO):
    factor_key:str
    question:str=Field(min_length=1,max_length=400)
    multiple:bool
    options:list[_Option]=Field(min_length=3,max_length=4)


@dataclass(frozen=True)
class Questions:
    groups:tuple[dict,...]
    used_question_bank:bool


def _bounded(text,locale):
    # The old filter uses Unicode word boundaries. Separate a Latin internal
    # token from adjacent CJK text for detection, without rewriting user text.
    check=re.sub(r'([A-Za-z0-9_])(?=[\u3400-\u9fff])',r'\1 ',text)
    check=re.sub(r'([\u3400-\u9fff])(?=[A-Za-z0-9_])',r'\1 ',check)
    return bool(text.strip()) and display_answer(check,locale)==check and _ACTION_CLAIM.search(text.replace('’',"'")) is None and _CONTROL.search(text) is None and (
        len(text)<=80 if locale=='zh' else len(text.split())<=50)


def questions(scene, selected, proposed, locale,*,option_variants=None):
    """Validate the model's question wording at its boundary, otherwise use bank.

    Stable ids and canonical send_text preserve what a selected option means;
    the model can rewrite the visible label/question within the allowed choice.
    This fallback is for a completed model result, not a supplier-error retry.
    """
    if scene!=Scene.EXPLORATION or not selected:return Questions((),False)
    fallback=tuple(factor.question(locale) for factor in selected)
    if not isinstance(proposed,list) or len(proposed)!=len(selected):return Questions(fallback,True)
    allowed={factor.key:factor for factor in selected};groups=[];seen=set()
    try:
        for raw in proposed:
            group=ModelQuestionGroup.model_validate(raw)
            factor=allowed.get(group.factor_key)
            if factor is None or group.factor_key in seen:
                return Questions(fallback,True)
            bank={option['id']:option for option in factor.question(locale)['options']}
            option_ids=[option.id for option in group.options]
            if len(set(option_ids))!=len(option_ids) or not set(option_ids)<=bank.keys():
                return Questions(fallback,True)
            if not _bounded(group.question,locale):return Questions(fallback,True)
            for option in group.options:
                if (not _bounded(option.display_text,locale) or
                        option.display_text.strip().casefold() in ('other','其他')):
                    return Questions(fallback,True)
                variants=(option_variants or {}).get(option.id,{})
                if option.display_text!=bank[option.id]['display_text'] and option.display_text not in variants:
                    return Questions(fallback,True)
            seen.add(group.factor_key)
            groups.append(dict(factor_key=group.factor_key,question=group.question,multiple=factor.multiple,
                options=[dict(id=option.id,display_text=option.display_text,send_text=(option_variants or {}).get(option.id,{}).get(
                    option.display_text,bank[option.id]['send_text'])) for option in group.options]))
    except ValidationError:
        return Questions(fallback,True)
    return Questions(tuple(groups),False)


def exits(scene,locale):
    zh=locale=='zh'
    rows={
        Scene.EXPLORATION:(('continue_refining','继续细化','Keep refining'),('plan_now','直接出方案','Plan now')),
        Scene.ADJUSTMENT:(('less_walking','再轻松点','Make it more relaxed'),
            ('more_food','多加点美食','Add more local food'),('later_start','每天晚一点出发','Start each day later')),
        Scene.TODAY:(('today_plan','看看今天的安排',"Show today's itinerary"),
            ('indoor','推荐一个室内去处','Suggest an indoor stop')),
    }.get(scene,())
    return tuple(dict(id=key,display_text=cn if zh else en,send_text=cn if zh else en) for key,cn,en in rows)


def emergency_opening(text,locale):
    medical=re.search(r'急救|受伤|胸痛|无法呼吸|喘不过气|ambulance|injur|chest pain|cannot breathe|can.t breathe',text,re.I)
    phone='120' if medical else '110'
    return ('请立即拨打'+phone+'，并请身边的人协助说明你的位置。' if locale=='zh' else
            'Call '+phone+' now and ask someone nearby to help explain your location.')
