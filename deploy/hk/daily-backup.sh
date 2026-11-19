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

if compose stop api worker &&
    backup_compose run --rm --no-deps backup; then
    compose up -d --no-deps api worker
else
    backup_status=$?
    # Restore only the pair that the timer interrupted, and only when the
    # original backup is no longer active and the signed source release is current.
    if [ -n "$api_before" ] && [ -n "$worker_before" ] &&
        active_backup=$(compose --profile operator ps --all -q --status running --status restarting --status paused backup) &&
        [ -z "$active_backup" ] &&
        backup_compose run --rm --no-deps -T --entrypoint python backup -B -m deploy.hk.backup --check-release; then
        if ! compose up -d --no-deps api worker; then
            printf '%s\n' 'ALERT beta_backup_source_resume_failed' >&2
        fi
    fi
    exit "$backup_status"
fi
