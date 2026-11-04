#!/bin/sh
set -eu
cd /srv/g2c-beta
docker compose --env-file compose.env -f deploy/hk/compose.yaml stop api worker
docker compose --env-file compose.env -f deploy/hk/compose.yaml --profile operator run --rm --no-deps backup
docker compose --env-file compose.env -f deploy/hk/compose.yaml up -d --no-deps api worker
