"""The fixed JT-approved G2C invite cohort for internal plug-ins."""
from hashlib import sha256
import json

from cj_strict_json import compact

from .demo_login import invitation_subject

# JT already belongs to the 99-account cohort. These are the original C.zh and C.en bindings.
EXTRA_TRANSLATION_SUBJECTS_SHA256 = '842aafcdb577ecfa4f7b70cb5750a62324efbb8e7e835797d1489e12599ba838'


def generate_plugin_subjects():
    return sorted(invitation_subject(f'G2C@{number:02d}') for number in range(1, 100))


def configured_plugin_subjects(raw):
    try:
        subjects = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError('exact_internal_plugin_roster_required') from None
    expected = frozenset(generate_plugin_subjects())
    if (type(subjects) is not list or len(subjects) != len(expected)
            or any(type(subject) is not str for subject in subjects)
            or frozenset(subjects) != expected):
        raise ValueError('exact_internal_plugin_roster_required')
    return expected


def configured_translation_subjects(raw):
    try:
        subjects = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError('exact_internal_translation_roster_required') from None
    expected = frozenset(generate_plugin_subjects())
    if type(subjects) is not list or any(type(subject) is not str for subject in subjects):
        raise ValueError('exact_internal_translation_roster_required')
    supplied = frozenset(subjects)
    extra = supplied - expected
    if (len(subjects) != len(supplied) or not expected <= supplied or
            extra and (len(extra) != 2 or
                       sha256(compact(sorted(extra))).hexdigest() != EXTRA_TRANSLATION_SUBJECTS_SHA256)):
        raise ValueError('exact_internal_translation_roster_required')
    return supplied


if __name__ == '__main__':
    print(compact(generate_plugin_subjects()).decode('utf-8'))
