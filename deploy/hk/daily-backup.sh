#!/bin/sh
set -eu
cd /srv/g2c-beta

compose() {
    docker compose --env-file compose.env -f deploy/hk/compose.yaml "$@"
}

api_before=$(compose ps -q --status running api)
worker_before=$(compose ps -q --status running worker)

if compose stop api worker &&
    compose --profile operator run --rm --no-deps backup; then
    compose up -d --no-deps api worker
else
    backup_status=$?
    # Restore only the pair that the timer interrupted, and only when the
    # original backup is no longer active and the signed source release is current.
    if [ -n "$api_before" ] && [ -n "$worker_before" ] &&
        active_backup=$(compose --profile operator ps --all -q --status running --status restarting --status paused backup) &&
        [ -z "$active_backup" ] &&
        compose --profile operator run --rm --no-deps -T --entrypoint python backup -B -m deploy.hk.backup --check-release; then
        if ! compose up -d --no-deps api worker; then
            printf '%s\n' 'ALERT beta_backup_source_resume_failed' >&2
        fi
    fi
    exit "$backup_status"
fi
