"""One registered planning understanding over genuine original MESSAGE clocks.

This returns validated data, not permission to save. The caller must still
register the original NEEDS, capture/hold the profile/calendar/provider sources
and use the sole publisher. City resolution and profile defaults are code-owned
inputs, never model evidence for an original traveler statement.
"""
from dataclasses import dataclass

from cj_message.lio_plan_input_schema import PLAN_UNDERSTANDING,PlanUnderstanding
from cj_feasibility.rich_edges import activity_windows

from .lio_pipeline_model import PLAN_UNDERSTANDING_SYSTEM
from .lio_plan_understanding import (original_plan_turns,parse_plan_understanding,compile_plan_fields,prepare_plan_fields,
    degraded_save_enabled,parse_plan_understanding_degraded)
from .lio_planning_grounding import PlanningTurn
from .local_lio_planning import PlanningDetails


@dataclass(frozen=True)
class PlanConstraints:
    """Checked original model data, with no city result or publication lease."""
    value:PlanUnderstanding
    turns:tuple[PlanningTurn,...]
    # W1-2 (#1722) degraded path only: fields left out as unconfirmed. Empty
    # whenever the strict parser accepted the understanding.
    unconfirmed:frozenset=frozenset()
    degraded:bool=False

    def project(self):
        """Complete source-covered fields without a city or source lease."""
        return prepare_plan_fields(self.value,self.turns,start_unconfirmed='start_date'in self.unconfirmed)

    def compile(self,*,day_count,city_reference,message_id,run_id):
        """Only after complete-graph preflight and genuine city resolution.

        Keep all destination/date/fixed-window checks in their original
        compiler. Extracted data never substitutes for a confirmed city result.
        """
        return compile_plan_fields(self.value,self.turns,day_count=day_count,city_reference=city_reference,
            message_id=message_id,run_id=run_id,start_unconfirmed='start_date'in self.unconfirmed)


def understand_constraints(host,worker,binding,view,*,locale):
    """One registered model call before any city/place supplier dispatch."""
    turns=original_plan_turns(host.database,worker,binding,view)
    raw=host._model(worker,binding,view,PLAN_UNDERSTANDING,PLAN_UNDERSTANDING_SYSTEM,
        dict(locale=locale,current_source_index=len(turns)-1,
             original_question_days=[turn.question_day.isoformat()for turn in turns]))
    if degraded_save_enabled():
        value,unconfirmed=parse_plan_understanding_degraded(raw,turns)
        return PlanConstraints(value,turns,unconfirmed,True)
    return PlanConstraints(parse_plan_understanding(raw,turns),turns)


def planning_details(projection,city_reference,references):
    """Bridge compiled, sourced fields to the existing registration input.

    This is data only. The actual register/current MESSAGE and subsequent
    calendar/source holders remain responsible for admission and publication.
    """
    return PlanningDetails(city_reference.name,projection.fields,None,references)


def planning_edges(projection,day_count):
    """Use checked options; no flight/train, clock or full-day request default."""
    def clock(event):
        value=projection.fields.get(event,{}).get('time',dict(state='missing'))
        if value['state']!='known':return None
        hours,minutes=map(int,value['value'].split(':'))
        return hours*3600+minutes*60
    mode=projection.edge_options['departure.mode'];full=projection.edge_options['first_day_full']
    return activity_windows(day_count,arrival_clock=clock('arrival'),departure_clock=clock('departure'),
        departure_mode=mode['value']if mode['state']=='known'else None,
        first_day_full=full['state']=='known'and full['value']is True)
