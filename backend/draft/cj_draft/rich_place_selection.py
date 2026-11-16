"""Explicit selection-source opt-in; old provider and publisher behavior stays.

The trusted host reads one deterministic result under the original holder and
formats it. It must not run a second matching rule or pass a model failure flag.
This component neither calls providers nor selects fuzzy/first-result matches.
"""
import json

from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.place_selection import VERSION, SOURCE, PLAN_SOURCE, selections
from .rich_provider_source import RichProviderContextSource
from .lio_rich import LioRichPublisher


class RichPlaceSelectionContextSource(RichProviderContextSource):
    plan_source_version = PLAN_SOURCE

    def _provider_value(self, calendar, providers):
        value = super()._provider_value(calendar, providers)
        value.update(version=SOURCE, place_selection_version=VERSION,
                     place_selections=selections(providers.outcomes, value['provider_records']))
        return value

    def selection_results(self, binding, capture):
        self.check(binding, capture)
        return json.loads(capture.raw)['place_selections']

    def place_selection(self, binding, capture, target, *, keyword):
        for result in self.selection_results(binding, capture):
            if result['target'] == target:
                if result['query_keyword'] != keyword:
                    raise LeaseUnavailable('selection keyword differs from its original target query')
                return result
        raise LeaseUnavailable('target has no original code-owned POI selection')

    def unavailable_targets(self, binding, capture):
        # Route targets cannot masquerade as a failed item lookup. Multiple
        # exact POIs stay ambiguous and cannot authorize fallback either.
        return frozenset(result['target'] for result in self.selection_results(binding, capture)
                         if result['status'] == 'unavailable')


class LioSelectedRichPublisher(LioRichPublisher):
    publication_policy = 'LIO-rich-selection-pipeline.1'
    plan_source_version = PLAN_SOURCE

    def __init__(self, original, confirmation, source, check_lio_original, code_checks):
        if type(source) is not RichPlaceSelectionContextSource:
            raise ValueError('explicit issued selection source required')
        super().__init__(original, confirmation, source, check_lio_original, code_checks)
