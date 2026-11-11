"""Annotated v2 controls, reusing the five unchanged v1 examples."""
import argparse
import json
from pathlib import Path

from evaluation.cj028.evaluate import read_json
from . import examples as legacy_examples
from .score import SPLITS
from .score_v2 import MUTATION_TASKS, REVISED_TASKS, DATASET_VERSION, VERSION, dataset


def example_batch(split, control):
    batch = legacy_examples.example_batch(split, control)
    _, digest = dataset()
    changes = read_json(Path(__file__).with_name('examples.v2.json').read_bytes())['tasks']
    batch.update(version=VERSION, dataset_version=DATASET_VERSION, dataset_sha256=digest)
    batch['run'].update(candidate_id='lio-v2-control-' + control, adapter_version='synthetic-fixture.2')
    for record in batch['observations']:
        task_id = record['task_id']
        attempt = f'fixture-v2/{task_id}/{record["language"]}/{control}'
        record['attempt_id'] = attempt
        if task_id in REVISED_TASKS:
            example = changes[task_id][control]
            state = record['state']['values'].copy()
            if task_id in MUTATION_TASKS:
                state = {name: state[name] for name in (
                    'runtime_role', 'foreign_message_rows', 'foreign_mutations', 'memory_item_count')}
            state.update(example['state'])
            if task_id == 'dev-local-edit':
                label = '天坛' if record['language'] == 'zh' else 'Temple of Heaven'
                state['applied_patch'] = {'day2.afternoon' if control == 'good' else 'day1.morning': label}
            record['state']['values'] = state
            record['reply']['values'] = example['reply']
        for section in ('state', 'reply'):
            record[section].update(attempt_id=attempt, ref=f'{attempt}/{section}')
    return batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=SPLITS, default='development')
    parser.add_argument('--control', choices=('good', 'bad'), required=True)
    args = parser.parse_args()
    print(json.dumps(example_batch(args.split, args.control), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
