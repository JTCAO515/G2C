"""The fixed JT-approved G2C invite cohort for internal plug-ins."""
import json

from .demo_login import invitation_subject


def generate_plugin_subjects():
    return sorted(invitation_subject(f'G2C@{number:02d}') for number in range(1, 100))


def configured_plugin_subjects(raw):
    subjects = json.loads(raw)
    expected = frozenset(generate_plugin_subjects())
    if (type(subjects) is not list or len(subjects) != len(expected)
            or any(type(subject) is not str for subject in subjects)
            or frozenset(subjects) != expected):
        raise ValueError('exact_internal_plugin_roster_required')
    return expected


if __name__ == '__main__':
    print(json.dumps(generate_plugin_subjects(), separators=(',', ':')))
