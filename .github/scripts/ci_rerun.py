"""Re-run a failed ci run only when GitHub never gave its failed jobs a runner (#1445).

Hosted macOS arm64 capacity sometimes runs out: a job then waits, gets no runner, finishes
with zero steps and the annotation "The job was not acquired by Runner ...". No test ran, so
re-running it cannot hide a test failure. Any failed job that did run (has a runner or steps),
or that lacks that annotation (for example a job someone cancelled), blocks the re-run. The
`postgres` summary is the one job allowed to fail with steps, and only when every failed
`postgres-shard (N)` was itself never acquired. At most MAX_RERUNS re-runs per run.

Only the newest failed main-push run is handled; a run of a commit that main has moved past is
left alone. A re-run started with GITHUB_TOKEN does not fire workflow_run again, so this job
waits for its re-run to finish and, if that attempt is again only capacity misses, re-runs once
more. Reads GITHUB_REPOSITORY, GH_TOKEN and RUN_ID; CI_RERUN_DRY_RUN=1 only prints.
"""
import json
import os
import time
import urllib.error
import urllib.request

MAX_RERUNS = 2
UNACQUIRED = 'not acquired by Runner'
FAILED = {'failure', 'cancelled', 'timed_out', 'startup_failure'}


def never_ran(job):
    return job.get('conclusion') in FAILED and not job.get('runner_name') and not job.get('steps')


def unacquired(job, annotations_for):
    return never_ran(job) and any(UNACQUIRED in (a.get('message') or '') for a in annotations_for(job))


def decide(jobs, annotations_for, attempt):
    """Return (rerun, reason). annotations_for(job) returns that job's check-run annotations."""
    if attempt > MAX_RERUNS:
        return False, f'attempt {attempt}: re-run limit {MAX_RERUNS} reached'
    failed = [job for job in jobs if job.get('conclusion') in FAILED]
    if not failed:
        return False, 'no failed jobs'
    stuck = {job['name'] for job in failed if unacquired(job, annotations_for)}
    real = [job['name'] for job in failed if job['name'] not in stuck]
    shards_stuck = any(name.startswith('postgres-shard') for name in stuck)
    shards_real = any(name.startswith('postgres-shard') for name in real)
    if real == ['postgres'] and shards_stuck and not shards_real:
        real = []  # the summary failed only because unacquired shards did not succeed
    if real:
        return False, 'failed jobs that ran or were not capacity misses: ' + ', '.join(sorted(real))
    return True, 'never acquired a runner: ' + ', '.join(sorted(stuck))


def api(path, method='GET'):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}", method=method,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    for delay in (0, 5, 15, 30, 60):
        time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            if error.code < 500:
                raise
        except OSError:
            pass
    raise SystemExit(f'GitHub API unavailable for {path}')


WAIT_SECONDS = 60
WAIT_LIMIT = 150  # polls per attempt; the job itself has a timeout as well


def newest_main_push(call):
    runs = call('actions/workflows/ci.yml/runs?event=push&branch=main&per_page=1')['workflow_runs']
    return runs[0]['id'] if runs else None


def handle(run_id, call=None, sleep=time.sleep, dry_run=False):
    """Re-run run_id while it stays the newest main push and fails only by capacity misses."""
    call = call or api
    while True:
        run = call(f'actions/runs/{run_id}')
        if run['event'] != 'push' or run['head_branch'] != 'main' or run['conclusion'] != 'failure':
            return f"run {run_id}: not a failed main push ({run['event']}, {run['conclusion']})"
        if newest_main_push(call) != run['id']:
            return f'run {run_id}: main has a newer push; superseded run left alone'
        attempt = run['run_attempt']
        jobs = call(f'actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100')['jobs']
        rerun, reason = decide(jobs, lambda job: call(f"check-runs/{job['id']}/annotations"), attempt)
        print(f"run {run_id} attempt {attempt}: {'re-run' if rerun else 'no re-run'} ({reason})", flush=True)
        if not rerun or dry_run:
            return reason
        call(f'actions/runs/{run_id}/rerun-failed-jobs', method='POST')
        for _ in range(WAIT_LIMIT):
            sleep(WAIT_SECONDS)
            run = call(f'actions/runs/{run_id}')
            if run['run_attempt'] > attempt and run['status'] == 'completed':
                break
        else:
            return f'run {run_id}: attempt {attempt + 1} did not finish in time'


def main():
    print(handle(os.environ['RUN_ID'], dry_run=os.environ.get('CI_RERUN_DRY_RUN') == '1'))


if __name__ == '__main__':
    main()
