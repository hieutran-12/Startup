#!/usr/bin/env bash
# Deploy API trên EC2. Chạy bằng root, do job deploy-* của .gitlab-ci.yml gửi tới qua SSM
# (deploy/ssm-run.sh); chạy tay cũng được: sudo bash deploy/deploy.sh <lệnh> ...
#
#   deploy.sh staging <tag>      api-staging (127.0.0.1:8001) chạy image <tag>
#   deploy.sh production <tag>   blue-green: màu đang nghỉ chạy image <tag>, khỏe thì Nginx chuyển
#                                sang, kiểm tra lại qua HTTPS, lỗi thì tự quay về màu cũ
#   deploy.sh rollback           Nginx chuyển ngay về màu kia (bản trước), nếu màu đó còn khỏe
#   deploy.sh status             màu đang phục vụ và image của từng service
#
# Thư mục /opt/thiepcuoi trên EC2:
#   docker-compose.prod.yml  3 service: api-blue (:8000), api-green (:8002), api-staging (:8001)
#   .env                     biến cho compose: API_REPOSITORY, API_IMAGE_BLUE/GREEN/STAGING
#   production.env           cấu hình app production; staging.env: cấu hình app staging
# Nginx: /etc/nginx/conf.d/thiepcuoi-upstream.conf chỉ chứa upstream thiepcuoi_production,
# trỏ tới cổng của màu đang phục vụ. Script này là nơi duy nhất sửa file đó.
set -euo pipefail

DIR=/opt/thiepcuoi
UPSTREAM_FILE=/etc/nginx/conf.d/thiepcuoi-upstream.conf
PUBLIC_HOST=api.ketduyen.me
REQUIRED_KEYS="DATABASE_URL JWT_SECRET CORS_ORIGINS S3_BUCKET MEDIA_PUBLIC_BASE_URL"

cd "$DIR"
compose() { docker compose -f docker-compose.prod.yml "$@"; }
log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }
die() { log "LỖI: $*"; exit 1; }

# Hai lần deploy không được chạy cùng lúc (GitLab đã có resource_group, đây là chốt thứ hai)
exec 9>/var/lock/thiepcuoi-deploy.lock
flock -w 600 9 || die "đang có lần deploy khác chạy quá 10 phút"

port_of() {
  case "$1" in
    blue) echo 8000 ;;
    green) echo 8002 ;;
    staging) echo 8001 ;;
  esac
}
other_color() { if [ "$1" = blue ]; then echo green; else echo blue; fi; }

# Màu đang phục vụ: đọc cổng trong file upstream của Nginx
active_color() {
  if grep -q "127.0.0.1:8002" "$UPSTREAM_FILE"; then echo green; else echo blue; fi
}

# Ghi KEY=VALUE vào .env của compose (thay dòng cũ nếu có)
set_compose_var() {
  if grep -q "^$1=" .env; then sed -i "s#^$1=.*#$1=$2#" .env; else echo "$1=$2" >>.env; fi
}

check_env_file() {
  [ -f "$1" ] || die "thiếu $DIR/$1"
  for key in $REQUIRED_KEYS; do
    grep -q "^$key=." "$1" || die "thiếu $key trong $1"
  done
}

# Đợi tối đa 60 giây cho tới khi /health của cổng trả 200
wait_healthy() {
  for _ in $(seq 1 30); do
    if curl -fs -o /dev/null --max-time 3 "http://127.0.0.1:$1/health"; then return 0; fi
    sleep 2
  done
  return 1
}

write_upstream() {
  cat >"$UPSTREAM_FILE" <<EOF
# Do /opt/thiepcuoi/deploy.sh ghi: màu đang phục vụ api.ketduyen.me là $1. Không sửa tay.
upstream thiepcuoi_production {
    server 127.0.0.1:$(port_of "$1");
}
EOF
}

reload_nginx() { nginx -t -q && systemctl reload nginx; }

# Gọi /health qua Nginx với HTTPS thật (đúng đường đi của người dùng), 5 lần liền phải qua cả 5
verify_public() {
  for _ in 1 2 3 4 5; do
    curl -fsS -o /dev/null --max-time 5 --resolve "$PUBLIC_HOST:443:127.0.0.1" \
      "https://$PUBLIC_HOST/health" || return 1
    sleep 1
  done
}

