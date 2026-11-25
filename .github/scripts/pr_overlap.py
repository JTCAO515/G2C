"""Which files two changes have in common, as the merge guard and pr-lint judge it.

Two changes overlap when they touch the same path, or both touch a shared area that only one
open PR may change at a time (docs/plan/issue-plan.md 现行流程 item 3). Run directly in pr-lint,
it reports the open PRs whose files overlap this PR's and never fails the job.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Areas where only one open PR may change files at a time, even different files in them.
SHARED_AREAS = ('contracts/', 'docs/plan/', 'backend/migrations/', 'scripts/test.py')


def area(path):
    return next((shared for shared in SHARED_AREAS if path == shared or path.startswith(shared)), None)


def overlap(ours, theirs):
    """Sorted paths or shared areas both sets of paths touch."""
    ours, theirs = set(ours), set(theirs)
    common = ours & theirs
    common |= {area(path) for path in ours} & {area(path) for path in theirs} - {None}
    return sorted(common)


def pr_paths(files):
    """Paths a PR touches, from the pulls/<n>/files listing, counting both sides of a rename."""
    paths = set()
    for item in files:
        paths.add(item['filename'])
        if item.get('previous_filename'):
            paths.add(item['previous_filename'])
    return paths


def api(path):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    for delay in (0, 5, 15, 30):
        time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code < 500:
                raise
        except OSError:
            pass
    raise RuntimeError(f'GitHub API unavailable for {path}')


def paged(call, path):
    items, page = [], 1
    while True:
        batch = call(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        items += batch
        if len(batch) < 100:
            return items
        page += 1


def report(number, call):
    """Lines describing each other open PR that overlaps PR `number`."""
    ours = pr_paths(paged(call, f'pulls/{number}/files'))
    lines = []
    for pr in paged(call, 'pulls?state=open'):
        if pr['number'] == number:
            continue
        common = overlap(ours, pr_paths(paged(call, f"pulls/{pr['number']}/files")))
        if common:
            stacked = ' (stacked)' if pr['head']['ref'] == os.environ.get('BASE_REF') else ''
            shown = ', '.join(common[:8]) + (f' and {len(common) - 8} more' if len(common) > 8 else '')
            lines.append(f"#{pr['number']}{stacked} overlaps on {shown}")
    return lines


def main():
    number = int(os.environ['PR_NUMBER'])
    try:
        lines = report(number, api)
    except Exception as error:  # report only: an API problem never fails pr-lint
        print(f'::warning::open PR overlap report unavailable: {error}')
        return
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if not lines:
        print('No other open PR touches the same files or shared areas')
        return
    for line in lines:
        print(f'::warning::{line}. Open PRs must not overlap (docs/plan/issue-plan.md 现行流程 3); '
              'merge one first, then update the other and run CI again.')
    if summary:
        with open(summary, 'a', encoding='utf-8') as out:
            out.write('### Open PRs with overlapping files\n\n' + ''.join(f'- {l}\n' for l in lines))


if __name__ == '__main__':
    sys.exit(main())
