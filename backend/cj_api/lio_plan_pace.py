"""Compile accepted NEEDS pace facts into the explicit first-plan generation choice."""
from dataclasses import dataclass

from cj_draft.rich_schema import Pace


_PACES={
    'relaxed':Pace.RELAXED,'leisurely':Pace.RELAXED,'slow':Pace.RELAXED,
    '轻松':Pace.RELAXED,'悠闲':Pace.RELAXED,'休闲':Pace.RELAXED,
    'moderate':Pace.MODERATE,'balanced':Pace.MODERATE,'适中':Pace.MODERATE,'中等':Pace.MODERATE,
    'packed':Pace.PACKED,'dense':Pace.PACKED,'fast':Pace.PACKED,'紧凑':Pace.PACKED,'密集':Pace.PACKED,
}


@dataclass(frozen=True)
class PlanPace:
    value:Pace | None
    defaulted:bool


def from_needs_fields(fields):
    """The caller supplies source-checked NEEDS fields, never a client profile flag.

    This normalizes the accepted style observation; it does not collect Memory,
    infer a new fact, rewrite NEEDS, or grant publication. Unresolved style uses
    #922's disclosed moderate default. A known style outside the three supported
    canonical choices keeps the legacy profile; it is not overwritten by a
    default. WP3's typed profile will replace this compatibility selection.
    """
    observation=fields.get('pace')
    if observation is not None and observation['state']=='known':
        selected=_PACES.get(observation['value'].strip().casefold())
        return PlanPace(selected,False)
    return PlanPace(Pace.MODERATE,True)


def saved_summary(locale,days,pace,*,dated,retained=False):
    """Called only after an actual save receipt, with the captured duration."""
    if retained:
        return ('新建议已保存为行程的新版本，原有安排已保留。还可以继续调整地点或时段。想先调整哪一天？'
                if locale=='zh' else
                'The new suggestions are saved in a new itinerary version, keeping the original arrangements. You can adjust stops or times. Which day would you like to change?')
    if locale=='zh':
        opening=f'行程已保存，共{days}天。'
        style=('节奏未定，先按适中安排。'if pace.defaulted else
               '还可以继续调整地点或时段。'if pace.value is None else
               '已按'+{Pace.RELAXED:'轻松',Pace.MODERATE:'适中',Pace.PACKED:'紧凑'}[pace.value]+'节奏安排。')
        ending=('想先调整哪一天？'if dated else'出发日期定了告诉我，我把每天对上日期；想先调整哪一天？')
    else:
        opening=f'Your {days}-day itinerary is saved. '
        style=('I used a moderate pace because the pace is not settled. 'if pace.defaulted else
               'You can adjust the stops or timing. 'if pace.value is None else
               'It follows a '+{Pace.RELAXED:'relaxed',Pace.MODERATE:'moderate',Pace.PACKED:'packed'}[pace.value]+' pace. ')
        ending=('Which day would you like to adjust?'if dated else
                'Tell me when the start date is set and I will add the dates; which day would you like to adjust?')
    return opening+style+ending
