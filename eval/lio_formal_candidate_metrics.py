"""Typed candidate measurements for #541; no AUTH, source or task certificate.

The qualified host must supply the actual candidate and its native canonical
digest. Hash equality proves content integrity, not custody or publication.
Old judge/scenarios stay unchanged. Prices and original FEAS evidence are not
inferred from prose, proposed route labels or a model's success assertion.
"""
from collections import Counter
from datetime import date
from hashlib import sha256
import json
import re

from cj_strict_json import reject_duplicates
from cj_trip.domain import packed
from cj_trip.structured import validate_document as validate_v1
from cj_trip.structured_v2 import validate_document as validate_v2
from cj_trip.structured_v3 import validate_document as validate_v3
from cj_trip.structured_v4 import validate_document as validate_v4


VERSION = 'LIO-formal-candidate-metrics.1'
VALIDATORS = {'structured.1': validate_v1, 'structured.2': validate_v2,
              'structured.3': validate_v3, 'structured.4': validate_v4}
FIELDS = ('candidate_day_count', 'max_candidate_daily_items',
          'verified_daily_cost', 'known_transfer_feasible')


def _nonfinite(_):
    raise ValueError('nonfinite candidate JSON')


def candidate_metrics(raw, *, expected_content_sha256):
    """Measure declared ordinal days and proposed sight items, never text labels.

    The frozen slow-pace input says sights, not meals/hotels/all activity cards.
    kind=sight is a proposed classification; semantic correctness still needs
    the independent grounded review. A cross-day sight has no defined daily
    count here and remains unavailable. No legacy text/day inference occurs.
    """
    observations = dict.fromkeys(FIELDS)
    reasons = {key: 'original_candidate_unavailable' for key in FIELDS}
    result = dict(version=VERSION, content_version=None, raw_sha256=None,
                  canonical_content_sha256=None, observations=observations,
                  unavailable_reasons=reasons, task_outcome='UNKNOWN',
                  authority='CONTENT_MEASUREMENTS_ONLY_NOT_AUTH_SOURCE_OR_STATE_EVIDENCE')
    if raw is None and expected_content_sha256 is None:
        return result
    if (type(raw) is not bytes or not 0 < len(raw) <= 1_000_000
            or type(expected_content_sha256) is not str
            or re.fullmatch(r'[0-9a-f]{64}', expected_content_sha256) is None):
        raise ValueError('bounded original candidate bytes and native canonical digest required')
    document = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate candidate field'),
                          parse_constant=_nonfinite)
    if type(document) is not dict or type(document.get('content_version')) is not str:
        raise ValueError('explicit structured candidate version required')
    version = document['content_version']
    if version not in VALIDATORS:
        raise ValueError('unsupported candidate version; no legacy fallback')
    VALIDATORS[version](document)
    canonical = sha256(packed(document)).hexdigest()
    if canonical != expected_content_sha256:
        raise ValueError('candidate differs from the native canonical content digest')
    result.update(content_version=version, raw_sha256=sha256(raw).hexdigest(),
                  canonical_content_sha256=canonical)
    reasons.update(candidate_day_count='explicit_ordinal_days_unavailable',
                   max_candidate_daily_items='explicit_sight_kinds_unavailable',
                   verified_daily_cost='complete_native_price_coverage_unavailable',
                   known_transfer_feasible='protected_original_transfer_feasibility_unavailable')
    if version in ('structured.3', 'structured.4'):
        observations['candidate_day_count'] = len(document['days'])
        reasons.pop('candidate_day_count')
    else:
        events = [item['schedule'][edge] for item in document['items'] for edge in ('start', 'end')]
        if all(event['date']['state'] == 'known' for event in events):
            zones = [event['timezone'] for event in events]
            if all(zone['state'] == 'known' and zone['value'] == zones[0]['value'] for zone in zones):
                days = [date.fromisoformat(event['date']['value']) for event in events]
                observations['candidate_day_count'] = (max(days) - min(days)).days + 1
                reasons.pop('candidate_day_count')
            else:
                reasons['candidate_day_count'] = 'common_explicit_calendar_timezone_unavailable'
        else:
            reasons['candidate_day_count'] = 'complete_explicit_schedule_dates_unavailable'
    if version == 'structured.4':
        sights = [item for item in document['items'] if item['kind'] == 'sight']
        if any(item['schedule']['start']['day_index'] != item['schedule']['end']['day_index']
               for item in sights):
            reasons['max_candidate_daily_items'] = 'cross_day_sight_count_unavailable'
        else:
            counts = Counter(item['schedule']['start']['day_index'] for item in sights)
            observations['max_candidate_daily_items'] = max(counts.values(), default=0)
            reasons.pop('max_candidate_daily_items')
    return result
