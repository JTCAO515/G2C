"""Score a development or validation batch without calling an agent."""
import argparse
import json
from pathlib import Path

from evaluation.cj028.evaluate import read_json, require
from .score import SPLITS, VERSION as V1, score as score_v1
from .score_v2 import VERSION as V2, score as score_v2

SCORERS = {V1: score_v1, V2: score_v2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=SPLITS, default='development')
    parser.add_argument('--observations', type=Path, required=True)
    args = parser.parse_args()
    try:
        batch = read_json(args.observations.read_bytes())
        require(type(batch) is dict and type(batch.get('version')) is str and batch['version'] in SCORERS,
                'unsupported scoring version')
        result = SCORERS[batch['version']](args.split, batch)
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
