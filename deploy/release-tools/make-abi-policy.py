"""Generate the next HK app-release ABI policy from the installed one (S line, 2026-11-27).

    cd <repo checkout>; python3 -I -B make-abi-policy.py <live source> <next source>

Reads the installed policy copy PREVIOUS (pinned by sha256), checks that its
accepted_source_hash_sets[1] is exactly the live source's set (the last rotation
installed the live release as "next"), and writes policy-<live8>-<next8>-<UTC day>.json
next to this script with:
- required_source_hashes = accepted_source_hash_sets[0] = live source set,
- accepted_source_hash_sets[1] = next source set (same file list). The HK host
  rejects every image when both sets are equal, so equal sets are refused here,
- every other field byte-for-byte unchanged.
Hashes come from `git show <sha>:<path>` of the checked-out repository. Only
prints the file name, its sha256 and which files differ between the two sets.
Writes nothing on the host; installing is a separate reviewed step.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser().resolve()
PREVIOUS = STATE / 'policy-47c89be1-e0bea843-20261127.json'
PREVIOUS_SHA = '94f78d0ae64281aeb0018de035debeb9bef5c5e426ae83f7e23af252fdceaeed'


def source_set(source, names):
    return {name: hashlib.sha256(subprocess.check_output(['git', 'show', source + ':' + name])).hexdigest()
            for name in names}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def main():
    live, following = sys.argv[1:]
    if not all(re.fullmatch('[0-9a-f]{40}', value) for value in (live, following)) or live == following:
        raise SystemExit('two distinct full source SHAs required')
    subprocess.run(['git', 'merge-base', '--is-ancestor', live, following], check=True)
    raw = PREVIOUS.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PREVIOUS_SHA:
        raise SystemExit('installed policy copy changed')
    policy = json.loads(raw)
    if encode(policy) != raw:
        raise SystemExit('unexpected policy encoding')
    names = sorted(policy['required_source_hashes'])
    if (len(policy['accepted_source_hash_sets']) != 2
            or any(sorted(item) != names for item in policy['accepted_source_hash_sets'])):
        raise SystemExit('unexpected policy shape')
    live_set = source_set(live, names)
    if policy['accepted_source_hash_sets'][1] != live_set:
        raise SystemExit('live source is not the installed policy\'s next set')
    next_set = source_set(following, names)
    if next_set == live_set:
        raise SystemExit('next source has the same ABI set; no rotation needed')
    rotated = dict(policy, required_source_hashes=live_set, accepted_source_hash_sets=[live_set, next_set])
    out = STATE / ('policy-%s-%s-%s.json' % (live[:8], following[:8], datetime.now(timezone.utc).strftime('%Y%m%d')))
    data = encode(rotated)
    with open(out, 'xb') as output:
        output.write(data)
    print(json.dumps(dict(file=out.name, sha256=hashlib.sha256(data).hexdigest(),
                          differs=[name for name in names if live_set[name] != next_set[name]])))


if __name__ == '__main__':
    main()
