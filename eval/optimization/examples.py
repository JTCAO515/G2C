"""Produce annotated synthetic observations for the scoring controls."""
import argparse
import json
from pathlib import Path

from evaluation.cj028.evaluate import read_json
from .score import DATASET_VERSION, LANGUAGES, SPLITS, VERSION, dataset


def example_batch(split, control):
    examples = read_json(Path(__file__).with_name('examples.v1.json').read_bytes())
    document, digest = dataset()
    records = []
    for task in document['tasks']:
        if task['split'] != split:
            continue
        case_id = task['id']
        example = examples['tasks'][case_id][control]
        for language in LANGUAGES:
            attempt_id = f'fixture/{case_id}/{language}/{control}'
            records.append(dict(
                task_id=case_id, language=language, attempt_id=attempt_id,
                state=dict(attempt_id=attempt_id, ref=attempt_id + '/state',
                           values=examples['common_state'] | example['state']),
                reply=dict(attempt_id=attempt_id, ref=attempt_id + '/reply',
                           values=example['reply']),
            ))
    return dict(version=VERSION, dataset_version=DATASET_VERSION, dataset_sha256=digest,
                observations=records, run=dict(
        candidate_id=f'control-{control}', adapter_version='synthetic-fixture.1',
        model_version='none', prompt_version='none', tools_version='none',
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=SPLITS, default='development')
    parser.add_argument('--control', choices=('good', 'bad'), required=True)
    args = parser.parse_args()
    print(json.dumps(example_batch(args.split, args.control), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
