"""Run the fixed five-level synthetic drill batch."""

import asyncio
import json
from dataclasses import asdict
from typing import get_args

from jt.common import Severity

from .runner import DRILL_SEED, run_drills


def main() -> int:
    results = asyncio.run(run_drills())
    observed = {result.severity for result in results}
    levels = get_args(Severity)
    missing = [level for level in levels if level not in observed]
    passed = len(results) == len(levels) and not missing and all(result.status == "PASS" for result in results)
    print(json.dumps({
        "seed": DRILL_SEED,
        "status": "PASS" if passed else "FAIL",
        "missing_levels": missing,
        "cases": [asdict(result) for result in results],
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
