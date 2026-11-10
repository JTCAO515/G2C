"""Score a development or validation batch without calling an agent."""
import argparse
import json
from pathlib import Path

from evaluation.cj028.evaluate import read_json
from .score import SPLITS, score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=SPLITS, default='development')
    parser.add_argument('--observations', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = score(args.split, read_json(args.observations.read_bytes()))
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
