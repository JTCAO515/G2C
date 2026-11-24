#!/usr/bin/env bash
# Run one CI postgres-shard job as LANES parallel lanes on the same runner (#1445).
#
# Lane k of shard i runs `pg_suites.py --shard (i*LANES+k)/(SHARDS*LANES)`, so across all
# shards and lanes every group still runs exactly once (pg_suites.shard_plan asserts this).
# Lane 0 uses the checkout; every other lane runs in its own copy of it, so the repository
# working directories the suites write (.local/pg-suites/<group>, backend/*/.local) are
# separate. Fixed /tmp socket directories either include a process id or belong to a single
# group, and clusters listen on Unix sockets only, so lanes do not collide.
#
# Lane 0 prints live; the other lanes write to files that are printed when they finish, and
# also on any exit of this script (failure, timeout or cancellation). Each lane is stopped
# after PG_LANE_MINUTES (default 75) where `timeout` exists, which fails the job.
#
# Usage: pg_lanes.sh SHARD SHARDS LANES   (run from the repository root)
set -euo pipefail

shard=$1 shards=$2 lanes=$3
if ! [[ $shard =~ ^[0-9]+$ && $shards =~ ^[1-9][0-9]*$ && $lanes =~ ^[1-9][0-9]*$ ]] || ((shard >= shards)); then
    echo "usage: pg_lanes.sh SHARD SHARDS LANES (0 <= SHARD < SHARDS)" >&2
    exit 2
fi
root=$PWD
work=${RUNNER_TEMP:?RUNNER_TEMP is required}
wrap=()
if command -v timeout >/dev/null; then wrap+=(timeout --kill-after=60 "${PG_LANE_MINUTES:-75}m"); fi
if command -v eatmydata >/dev/null; then wrap+=(eatmydata); fi

printed=()
print_lane() {
    local k=$1 note=$2
    if [[ -z ${printed[k]:-} && -f "$work/pg-lane-$k.log" ]]; then
        printed[k]=1
        echo "=== pg lane $k of shard $shard/$shards ($note) ==="
        cat "$work/pg-lane-$k.log"
    fi
}
pids=()
print_rest() {
    if ((${#pids[@]})); then kill "${pids[@]}" 2>/dev/null || true; fi
    for ((k = 1; k < lanes; k++)); do print_lane "$k" "log at exit"; done
}
trap print_rest EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

dirs=("$root")
for ((k = 1; k < lanes; k++)); do
    dir="$work/pg-lane-$k"
    rsync -a --delete --exclude /.venv --exclude /.local "$root/" "$dir/"
    (cd "$dir" && uv sync --locked --quiet)
    dirs+=("$dir")
done

for ((k = 0; k < lanes; k++)); do
    command=(uv run --locked python -B scripts/pg_suites.py --shard "$((shard * lanes + k))/$((shards * lanes))")
    if ((k == 0)); then
        (cd "${dirs[k]}" && exec ${wrap[@]+"${wrap[@]}"} "${command[@]}") &
    else
        (cd "${dirs[k]}" && exec ${wrap[@]+"${wrap[@]}"} "${command[@]}") >"$work/pg-lane-$k.log" 2>&1 &
    fi
    pids+=($!)
done

status=0
for ((k = 0; k < lanes; k++)); do
    if wait "${pids[k]}"; then result=0; else result=$?; status=1; fi
    echo "=== pg lane $k of shard $shard/$shards finished (exit $result) ==="
    if ((k > 0)); then print_lane "$k" "exit $result"; fi
done
exit "$status"
