"""Explicit selection-source opt-in; old provider and publisher behavior stays.

The trusted host reads one deterministic result under the original holder and
formats it. It must not run a second matching rule or pass a model failure flag.
This component neither calls providers nor selects fuzzy/first-result matches.
"""
import json

from cj_agent.draft import DraftRejected
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.place_selection import VERSION, SOURCE, PLAN_SOURCE, selections
from .rich_provider_source import RichProviderContextSource
from .lio_rich import LioRichPublisher
from .rich_adjustment import RichAdjustment, check_document


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

    def __init__(self, original, confirmation, source, check_lio_original, code_checks, *, adjustment_authority=None):
        if type(source) is not RichPlaceSelectionContextSource:
            raise ValueError('explicit issued selection source required')
        super().__init__(original, confirmation, source, check_lio_original, code_checks)

        self.adjustment_authority = adjustment_authority

    def _require_adjustment(self, binding, original, adjustment):
        # The configured host must reread its authorization for this original,
        # exact Trip head, target and operation under the current MESSAGE hold.
        if (type(adjustment) is not RichAdjustment or self.adjustment_authority is None
                or self.adjustment_authority(binding, original, adjustment) is not True):
            raise DraftRejected('original scoped adjustment authority required')
        self.require_lio(binding, original, adjustment.head)

    def conditional_adjustment_source(self, binding, original, capture, checks, document, adjustment):
        """Issue scoped assembly inputs in the same active Source4 holder."""
        self.source.check(binding, capture)
        self._require_adjustment(binding, original, adjustment)
        check_document(self.source.contexts[binding], capture, adjustment, document)
        return self._conditional_source(binding, capture, checks, document, adjusted_item=adjustment.item_id)

    def publish_adjustment_for_message(self, binding, original, current, assembly, capture, *,
                                       adjustment, checks, before_publish):
        """Append one scoped Source4 revision and return the original rich receipt."""
        if type(adjustment) is not RichAdjustment:
            raise DraftRejected('typed original scoped adjustment required')
        return self._publish_assembly(binding, original, current, assembly, capture,
                                      checks=checks, proposed_subjects={}, before_publish=before_publish,
                                      adjustment=adjustment)
