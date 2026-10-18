#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# EC2 runs this as root during the first boot of a new Ubuntu 22.04 instance.
apt-get -o Acquire::Retries=5 update
apt-get -o Acquire::Retries=5 install -y --no-install-recommends ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl --retry 5 --retry-delay 3 --fail --silent --show-error --location \
  https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get -o Acquire::Retries=5 update
apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker ubuntu
install -d -m 0755 -o ubuntu -g ubuntu /opt/livechat-backend /opt/livechat-frontend

# Keep these checks in the boot log; a running VM alone is not proof of success.
docker --version
docker compose version
docker info > /dev/null
touch /var/lib/livechat-bootstrap-complete
