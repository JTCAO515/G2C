#!/usr/bin/env bash
# Specified trial host only. No uninstall, billing, security-group or account changes.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C
[[ $(id -u) == 0 && $(hostname) == iZj6c3ldt64bg18flzpr7hZ && $(uname -m) == x86_64 ]]
[[ $(date -u +%s) -lt 1796054400 ]]
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
trap 'echo "ALERT original Docker preparation failed; inspect this intent and systemd unit before any retry" >&2' ERR
# Alibaba Cloud Linux 3's documented CentOS-release compatibility plugin.
dnf -y install dnf-plugin-releasever-adapter --repo alinux3-plus
curl -q --fail --silent --show-error --proto '=https' --tlsv1.2 --max-time 90 \
  https://download.docker.com/linux/centos/docker-ce.repo -o "$work/docker-ce.repo"
curl -q --fail --silent --show-error --proto '=https' --tlsv1.2 --max-time 90 \
  https://download.docker.com/linux/centos/gpg -o "$work/docker.gpg"
mkdir -m 700 "$work/gpg"
fingerprint=$(gpg --batch --homedir "$work/gpg" --with-colons --import-options show-only --import "$work/docker.gpg" 2>/dev/null | awk -F: '$1=="fpr" {print $10; exit}')
[[ "$fingerprint" == 060A61C51B558A7F742B77AAC52FEB6B621E9F35 ]]
grep -q '^gpgcheck=1$' "$work/docker-ce.repo"
grep -q '^gpgkey=https://download.docker.com/linux/centos/gpg$' "$work/docker-ce.repo"
rpm --import "$work/docker.gpg"
chmod 644 "$work/docker-ce.repo"
ln "$work/docker-ce.repo" /etc/yum.repos.d/g2c-docker-ce.repo
# Retain package signature verification; never allow removal to solve conflicts.
dnf -y --setopt=install_weak_deps=False install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version --format '{{.Server.Version}}'
docker compose version
docker buildx version
(set -o noclobber; printf 'completed; inspect installed versions\n' > "$work/done")
echo 'PASS specified trial host Docker preparation'