# Chạy migration bằng image mới, trước khi bản mới nhận request
migrate() { compose run --rm --no-deps "$1" alembic upgrade head; }

seed() { compose exec -T "$1" python -m app.scripts.seed_templates; }

deploy_staging() {
  local tag=$1
  check_env_file staging.env
  log "staging: image $tag"
  # Tải image trước: tag sai thì dừng ở đây, .env chưa bị đổi
  docker pull -q "$API_REPOSITORY:$tag" >/dev/null
  set_compose_var API_IMAGE_STAGING "$API_REPOSITORY:$tag"
  migrate api-staging
  compose up -d api-staging
  if ! wait_healthy "$(port_of staging)"; then
    compose logs --tail 50 api-staging
    die "api-staging không khỏe sau 60 giây"
  fi
  seed api-staging
  log "staging đang chạy $tag"
}

deploy_production() {
  local tag=$1 active next
  check_env_file production.env
  active=$(active_color)
  next=$(other_color "$active")
  log "production: đang phục vụ $active, deploy $tag vào $next"

  # Tải image trước: tag sai thì dừng ở đây, .env chưa bị đổi
  docker pull -q "$API_REPOSITORY:$tag" >/dev/null
  set_compose_var "API_IMAGE_${next^^}" "$API_REPOSITORY:$tag"
  # Migration phải tương thích ngược: bản $active (cũ) vẫn phục vụ trên schema mới cho tới khi đổi
  migrate "api-$next"
  compose up -d "api-$next"
  if ! wait_healthy "$(port_of "$next")"; then
    compose logs --tail 50 "api-$next"
    compose stop "api-$next"
    die "api-$next không khỏe: không đổi gì, $active vẫn phục vụ"
  fi

  cp "$UPSTREAM_FILE" "$UPSTREAM_FILE.bak"
  write_upstream "$next"
  reload_nginx
  if ! verify_public; then
    log "kiểm tra https://$PUBLIC_HOST/health lỗi: quay về $active"
    cp "$UPSTREAM_FILE.bak" "$UPSTREAM_FILE"
    reload_nginx
    compose logs --tail 50 "api-$next"
    compose stop "api-$next"
    die "đã tự quay về $active"
  fi

  seed "api-$next"
  # Màu cũ vẫn chạy để rollback tức thì; lần deploy sau sẽ thay nó bằng bản mới hơn
  log "production: $next đang phục vụ $tag; $active (bản trước) vẫn chạy để rollback"
  docker image prune -af --filter "until=168h" >/dev/null 2>&1 || true
}

rollback() {
  local active previous
  active=$(active_color)
  previous=$(other_color "$active")
  wait_healthy "$(port_of "$previous")" || die "api-$previous không chạy hoặc không khỏe: deploy lại tag cũ"
  cp "$UPSTREAM_FILE" "$UPSTREAM_FILE.bak"
  write_upstream "$previous"
  reload_nginx
  verify_public || { cp "$UPSTREAM_FILE.bak" "$UPSTREAM_FILE"; reload_nginx; die "$previous lỗi, giữ $active"; }
  log "rollback xong: $previous đang phục vụ (trước đó là $active)"
}

status() {
  log "màu đang phục vụ production: $(active_color)"
  grep '^API_IMAGE_' .env | sed 's#=.*:#: #'
  compose ps --format '{{.Service}}: {{.Status}}'
}

[ -f .env ] || die "thiếu $DIR/.env"
# shellcheck disable=SC1091
. ./.env
[ -n "${API_REPOSITORY:-}" ] || die "thiếu API_REPOSITORY trong .env"

case "${1:-}" in
  staging | production)
    tag=${2:-}
    [[ "$tag" =~ ^[0-9a-f]{7,40}$ ]] || die "tag phải là commit hash, nhận được: '$tag'"
    "deploy_$1" "$tag"
    ;;
  rollback) rollback ;;
  status) status ;;
  *) die "cách dùng: deploy.sh staging|production <tag> | rollback | status" ;;
esac
