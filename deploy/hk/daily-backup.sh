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
selection=$(python3 deploy/hk/daily_backup_image.py)
if [ -n "$selection" ]; then
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
            compose --profile operator run --pull never "$@"
        )
    else
        compose --profile operator run "$@"
    fi
}

api_before=$(compose ps -q --status running api)
worker_before=$(compose ps -q --status running worker)

if compose stop api worker &&
    backup_compose --rm --no-deps backup; then
    compose up -d --no-deps api worker
else
    backup_status=$?
    # Restore only the pair that the timer interrupted, and only when the
    # original backup is no longer active and the signed source release is current.
    if [ -n "$api_before" ] && [ -n "$worker_before" ] &&
        active_backup=$(compose --profile operator ps --all -q --status running --status restarting --status paused backup) &&
        [ -z "$active_backup" ] &&
        backup_compose --rm --no-deps -T --entrypoint python backup -B -m deploy.hk.backup --check-release; then
        if ! compose up -d --no-deps api worker; then
            printf '%s\n' 'ALERT beta_backup_source_resume_failed' >&2
        fi
    fi
    exit "$backup_status"
fi
