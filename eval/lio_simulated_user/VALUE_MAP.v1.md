# #936 public representation conversion, part 1

`profile-value-map.1.json` publishes **LIO-profile-value-map.1**. Its exact byte
SHA is returned with every **LIO-normalized-profile.1** result. Public product
factor labels, canonical aliases and the merged C design are the listed sources;
each has its repository path, commit and byte SHA. Hidden personas/answers are
not a source or a runtime dependency.

`value_map_v1.normalize_value(factor, value)` maps only complete listed forms,
using surrounding whitespace removal and Unicode casefold for lookup. The raw
JSON value is retained. It returns `NORMALIZED` or `UNAVAILABLE`, never a test
PASS. For example:

```python
normalize_value('city', '北京')['value']              # 'beijing'
normalize_value('party_type', 'family')['value']     # 'family_with_child'
normalize_value('lodging_tier', 'simple')['value']   # 'budget'
normalize_value('interests', ['美食', '历史', '美食'])['value']
# ['food', 'history', 'food']
```

The four city names are the currently listed public product forms, **not a
product allow-list**. Other cities remain evaluation conversion gaps until a
new catalog adds independently sourced equivalents. There is no fuzzy match,
substring city extraction or disambiguation from a persona. Specific sights are
not turned into a generic museum or a different sight.

Integer and boolean factors retain exact JSON types. Four array factors retain
every item, its order and duplicates; a scalar is not promoted to a list and an
unknown item does not disappear. Dietary restrictions are never collapsed to
one item. Null remains explicit null/UNAVAILABLE, distinct from an absent field,
an explicit empty array and an explicit `none` token. This first version does
not convert arrival/departure values: the actual precise day/time/transport
source interface is still outstanding, so even a supplied object is retained
as unavailable rather than given invented semantics.

`normalize_profile(profile, native_profile_complete=...)` accepts an explicit
decoded observation, **not a public display profile or a context.2 wire**:

```python
{
    'pace': {
        'value': '慢节奏', 'state': 'known',
        'sources': [{'kind': 'message', 'message_id': 'actual-original-mid',
                     'sequence': 1, 'quote': '慢节奏', 'offset': 0}]
    }
}
```

Each row retains the full raw fact, state, sources and any extra metadata.
`memory` is not upgraded to `from_memory`; `default`, `not_needed`, `inferred`
and `known` are not exchanged. Native completeness is echoed separately from
normalization coverage, with absent and unavailable factor lists. The converter
does not authenticate those inputs or manufacture a native observation ref.
Its output cannot be submitted as a legacy trace.1 profile or used to claim G3.

Remaining for the full integration: B's protected original snapshot reader and
actual selected exploration boundary; precise temporal sources; independently
sourced names outside this catalog; a new evaluation-input adapter with
question census and injected Memory evidence. Old core/trace.1, its strict
comparison and all thresholds stay unchanged. Do not run the real 60 trajectories
until the complete, scoreable observation and existing real-call gates are ready.

Tests are local representation controls. They are not real actor/DUT results,
new-system regression qualification, deployment evidence or costs. The existing
`scripts/test.py` simulated-user discovery includes the new tests; no shared
test entry, package manifest, backend or authorization file is changed. This
module currently runs from the evaluation checkout, not a worker-installed wheel.
