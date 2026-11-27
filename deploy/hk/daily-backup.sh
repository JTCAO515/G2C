#!/bin/sh
set -eu
cd /srv/g2c-beta

compose() {
    if grep -qx 'CJ_BETA_DB_TARGET=hk-local' common.env; then
        docker compose --env-file compose.env -f deploy/hk/compose.yaml -f deploy/hk/compose.local-pg.yaml "$@"
    else
        docker compose --env-file compose.env -f deploy/hk/compose.yaml "$@"
    fi
}

backup_image=
if [ -e backup.image ] || [ -L backup.image ]; then
    selection=$(python3 deploy/hk/daily_backup_image.py)
    if [ -z "$selection" ]; then
        printf '%s\n' 'ALERT beta_backup_image_selection_invalid' >&2
        exit 1
    fi
    backup_tag=${selection% *}
    backup_image=${selection#* }
    expected="$backup_image amd64 ${backup_tag#*:}"
    if ! actual=$(docker image inspect --format '{{.Id}} {{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}}' "$backup_tag") ||
        [ "$actual" != "$expected" ]; then
        printf '%s\n' 'ALERT beta_backup_image_selection_mismatch' >&2
        exit 1
    fi
fi

backup_compose() {
    if [ -n "$backup_image" ]; then
        (
            export CJ_BETA_OPERATOR_IMAGE="$backup_image"
            compose -f deploy/hk/compose.backup-image.yaml --profile operator "$@"
        )
    else
        compose --profile operator "$@"
    fi
}

if [ -n "$backup_image" ]; then
    backup_config=$(backup_compose config --format json)
    if ! printf '%s' "$backup_config" | python3 -c '
import json
import sys

try:
    backup = json.load(sys.stdin)["services"]["backup"]
    valid = backup["image"] == sys.argv[1] and backup["pull_policy"] == "never"
except (KeyError, TypeError, ValueError):
    valid = False
raise SystemExit(0 if valid else 1)
' "$backup_image"; then
        printf '%s\n' 'ALERT beta_backup_image_policy_invalid' >&2
        exit 1
    fi
    unset backup_config
fi

api_before=$(compose ps -q --status running api)
worker_before=$(compose ps -q --status running worker)

# Every run that stops api/worker brings back the ones that were running before it, whatever
# happens next: a failed export, a failed release check, a backup container that is still active,
# or systemd's TimeoutStartSec killing this script. The 2026-11-28 03:00 run stopped both, failed
# with a backup image that predated the live schema, then kept them stopped for 45 minutes because
# the release check ran with the same image. The application still refuses to serve on an
# unverified release by itself, so starting it is never the unsafe step.
stopped=
resumed=
resume_running() {
    set --
    if [ -n "$api_before" ]; then set -- "$@" api; fi
    if [ -n "$worker_before" ]; then set -- "$@" worker; fi
    # An operator may have intentionally stopped either service before the backup.
    if [ "$#" -gt 0 ] && ! compose up -d --no-deps "$@"; then
        printf '%s\n' 'ALERT beta_backup_source_resume_failed' >&2
        return 1
    fi
    resumed=yes
}
on_exit() {
    status=$?
    trap - EXIT
    if [ -n "$stopped" ] && [ -z "$resumed" ]; then
        printf '%s\n' 'ALERT beta_backup_interrupted_resuming_source' >&2
        resume_running || true
    fi
    exit "$status"
}
trap on_exit EXIT
trap 'exit 143' TERM INT HUP

stopped=yes
if compose stop api worker &&
    backup_compose run --rm --no-deps backup; then
    resume_running || exit 1
else
    backup_status=$?
    # Let the original backup container finish first (bounded), so the source is not reopened
    # under a running export; past the bound the source is reopened anyway, with an alert.
    waited=0
    limit=${CJ_BACKUP_ACTIVE_WAIT_SECONDS:-600}
    while active_backup=$(compose --profile operator ps --all -q --status running --status restarting --status paused backup) &&
        [ -n "$active_backup" ] && [ "$waited" -lt "$limit" ]; do
        sleep 5
        waited=$((waited + 5))
    done
    if [ -n "${active_backup:-}" ]; then
        printf '%s\n' 'ALERT beta_backup_still_active_resuming_source' >&2
    fi
    if ! backup_compose run --rm --no-deps -T --entrypoint python backup -B -m deploy.hk.backup --check-release; then
        printf '%s\n' 'ALERT beta_backup_source_release_unverified_resuming_source' >&2
    fi
    resume_running || true
    exit "$backup_status"
fi
