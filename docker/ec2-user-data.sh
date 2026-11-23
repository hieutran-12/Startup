#!/bin/bash
# User data cho EC2 chạy API (Ubuntu 24.04 arm64), chạy một lần khi máy khởi động lần đầu.
# Cài Docker, compose, Nginx, AWS CLI; cho docker pull từ ECR bằng IAM role của máy. Sau đó: README › Lên production.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

# t4g.small chỉ có 2 GB RAM: thêm 1 GB swap phòng lúc pull image
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

apt-get -o DPkg::Lock::Timeout=600 update
apt-get -o DPkg::Lock::Timeout=600 install -y docker.io docker-compose-v2 nginx amazon-ecr-credential-helper
snap install aws-cli --classic
systemctl enable --now docker
usermod -aG docker ubuntu

# ECR của chính tài khoản này (đọc account và region từ metadata của máy, IMDSv2)
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
DOC=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/dynamic/instance-identity/document)
ACCOUNT=$(echo "$DOC" | python3 -c 'import json,sys; print(json.load(sys.stdin)["accountId"])')
REGION=$(echo "$DOC" | python3 -c 'import json,sys; print(json.load(sys.stdin)["region"])')
for d in /root/.docker /home/ubuntu/.docker; do
  mkdir -p "$d"
  echo "{\"credHelpers\": {\"$ACCOUNT.dkr.ecr.$REGION.amazonaws.com\": \"ecr-login\"}}" > "$d/config.json"
done
chown -R ubuntu:ubuntu /home/ubuntu/.docker

mkdir -p /opt/thiepcuoi
