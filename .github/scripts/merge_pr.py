"""The one way every line merges a PR into main: check the merge conditions, then merge locked.

    python3 .github/scripts/merge_pr.py <PR> --head <SHA> --freeze-note <main-freeze.md> [--dry-run]

Run it from a checkout of this repository with `origin` pointing at GitHub, with an authenticated
`gh`. `--freeze-note` (or G2C_FREEZE_NOTE) names the coordination thread's main-freeze.md; it lives
outside the repository, so the path is never written here. In order, it stops unless:

1. main is open: the note's `**当前：...**` line says 未冻结. While it says 暂停合并 (main is broken),
   only a PR that repairs main may merge, declared with --fix-main; any other or missing state stops;
2. the PR is open, not a draft, targets main and its head is exactly --head;
3. the newest member `Review: APPROVE|REQUEST CHANGES <head>` comment approves that head;
4. the newest ci.yml pull_request run of the head succeeded and every check on the head passed
   (success, skipped or neutral) with none still running;
5. no commit that reached main after that ci run started touches a file (or shared area, see
   pr_overlap.py) this PR touches. Each PR's CI tested it against main as it was then; a later
   main commit to the same files is what broke main in f687a32f (#1604 and #1616). When this stops
   the merge, bring the branch up to date with main, wait for its new CI and review, and run again.

It then reads the freeze note again, merges with `gh pr merge --merge --match-head-commit` and
reads the PR back. Exit codes: 0 merged (or would merge with --dry-run), 2 a condition is not met,
3 main is frozen, 1 the check could not finish or the merge result could not be read back (GitHub
or git unavailable; look at the PR before running again), 64 bad arguments.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr_overlap import overlap, pr_paths  # noqa: E402

REPO = 'JTCAO515/G2C'
MEMBERS = {'OWNER', 'MEMBER', 'COLLABORATOR'}
PASSED = {'success', 'skipped', 'neutral'}
MARGIN = datetime.timedelta(minutes=2)  # count main commits from a little before the ci run began


class Blocked(Exception):
    code = 2


class Frozen(Blocked):
    code = 3


def freeze_state(text):
    """The state on the note's `**当前：<state>**` line, or None when there is none."""
    match = re.search(r'^\*\*当前：(.+?)\*\*', text, re.M)
    return match.group(1).strip() if match else None


def check_freeze(path, fix_main=False):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError as error:
        raise Frozen(f'cannot read the freeze note {path}: {error}') from error
    state = freeze_state(text)
    if state is not None and (state.startswith('未冻结') or (fix_main and state.startswith('暂停合并'))):
        return state
    raise Frozen(f'main is not open for merging: {state or "no 当前 line in the freeze note"}')


def check_pr(pr, head):
    if pr['state'] != 'open' or pr.get('merged'):
        raise Blocked(f"PR is {pr['state']}, not open")
    if pr.get('draft'):
        raise Blocked('PR is a draft')
    if pr['base']['ref'] != 'main':
        raise Blocked(f"PR targets {pr['base']['ref']}, not main; merge the PR below it first")
    if pr['head']['sha'] != head:
        raise Blocked(f"PR head is {pr['head']['sha']}, not {head}")


def check_review(comments, head):
    decision = re.compile(r'Review: (APPROVE|REQUEST CHANGES) ' + head)
    latest = None
    for comment in comments:
        if (comment['author_association'] in MEMBERS
                and decision.fullmatch(comment['body'].partition('\n')[0])
                and (latest is None or comment['id'] > latest['id'])):
            latest = comment
    if latest is None:
        raise Blocked(f'no `Review: APPROVE {head}` comment on the PR')
    if not latest['body'].startswith(f'Review: APPROVE {head}'):
        raise Blocked(f'the newest review of {head} requests changes')


def check_ci(runs, checks):
    """The newest ci.yml pull_request run of the head, once every check on the head has passed."""
    if not runs:
        raise Blocked('no ci.yml pull_request run for this head')
    run = max(runs, key=lambda r: (r['created_at'], r['id']))
    if run['status'] != 'completed' or run['conclusion'] != 'success':
        raise Blocked(f"ci run {run['id']} is {run['status']} {run['conclusion'] or ''}".strip())
    newest = {}  # a re-run or a later pr-lint is a new check run of the same name; the newest counts
    for c in checks:
        if c['name'] not in newest or c['id'] > newest[c['name']]['id']:
            newest[c['name']] = c
    checks = newest.values()
    pending = sorted(c['name'] for c in checks if c['status'] != 'completed')
    if pending:
        raise Blocked('checks still running: ' + ', '.join(pending))
    failed = sorted(f"{c['name']} ({c['conclusion']})" for c in checks if c['conclusion'] not in PASSED)
    if failed:
        raise Blocked('checks not passed: ' + ', '.join(failed))
    return run


def check_overlap(pr_files, later_files, log_for=lambda paths: ''):
    common = overlap(pr_paths(pr_files), later_files)
    if common:
        later_log = log_for(common)
        raise Blocked(
            'main changed the same files after this PR\'s CI started: ' + ', '.join(common)
            + ('\n' + later_log if later_log else '')
            + '\nBring the branch up to date with main (gh pr update-branch <PR>, or merge'
            ' origin/main), wait for the new CI and a review of the new head, then run this again.')


