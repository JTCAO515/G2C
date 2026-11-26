#!/bin/bash
set -euo pipefail
umask 077
source_dir=${1:?reviewed source directory required}
revision=${2:?reviewed revision required}
[[ $revision =~ ^[a-f0-9]{40}$ ]]
root=/srv/g2c-beta
home=$root/jt-workbench
config=$root/deploy/hk/Caddyfile
pgdata=$root/local-pg/pg/data
bundle=$source_dir/deploy/hk/jt-workbench
host_bundle=$root/deploy/hk/jt-workbench
caddy=g2c-beta-caddy-1
api=g2c-beta-api-1
postgres=g2c-beta-postgres-1

exec 9<"$root/probes/application-deploy.lock"
flock -n -x 9
systemctl is-active --quiet g2c-beta-backup.timer
[[ $(systemctl show -p ActiveState --value g2c-beta-backup.service) == inactive ]]
[[ $(docker inspect --format '{{.State.Health.Status}}' "$api") == healthy ]]
[[ $(docker exec "$caddy" caddy version | cut -d ' ' -f 1) == v2.11.* ]]
[[ $(docker inspect --format '{{json .Config.Cmd}}' "$caddy") == '["caddy","run","--config","/etc/caddy/Caddyfile","--adapter","caddyfile"]' ]]
caps=$(docker inspect --format '{{json .HostConfig.CapAdd}} {{json .HostConfig.CapDrop}} {{.Config.User}}' "$caddy")
case "$caps" in
  '["NET_BIND_SERVICE"] ["ALL"] '|'["CAP_NET_BIND_SERVICE"] ["ALL"] ') ;;
  *) exit 1 ;;
esac
[[ -r $bundle/compose.yaml && -r $config && ! -L $config && -S $root/local-pg-socket/.s.PGSQL.5432 ]]
[[ -x /usr/lib/systemd/systemd-socket-proxyd && -x /usr/bin/setpriv ]]
awk '/^MemTotal:/{total=$2} /^MemAvailable:/{available=$2} END{exit !(available > total/5+512*1024)}' /proc/meminfo
[[ $(df -Pm "$root" | awk 'END{print $4}') -ge 4096 ]]

# Prepare files without changing anything reachable from the public listener.
install -d -m 0700 "$home"
install -d -o 0 -g 10031 -m 0750 "$home/db"
install -d -o 10001 -g 10001 -m 0700 "$home/backups"
install -d -o 10031 -g 0 -m 2750 "$root/caddy-config/jt-workbench"
install -d -m 0755 "$host_bundle"
for file in compose.yaml backup.py offboard.py recover_admin.py; do install -m 0644 "$bundle/$file" "$host_bundle/$file"; done
python3 - "$home" <<'PY'
import os, secrets, stat, sys
from pathlib import Path
from urllib.parse import quote

root = Path(sys.argv[1])
for purpose, user, uid in (("owner", "jt_workbench_owner", 10031), ("runtime", "jt_workbench_runtime", 10031)):
    path = root / (purpose + ".dsn")
    if not path.exists():
        safe_host = quote("/run/jt-workbench-db", safe="")
        dsn = f"postgresql://{user}:{secrets.token_urlsafe(36)}@/jt_workbench?host={safe_host}&port=5432&sslmode=disable\n"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as output:
            os.fchown(output.fileno(), uid, uid)
            output.write(dsn)
            output.flush()
            os.fsync(output.fileno())
    elif path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600 or path.stat().st_uid != uid:
        raise SystemExit("unexpected private DSN file")
PY
install -o 10001 -g 10001 -m 0600 "$home/owner.dsn" "$home/backup.dsn"

candidate="$source_dir/deploy/hk/Caddyfile"
if ! cmp -s "$config" "$candidate"; then
  # The candidate must preserve every byte currently routing CJ.
  python3 - "$config" "$candidate" <<'PY'
from pathlib import Path
import sys
old, new = (Path(name).read_bytes() for name in sys.argv[1:])
header = b"\njtadmin.go2china.space {\n"
if header in old or not new.startswith(old.rstrip(b"\n") + b"\n" + header) or new.count(header) != 1:
    raise SystemExit("Caddy candidate is not an append-only workbench site")
PY
fi
docker exec -i "$caddy" caddy validate --config - --adapter caddyfile < "$candidate"

