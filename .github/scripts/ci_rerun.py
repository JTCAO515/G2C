"""Re-run a failed ci run only when GitHub never gave its failed jobs a runner (#1445).

Hosted macOS arm64 capacity sometimes runs out: a job then waits, gets no runner, finishes
with zero steps and the annotation "The job was not acquired by Runner ...". No test ran, so
re-running it cannot hide a test failure. Any failed job that did run (has a runner or steps),
or that lacks that annotation (for example a job someone cancelled), blocks the re-run. The
`postgres` summary is the one job allowed to fail with steps, and only when every failed
`postgres-shard (N)` was itself never acquired. At most MAX_RERUNS re-runs per run.

Usage (from .github/workflows/ci-rerun.yml): ci_rerun.py; reads GITHUB_REPOSITORY, RUN_ID,
RUN_ATTEMPT and GH_TOKEN. CI_RERUN_DRY_RUN=1 prints the decision without re-running.
"""
import json
import os
import time
import urllib.error
import urllib.request

MAX_RERUNS = 2
UNACQUIRED = 'not acquired by Runner'
FAILED = {'failure', 'cancelled', 'timed_out', 'startup_failure'}


def unacquired(job, annotations):
    return (job.get('conclusion') in FAILED and not job.get('runner_name') and not job.get('steps')
            and any(UNACQUIRED in (a.get('message') or '') for a in annotations))


def decide(jobs, annotations_for, attempt):
    """Return (rerun, reason). annotations_for(job) returns that job's check-run annotations."""
    if attempt > MAX_RERUNS:
        return False, f'attempt {attempt}: re-run limit {MAX_RERUNS} reached'
    failed = [job for job in jobs if job.get('conclusion') in FAILED]
    if not failed:
        return False, 'no failed jobs'
    stuck = {job['name'] for job in failed if unacquired(job, annotations_for(job))}
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


def main():
    run, attempt = os.environ['RUN_ID'], int(os.environ['RUN_ATTEMPT'])
    jobs = api(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    rerun, reason = decide(jobs, lambda job: api(f"check-runs/{job['id']}/annotations"), attempt)
    print(f'run {run} attempt {attempt}: {"re-run" if rerun else "no re-run"} ({reason})')
    if rerun and os.environ.get('CI_RERUN_DRY_RUN') != '1':
        api(f'actions/runs/{run}/rerun-failed-jobs', method='POST')


if __name__ == '__main__':
    main()