# --- I/O -----------------------------------------------------------------------------------

def gh(path):
    for delay in (0, 5, 15, 30, 60):
        time.sleep(delay)
        result = subprocess.run(['gh', 'api', f'repos/{REPO}/{path}'], capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        if re.search(r'HTTP 4\d\d', result.stderr):  # 5xx, EOF, resets and timeouts are retried
            raise RuntimeError(f'gh api {path}: {result.stderr.strip()}')
    raise RuntimeError(f'GitHub unavailable for {path}')


def paged(path, key=None):
    items, page = [], 1
    while page <= 30:
        batch = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        batch = batch[key] if key else batch
        items += batch
        if len(batch) < 100:
            return items
        page += 1
    raise RuntimeError(f'{path}: more than 30 pages')


def git(*args):
    for delay in (0, 5, 15) if 'fetch' in args else (0,):
        time.sleep(delay)
        result = subprocess.run(['git', *args], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
    raise RuntimeError(f"git {' '.join(args[:3])}: {result.stderr.strip()}")


def main_changes_since(started):
    """Files main changed since shortly before `started`, and a function listing the main
    (first-parent) commits that changed given paths."""
    git('fetch', '--quiet', 'origin', 'main')
    since = (started - MARGIN).strftime('%Y-%m-%dT%H:%M:%SZ')
    base = git('rev-list', '-1', '--first-parent', f'--before={since}', 'origin/main').strip()
    if not base:
        raise RuntimeError(f'no main commit before {since}')
    # --no-renames lists both sides of a rename on main; -z keeps spaces and non-ASCII paths intact.
    files = set(filter(None, git('diff', '--no-renames', '-z', '--name-only', base, 'origin/main').split('\0')))

    def log_for(paths):
        return git('--literal-pathspecs', 'log', '--no-renames', '--first-parent', '--format=  %h %s', f'{base}..origin/main',
                   '--', *paths).rstrip()
    return files, log_for


def merge(number, head):
    result = subprocess.run(['gh', 'pr', 'merge', str(number), '-R', REPO, '--merge',
                             '--match-head-commit', head], capture_output=True, text=True)
    read = False
    for delay in (0, 5, 10, 20, 30):  # gh may report an error for a merge that went through
        time.sleep(delay)
        try:
            pr = gh(f'pulls/{number}')
        except RuntimeError:
            continue
        read = True
        if pr.get('merged'):
            if pr['head']['sha'] != head:
                raise RuntimeError(f"PR merged with head {pr['head']['sha']}, not {head}")
            return pr['merge_commit_sha']
    if not read:
        raise RuntimeError('merge requested but the PR could not be read back; look at it before retrying')
    if result.returncode == 0:
        raise RuntimeError('gh reported the merge done but the PR still reads unmerged; look at it')
    raise Blocked('merge did not go through: ' + (result.stderr.strip() or result.stdout.strip()))


def guard(number, head, note, dry_run=False, fix_main=False):
    state = check_freeze(note, fix_main)
    check_pr(gh(f'pulls/{number}'), head)
    check_review(paged(f'issues/{number}/comments'), head)
    runs = gh(f'actions/workflows/ci.yml/runs?event=pull_request&head_sha={head}&per_page=20')['workflow_runs']
    run = check_ci(runs, paged(f'commits/{head}/check-runs?filter=latest', 'check_runs'))
    started = datetime.datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
    later, log_for = main_changes_since(started)
    check_overlap(paged(f'pulls/{number}/files'), later, log_for)
    print(f'#{number} {head}: main {state}, approved, CI green (run {run["id"]}), '
          f'no overlap with {len(later)} files main changed since that CI started')
    if dry_run:
        return None
    check_freeze(note, fix_main)
    commit = merge(number, head)
    print(f'merged #{number} as {commit}')
    return commit


class Parser(argparse.ArgumentParser):
    def error(self, message):  # 64 (EX_USAGE), so a usage error never reads as a merge condition
        self.print_usage(sys.stderr)
        print(f'{self.prog}: error: {message}', file=sys.stderr)
        sys.exit(64)


def main(argv=None):
    parser = Parser(description=__doc__.partition('\n\n')[0])
    parser.add_argument('pr', type=int)
    parser.add_argument('--head', required=True, help='the exact reviewed head SHA (40 hex)')
    parser.add_argument('--freeze-note', default=os.environ.get('G2C_FREEZE_NOTE'),
                        help='path to main-freeze.md (default: $G2C_FREEZE_NOTE)')
    parser.add_argument('--dry-run', action='store_true', help='check everything, do not merge')
    parser.add_argument('--fix-main', action='store_true',
                        help='this PR repairs a broken main; allowed while the note says 暂停合并')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[0-9a-f]{40}', args.head):
        parser.error('--head must be the full 40-character SHA')
    if not args.freeze_note:
        parser.error('--freeze-note or G2C_FREEZE_NOTE is required')
    try:
        guard(args.pr, args.head, args.freeze_note, args.dry_run, args.fix_main)
    except Blocked as stop:
        print(f'NOT MERGED #{args.pr}: {stop}', file=sys.stderr)
        return stop.code
    except RuntimeError as error:
        print(f'NOT MERGED #{args.pr}: check could not finish: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
