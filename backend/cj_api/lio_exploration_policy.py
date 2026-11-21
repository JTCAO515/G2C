"""Code-owned scene/question/exit policies for #922 §3.3–3.4, opt-in native4."""
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import Enum
import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from cj_message.lio_exploration_schema import QuestionGroup as ModelQuestionGroup
from cj_draft.rich_adjustment import RichAdjustment
from cj_message.domain import Stored
from cj_run.core import Binding
from cj_trip.domain import packed
from cj_trip.lio_history import TripHead

from .lio_exploration_factors import BY_KEY, FACTORS
from .lio_edit_selection import _QUALIFIED_LABEL, _edit_parts, _replacement_label, match_edit
from .lio_flow_intake import _quoted_data_spans
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


_RELAX = re.compile(r'(?:(?:请|帮我)\s*)?(?:再轻松(?:点|一点)|安排得轻松一点|把行程排得轻松一点)'
                    r'|(?:(?:please|(?:can|could|would) you)\s+)?make (?:it|the trip|my itinerary) more relaxed', re.I)
_FOOD = re.compile(r'(?:(?:请|能|可以|帮我)\s*)?(?:多加点美食|多安排点美食)(?:吗)?'
                   r'|(?:(?:please|(?:can|could|would) you)\s+)?add more (?:local )?food', re.I)
_REMOVE = re.compile(r'(?:(?:请)?去掉\s*|(?:(?:please|(?:can|could|would) you)\s+)?remove\s+)(?P<name>.+)', re.I)
_EXPLICIT_REQUEST = re.compile(r'^(?:请|帮我|能|可以|(?:please|(?:can|could|would) you)\b)',re.I)
_CONDITIONAL_CHANGE = re.compile(
    r'要是|除非|(?:确认|同意|批准|核实|核对)(?:之后|以后|后|了再)|以后再|晚些再|才执行'
    r'|\b(?:until|when|once|pending|approv(?:e|es|ed))\b',re.I)
_QUOTES = {'「': '」', '“': '”', '"': '"', "'": "'"}
_SUGGESTED = frozenset(('sight', 'meal', 'free_time'))
ADJUSTMENT_EFFECT = 'lio_rich_adjustment.1:'


@dataclass(frozen=True)
class SelectedAdjustment:
    scope: RichAdjustment
    kind: str
    replacement: str | None = None


@dataclass(frozen=True)
class AdjustmentAuthorization:
    binding: Binding
    original: Stored
    question_day: date
    selection: SelectedAdjustment

    def matches(self, binding, original, scope):
        return binding == self.binding and original == self.original and scope == self.selection.scope

    def marker(self):
        return packed(dict(version='LIO-scoped-adjustment.1', message_id=self.binding.message_id,
                           run_id=self.binding.run_id, input_sha256=self.original.receipt.input_sha256,
                           question_day=self.question_day.isoformat(), adjustment=self.selection.scope.basis()))


def _unlocked(item):
    return (item['kind'] in _SUGGESTED and item['fixed'] == dict(state='known', value=False)
            and item['verification'] == 'pending' and not item['evidence']
            and item['source_category'] == 'unknown' and not item['source_refs'])


def _literal_name(text):
    text=text.strip()
    if (len(text)>2 and _QUOTES.get(text[0])==text[-1]
            and _quoted_data_spans(text)==((0,len(text)),)):
        return text[1:-1].strip()
    return None


def _qualified_name(text):
    return _QUALIFIED_LABEL.search(text) is not None or _CONDITIONAL_CHANGE.search(text) is not None


def _named_item(items, label):
    label=label.strip()
    literal=_literal_name(label)
    if literal is None and _qualified_name(label):
        return None
    label=label if literal is None else literal
    matches = [item for item in items if item['text'].casefold() == label.casefold()]
    if len(matches) == 1 and _unlocked(matches[0]):
        return matches[0]
    return None


def _optional_sight(items):
    by_day = Counter(item['schedule']['start']['day_index'] for item in items if item['kind'] == 'sight')
    options = []
    for index, item in enumerate(items):
        day = item['schedule']['start']['day_index']
        if item['kind'] == 'sight' and by_day[day] > 1 and _unlocked(item):
            options.append((by_day[day], index))
    return items[max(options)[1]] if options else None


def _request_text(text):
    return text.strip().rstrip('。！!？?.').rstrip()


def matches_adjustment(text):
    text = _request_text(text)
    return (_RELAX.fullmatch(text) is not None or _FOOD.fullmatch(text) is not None
            or _REMOVE.fullmatch(text) is not None or match_edit(text) is not None)


def select_adjustment(trip, text, question_day):
    document = json.loads(trip.content)
    if document.get('content_version') != 'structured.4':
        return None
    calendar = document['calendar']
    if calendar['state'] == 'dated' and date.fromisoformat(calendar['start_date']) <= question_day:
        return None
    question = text.rstrip().endswith(('?', '？'))
    text = _request_text(text)
    if question and not _EXPLICIT_REQUEST.match(text):
        return None
    items = document['items']
    food = _FOOD.fullmatch(text) is not None
    if food or _RELAX.fullmatch(text):
        item = next((row for row in items if row['kind'] == 'free_time' and _unlocked(row)), None) if food else None
        if item is None:
            item = _optional_sight(items)
        if item is None:
            return None
        scope = RichAdjustment(TripHead.from_trip(trip), item['id'], 'replace' if food else 'remove')
        return SelectedAdjustment(scope, 'meal' if food else item['kind'])
    remove = _REMOVE.fullmatch(text)
    if remove is not None:
        item = _named_item(items, remove['name'])
        if item is not None:
            return SelectedAdjustment(RichAdjustment(TripHead.from_trip(trip), item['id'], 'remove'), item['kind'])
        return None
    swap = match_edit(text)
    if swap is None:
        return None
    replacements = []
    for target, raw in _edit_parts(swap):
        if _literal_name(raw) is None and _qualified_name(raw):
            continue
        item = _named_item(items, target)
        label = _replacement_label(raw, national_names=True)
        if item is not None and label is not None and label.casefold() != item['text'].casefold():
            replacements.append((item, label))
    if len(replacements) == 1:
        (item, label), = replacements
        return SelectedAdjustment(RichAdjustment(TripHead.from_trip(trip), item['id'], 'replace'), item['kind'], label)
    return None


def adjustment_document(trip, selection, *, replacement):
    from .lio_pipeline_document import unconfirmed_legs,unconfirmed_place
    document = json.loads(trip.content)
    selected_id = selection.scope.item_id
    if selection.scope.operation == 'remove':
        document['items'] = [item for item in document['items'] if item['id'] != selected_id]
    else:
        item, = (row for row in document['items'] if row['id'] == selected_id)
        item.update(text=replacement, kind=selection.kind, place=unconfirmed_place((replacement, replacement)),
                    note=None, tip=None, reason_refs=[])
    def pair(leg):
        return leg['day_index'], leg['from_item_id'], leg['to_item_id']
    existing = {pair(leg): leg for leg in document['legs'] if selected_id not in pair(leg)[1:]}
    document['legs'] = [existing.get(pair(leg), leg) for leg in unconfirmed_legs(document)]
    return document
