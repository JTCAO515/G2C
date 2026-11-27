"""Score place candidates so the reviewer sees the likeliest keepers first (#1986, F-4).

The score only orders the review table; it never admits anything. A person decides every entry.
Parts (each 0..max), summed and rescaled to 0..100 over the parts that apply:

* foreigner   40  English signage / English service / foreign cards (10 each when true), +10 when the
                  stated signals carry evidence URLs
* confidence  20  the drafter's own confidence (high 20, medium 12, low 4)
* sources     10  official sources listed (5 each, two count)
* complete    10  how much of the practical information (hours, ticket, metro, addresses) is filled
* amap        20  how well the Amap POI matches the name (exact 20, close 12, address-only 6, weak 4)
* external    20  ONLY with `use_external=True`: a city rank (<=5: 20, <=10: 16, <=20: 12, <=40: 8, else 4)
                  or a 0..5 rating (value/5*20), whichever is higher

External signals (Tripadvisor and the like) are off by default: whether their use for an internal
decision is allowed is the coordinator's call after Codex's terms research (`codex-inbox/C3/terms.md`).
"""

MAX = {'foreigner': 40, 'confidence': 20, 'sources': 10, 'complete': 10, 'amap': 20, 'external': 20}
AMAP_POINTS = {'exact': 20, 'close': 12, 'address-only': 6, 'weak': 4, 'none': 0}
CONFIDENCE_POINTS = {'high': 20, 'medium': 12, 'low': 4}
COMPLETE_FIELDS = {
    'attraction': ('hours_zh', 'ticket', 'nearest_metro', 'address_zh', 'address_en', 'visit_minutes', 'official_url'),
    'food': ('hours_zh', 'nearest_metro', 'address_zh', 'address_en', 'cuisine_zh', 'price_per_person_cny', 'official_url'),
    'shopping': ('hours_zh', 'nearest_metro', 'address_zh', 'address_en', 'official_url'),
    'hotel': ('address_zh', 'address_en', 'star', 'price_band', 'foreign_service', 'nearest_metro', 'official_url'),
    'hub': ('to_city_zh', 'to_city_en', 'terminals', 'foreigner_tips_zh', 'official_url'),
}


def _foreigner(entry):
    signals = entry.get('foreigner_signals') or {}
    points = sum(10 for key in ('english_signage', 'english_service', 'foreign_cards') if signals.get(key) is True)
    return points + (10 if points and signals.get('evidence') else 0)


def _complete(entry):
    fields = COMPLETE_FIELDS[entry['category']]
    return round(MAX['complete'] * sum(1 for key in fields if entry.get(key) not in (None, [], '')) / len(fields))


def _external(signals):
    best = 0
    for item in signals or []:
        value = item.get('value')
        if item.get('metric') == 'rank_in_city' and value >= 1:
            best = max(best, 20 if value <= 5 else 16 if value <= 10 else 12 if value <= 20 else 8 if value <= 40 else 4)
        elif item.get('metric') in ('rating', 'rating_5') and 0 <= value <= 5:
            best = max(best, round(value / 5 * 20))
    return best


def score(entry, amap_status, external_signals=None, use_external=False):
    """{'total': 0..100, 'parts': {...}, 'external_used': bool} for one normalised draft entry."""
    parts = {
        'foreigner': _foreigner(entry),
        'confidence': CONFIDENCE_POINTS[entry['confidence']],
        'sources': 5 * min(len(entry['sources']), 2),
        'complete': _complete(entry),
        'amap': AMAP_POINTS.get(amap_status, 0),
    }
    possible = sum(MAX[k] for k in parts)
    if use_external:
        parts['external'] = _external(external_signals)
        possible += MAX['external']
    return {'total': round(100 * sum(parts.values()) / possible), 'parts': parts, 'external_used': use_external}


def order_key(candidate):
    """Review order: main before backup, then higher score, then id (stable)."""
    return (candidate['draft']['tier'] != 'main', -candidate['score']['total'], candidate['id'])
