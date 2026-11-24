#!/usr/bin/env bash
# Run one CI postgres-shard job as LANES parallel lanes on the same runner (#1445).
#
# Lane k of shard i runs `pg_suites.py --shard (i*LANES+k)/(SHARDS*LANES)`, so across all
# shards and lanes every group still runs exactly once (pg_suites.shard_plan asserts this).
# Lane 0 uses the checkout; every other lane runs in its own copy of it, so the repository
# working directories the suites write (.local/pg-suites/<group>, backend/*/.local) are
# separate. Fixed /tmp socket directories either include the pg_suites process id or belong
# to a single group, and clusters listen on Unix sockets only, so lanes do not collide.
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
if command -v eatmydata >/dev/null; then wrap=(eatmydata); fi

dirs=("$root")
for ((k = 1; k < lanes; k++)); do
    dir="$work/pg-lane-$k"
    rsync -a --delete --exclude /.venv --exclude /.local "$root/" "$dir/"
    (cd "$dir" && uv sync --locked --quiet)
    dirs+=("$dir")
done

pids=()
for ((k = 0; k < lanes; k++)); do
    (cd "${dirs[k]}" && exec ${wrap[@]+"${wrap[@]}"} uv run --locked python -B scripts/pg_suites.py \
        --shard "$((shard * lanes + k))/$((shards * lanes))") >"$work/pg-lane-$k.log" 2>&1 &
    pids+=($!)
done

status=0
for ((k = 0; k < lanes; k++)); do
    if wait "${pids[k]}"; then result=0; else result=$?; status=1; fi
    echo "=== pg lane $k of shard $shard/$shards (exit $result) ==="
    cat "$work/pg-lane-$k.log"
done
exit "$status"
