#!/usr/bin/env bash
# Specified trial host only. No uninstall, billing, security-group or account changes.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C
[[ $(id -u) == 0 && $(hostname) == iZj6c3ldt64bg18flzpr7hZ && $(uname -m) == x86_64 ]]
[[ ${CJ_TRIAL_ZERO_CONFIRMED:-} == 1 ]]
trial_end=$(date -u -d "${CJ_TRIAL_VALID_UNTIL:?verified trial expiry required}" +%s)
now=$(date -u +%s)
[[ "$now" -lt 1796054400 && "$now" -lt "$trial_end" ]]
grep -q '^NAME="Alibaba Cloud Linux"' /etc/os-release
[[ ! -e /etc/docker/daemon.json && ! -e /etc/systemd/system/docker.service ]]
if compgen -G '/etc/yum.repos.d/*docker*.repo' >/dev/null; then
  echo 'HOLD existing Docker repository requires inspection' >&2; exit 40
fi
for package in docker-ce docker-ce-cli containerd.io podman runc; do
  if rpm -q --quiet "$package"; then echo 'HOLD existing container package requires inspection' >&2; exit 40; fi
done
work=/srv/g2c-beta/host-prepare
mkdir -p "$work"
[[ $(stat -c '%u:%a' /srv/g2c-beta) == 0:700 && $(stat -c '%u:%a' "$work") == 0:700 ]]
exec 9>"$work/lock"
flock -n 9
[[ ! -e "$work/intent" && ! -e "$work/done" ]]
(set -o noclobber; printf 'original docker package operation\n' > "$work/intent")
sync -f "$work"
trap 'echo "ALERT original Docker preparation failed; inspect this intent and systemd unit before any retry" >&2' ERR
# Fixed Alibaba Cloud Linux 3 uses the vendor's EL8-compatible packages.
# Do not consume a downloaded repository configuration or other enabled repos.
curl -q --fail --silent --show-error --proto '=https' --tlsv1.2 --max-time 90 \
  https://download.docker.com/linux/centos/gpg -o "$work/docker.gpg"
mkdir -m 700 "$work/gpg"
gpg --batch --homedir "$work/gpg" --with-colons --import-options show-only --import "$work/docker.gpg" > "$work/key-metadata"
[[ $(awk -F: '$1=="pub" {n++} END {print n+0}' "$work/key-metadata") == 1 ]]
fingerprint=$(awk -F: '$1=="pub" {waiting=1; next} waiting && $1=="fpr" {print $10; waiting=0}' "$work/key-metadata")
[[ "$fingerprint" == 060A61C51B558A7F742B77AAC52FEB6B621E9F35 ]]
rpm --import "$work/docker.gpg"
cat > "$work/docker-ce.repo" <<'REPO'
[docker-ce-stable]
name=G2C fixed Docker CE stable
baseurl=https://download.docker.com/linux/centos/8/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=file:///srv/g2c-beta/host-prepare/docker.gpg
REPO
chmod 644 "$work/docker-ce.repo"
ln "$work/docker-ce.repo" /etc/yum.repos.d/g2c-docker-ce.repo
# Only already-trusted Alibaba repos and the one verified Docker primary key.
# Empty transaction gpgkey options prohibit auto-import of another fetched key.
repos=(alinux3-os alinux3-updates alinux3-module alinux3-plus alinux3-powertools docker-ce-stable)
command=(dnf -y --disablerepo='*' --setopt=install_weak_deps=False)
for repo in "${repos[@]}"; do
  command+=(--enablerepo="$repo" --setopt="$repo.gpgcheck=1" --setopt="$repo.gpgkey=")
done
"${command[@]}" install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version --format '{{.Server.Version}}'
docker compose version
docker buildx version
(set -o noclobber; printf 'completed; inspect installed versions\n' > "$work/done")
sync -f "$work"
echo 'PASS specified trial host Docker preparation'
