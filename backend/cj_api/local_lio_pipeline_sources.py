"""Native4 plan source composition over the existing current worker boundaries.

No provider dispatch, model result, new authority or Trip publication occurs
here. The caller must preflight the complete graph, retain original attempts
and use issued date checks and the sole selected publisher for final commit.
"""
from dataclasses import dataclass
from cj_draft.rich_place_selection import RichPlaceSelectionContextSource
from cj_message.lio_plan_needs import original_needs
from cj_trip.postgres import Repository as TripRepository
from .local_lio_planning import register,PlanningDetails
from .local_lio_rich_source import RichProfileSource
from .local_lio_rich_calendar_source import RichCalendarSource
from .local_lio_provider_sources import RegisteredProviderSources
from .local_lio_pipeline_places import lookup_selected_places


@dataclass
class PipelineSources:
    worker:object
    binding:object
    profiles:RichProfileSource
    providers:RegisteredProviderSources
    source:RichPlaceSelectionContextSource
    repository:TripRepository
    calendar_capture:object

    def seal(self):
        """Outside worker._step, after all original attempts settle."""
        return self.source.seal_providers(self.binding,self.calendar_capture)

    def places(self,skeleton,capture):
        """Format under actual publication holders; no external IO here."""
        def read():
            with self.source.hold_for_publication(self.binding):
                return lookup_selected_places(skeleton,self.source,self.binding,capture)
        _,value=self.worker._step(self.binding,read)
        return value


def capture_pipeline_sources(host,worker,binding,view,fields,city_reference,*,day_count,start_date):
    """Record literal plan-now and original NEEDS once, then capture sources.

    Profile/M/Memory holders decide admission. Old previews and .3 originals
    are not relabelled. The calendar reads originals' persistent own clocks;
    this function supplies no substitute clock and performs no supplier call.
    """
    profiles=RichProfileSource(host.database)
    state=profiles.record_plan_now(worker,binding,worker.runs.snapshot(binding))
    register(worker,binding,state,PlanningDetails(city_reference.name,fields,None,view.references))
    original=host.legacy.calendar.context_publisher
    repository=TripRepository(original.repository.connect,original.repository.scope,
        host.legacy.calendar.confirmation,structured=True,calendar=True,rich=True)
    calendar=RichCalendarSource(host.database,worker.message_context,day_count=day_count,
        start_date=start_date,references=view.references)
    providers=RegisteredProviderSources(worker,binding)
    source=RichPlaceSelectionContextSource(original.source,original_needs,calendar,repository,
        profile_reader=profiles,worker=worker,expected_profile=view.profile,provider_reader=providers)
    _,captured=worker._step(binding,lambda:source.capture(binding))
    return PipelineSources(worker,binding,profiles,providers,source,repository,captured)
