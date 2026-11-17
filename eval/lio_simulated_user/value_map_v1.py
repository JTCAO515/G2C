"""Public representation conversion; never accepted-profile or G3 evidence.

This module has no persona, provider, reader, scorer or backend dependency.
Only whole, explicitly listed forms are equivalent. Unknown forms remain gaps.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from cj_strict_json import reject_duplicates


CATALOG = Path(__file__).with_name('profile-value-map.1.json')
VERSION = 'LIO-profile-value-map.1'
PROFILE_VERSION = 'LIO-normalized-profile.1'
FACTORS = ('city', 'duration_days', 'season', 'first_visit', 'party_type',
           'interests', 'pace', 'lodging_tier', 'dietary', 'must_see', 'avoid',
           'mobility', 'arrival', 'departure')


def _nonfinite(_):
    raise ValueError('nonfinite public catalog')


def _load_catalog():
    raw = CATALOG.read_bytes()
    catalog = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate catalog field'),
                         parse_constant=_nonfinite)
    alias_factors = set(FACTORS) - {'duration_days', 'first_visit', 'arrival', 'departure'}
    if (type(catalog) is not dict or catalog.get('version') != VERSION
            or catalog.get('factors') != list(FACTORS)
            or catalog.get('array_factors') != ['interests', 'dietary', 'must_see', 'avoid']
            or type(catalog.get('aliases')) is not dict
            or set(catalog['aliases']) != alias_factors):
        raise ValueError('exact public catalog shape required')
    aliases = {}
    for factor, entries in catalog['aliases'].items():
        if type(entries) is not dict or not entries:
            raise ValueError('explicit public aliases required')
        words = {}
        for canonical, forms in entries.items():
            if (type(canonical) is not str or not canonical.strip()
                    or type(forms) is not list
                    or any(type(form) is not str or not form.strip() for form in forms)):
                raise ValueError('nonempty whole public value forms required')
            for form in (canonical, *forms):
                key = form.strip().casefold()
                if key in words and words[key] != canonical:
                    raise ValueError('ambiguous public value alias')
                words[key] = canonical
        aliases[factor] = words
    return catalog, aliases, sha256(raw).hexdigest()


_CATALOG, _ALIASES, CATALOG_SHA256 = _load_catalog()


def _convert(factor, value):
    if value is None:
        return None, 'explicit_null'
    if factor == 'duration_days':
        return (value, None) if type(value) is int else (None, 'integer_required')
    if factor == 'first_visit':
        return (value, None) if type(value) is bool else (None, 'boolean_required')
    if factor in ('arrival', 'departure'):
        return None, 'precise_temporal_source_required'
    words = _ALIASES[factor]
    if factor in _CATALOG['array_factors']:
        if type(value) is not list:
            return None, 'array_required'
        converted = []
        for item in value:
            if type(item) is not str or item.strip().casefold() not in words:
                return None, 'unlisted_array_item'
            converted.append(words[item.strip().casefold()])
        return converted, None
    if type(value) is not str:
        return None, 'string_required'
    canonical = words.get(value.strip().casefold())
    return (canonical, None) if canonical is not None else (None, 'unlisted_value')


def normalize_value(factor, value):
    """Convert one external JSON value, preserving raw nulls and unknowns.

    NORMALIZED describes representation only. It does not mean PASS, a known
    fact, authenticated custody, complete observation or complete exploration.
    """
    if type(factor) is not str or factor not in FACTORS:
        raise ValueError('known profile factor required')
    # JSON is the observation boundary, not an internal domain-object probe.
    json.dumps(value, allow_nan=False)
    return _result(factor, value)


def _result(factor, value):
    canonical, reason = _convert(factor, value)
    return dict(raw_value=deepcopy(value), status='NORMALIZED' if reason is None else 'UNAVAILABLE',
                value=canonical, reason=reason)


def normalize_profile(profile, *, native_profile_complete):
    """Convert a decoded observation without asserting its origin or score.

    The host still owes the actual protected snapshot. This is not a context.2
    decoder: the explicit input is factor -> {value, state, sources, ...}.
    Sources and native state are retained, including memory versus from_memory.
    No partial result is emitted as a legacy trace.1 profile.
    """
    if (type(profile) is not dict or type(native_profile_complete) is not bool
            or any(type(key) is not str or key not in FACTORS for key in profile)):
        raise ValueError('explicit native profile observation required')
    rows = {}
    for factor, fact in profile.items():
        if (type(fact) is not dict or not {'value', 'state', 'sources'} <= fact.keys()
                or fact['state'] not in ('known', 'not_needed', 'inferred', 'default', 'memory', 'from_memory')
                or type(fact['sources']) is not list):
            raise ValueError('raw state, value and sources required')
        json.dumps(fact, allow_nan=False)
        converted = _result(factor, fact['value'])
        rows[factor] = dict(raw_fact=deepcopy(fact), **converted)
    missing = [key for key in FACTORS if key not in rows]
    unavailable = [key for key, row in rows.items() if row['status'] == 'UNAVAILABLE']
    return dict(version=PROFILE_VERSION, catalog_version=VERSION, catalog_sha256=CATALOG_SHA256,
                native_profile_complete=native_profile_complete,
                normalization_complete=not missing and not unavailable,
                missing_factors=missing, unavailable_factors=unavailable, factors=rows)
