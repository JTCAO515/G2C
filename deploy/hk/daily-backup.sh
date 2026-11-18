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
    # Only a fixed reviewed source tag and its loaded operator image ID.
    if [ ! -f backup.image ] || [ -L backup.image ]; then
        printf '%s\n' 'ALERT beta_backup_image_selection_invalid' >&2
        exit 1
    fi
    selection=$(cat backup.image)
    if [ "$(printf '%s\n' "$selection" | wc -l)" -ne 1 ] ||
        ! printf '%s\n' "$selection" | grep -qxE 'g2c-beta-operator:[0-9a-f]{40} sha256:[0-9a-f]{64}'; then
        printf '%s\n' 'ALERT beta_backup_image_selection_invalid' >&2
        exit 1
    fi
    backup_image=${selection% *}
    expected="${selection#* } amd64 ${backup_image#*:}"
    if ! actual=$(docker image inspect --format '{{.Id}} {{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}}' "$backup_image") ||
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