app_base=$(docker inspect --format '{{.Image}}' "$api")
[[ $app_base =~ ^sha256:[a-f0-9]{64}$ ]]
base_tag=jt-workbench-base:${app_base#sha256:}
docker image tag "$app_base" "$base_tag"
backup_image=$(docker inspect --format '{{.Image}}' "$postgres")
[[ $backup_image =~ ^sha256:[a-f0-9]{64}$ ]]
image=jt-workbench:$revision
docker build --pull=false --network=none --label "org.opencontainers.image.revision=$revision" \
  --build-arg "JT_WORKBENCH_RUNTIME_IMAGE=$base_tag" -f "$source_dir/jt/workbench/Dockerfile" -t "$image" "$source_dir"
[[ $(docker image inspect --format '{{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}}' "$image") == "amd64 $revision" ]]
printf 'JT_WORKBENCH_IMAGE=%s\nJT_WORKBENCH_BACKUP_IMAGE=%s\n' "$image" "$backup_image" > "$home/images.env"

# Add only the dedicated database authentication rule. PostgreSQL is reloaded, never restarted.
include="include jt_workbench_hba.conf"
install -o 10001 -g 10001 -m 0600 "$bundle/pg_hba.conf" "$pgdata/jt_workbench_hba.conf"
hba_added=false
if ! grep -Fxq "$include" "$pgdata/pg_hba.conf"; then
  [[ ! -e $home/pg_hba.before ]]
  cp "$pgdata/pg_hba.conf" "$home/pg_hba.before"
  next=$(mktemp "$pgdata/.jt-workbench-hba.XXXXXXXX")
  { printf '%s\n' "$include"; cat "$pgdata/pg_hba.conf"; } > "$next"
  chown --reference="$pgdata/pg_hba.conf" "$next"
  chmod --reference="$pgdata/pg_hba.conf" "$next"
  mv "$next" "$pgdata/pg_hba.conf"
  hba_added=true
fi
restore_hba() {
  if "$hba_added"; then
    cat "$home/pg_hba.before" > "$pgdata/pg_hba.conf"
    rm -- "$home/pg_hba.before"
    docker kill --signal HUP "$postgres" >/dev/null
  fi
}
trap restore_hba ERR
python3 - "$home" <<'PY' | docker exec -i "$postgres" python -B -c "$(cat "$bundle/database.py")"
import json, sys
from pathlib import Path
from urllib.parse import urlsplit
root = Path(sys.argv[1])
connections = [urlsplit((root / (purpose + ".dsn")).read_text().strip()) for purpose in ("owner", "runtime")]
json.dump({item.username: item.password for item in connections}, sys.stdout)
PY
trap - ERR
for unit in jt-workbench-postgres.service jt-workbench-postgres.socket jt-workbench-backup.service; do
  install -m 0644 "$bundle/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now jt-workbench-postgres.socket
compose() { docker compose --env-file "$home/images.env" -f "$host_bundle/compose.yaml" "$@"; }
compose config --quiet
compose run --rm --no-deps -T migrate
compose up -d --no-deps --wait --wait-timeout 35 app
[[ $(docker inspect --format '{{.State.Health.Status}}' "$api") == healthy ]]

# Verify the private PostgreSQL dump from the same unit the daily backup will launch.
systemctl start jt-workbench-backup.service
install -d -m 0755 /etc/systemd/system/g2c-beta-backup.service.d
install -m 0644 "$bundle/g2c-beta-backup.workbench.conf" /etc/systemd/system/g2c-beta-backup.service.d/70-jt-workbench.conf
systemctl daemon-reload

restore_caddy() {
  cat "$home/Caddyfile.before" > "$config"
  docker kill --signal USR1 "$caddy" >/dev/null
}
if cmp -s "$config" "$candidate"; then
  # A matching disk config may be left by an earlier signal whose result was unknown.
  [[ -f $home/Caddyfile.before && ! -L $home/Caddyfile.before ]]
else
  if [[ -e $home/Caddyfile.before ]]; then
    cmp -s "$config" "$home/Caddyfile.before"
  else
    cp "$config" "$home/Caddyfile.before"
  fi
  trap restore_caddy ERR
  # The running container uses a single-file bind mount, so retain its inode on the host.
  cat "$candidate" > "$config"
fi
trap restore_caddy ERR
docker kill --signal USR1 "$caddy" >/dev/null
curl --noproxy '*' --fail --silent --show-error --retry 2 --max-time 6 \
  --resolve api-beta.go2china.space:443:127.0.0.1 https://api-beta.go2china.space/health/ready >/dev/null
trap - ERR
for attempt in {1..12}; do
  if login=$(curl --noproxy '*' --fail --silent --max-time 3 \
    --resolve jtadmin.go2china.space:443:127.0.0.1 https://jtadmin.go2china.space/login) &&
    [[ $login == *'首次设置或重绑验证器'* ]]; then
    printf '%s\n' 'JT workbench login ready with a trusted HTTPS certificate.'
    exit 0
  fi
  sleep 3
done
printf '%s\n' 'JT workbench still waiting for HTTPS or login readback.' >&2
exit 2
