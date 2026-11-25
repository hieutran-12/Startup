#!/usr/bin/env bash
# Chạy deploy/deploy.sh trên EC2 qua AWS SSM. Job deploy-staging, deploy-production của
# .gitlab-ci.yml gọi script này sau khi đã có khoá AWS tạm (OIDC). Không cần SSH, không mở cổng.
#
#   bash deploy/ssm-run.sh staging <tag> | production <tag> | rollback | status
#
# Cách gửi: nén deploy.sh (gzip + base64, chỉ còn chữ và số nên nhét vào JSON an toàn), SSM chạy
# trên EC2: giải nén ra /tmp rồi `bash` nó. EC2 không cần giữ bản deploy.sh nào: luôn chạy đúng
# bản trong commit đang deploy.
set -euo pipefail

INSTANCE_NAME=${INSTANCE_NAME:-thiepcuoi-api}
args="$*"
[[ "$args" =~ ^(staging|production)\ [0-9a-f]{7,40}$|^rollback$|^status$ ]] ||
  { echo "Tham số không hợp lệ: '$args'"; exit 2; }

instance_id=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$instance_id" != None ] || { echo "Không thấy EC2 đang chạy có tag Name=$INSTANCE_NAME"; exit 1; }

payload=$(gzip -9c "$(dirname "$0")/deploy.sh" | base64 | tr -d "\n")
params=$(printf '{"commands":["echo %s | base64 -d | gunzip > /tmp/thiepcuoi-deploy.sh","bash /tmp/thiepcuoi-deploy.sh %s"],"executionTimeout":["900"]}' \
  "$payload" "$args")

command_id=$(aws ssm send-command --instance-ids "$instance_id" \
  --document-name AWS-RunShellScript \
  --comment "deploy.sh $args (pipeline ${CI_PIPELINE_ID:-tay})" \
  --parameters "$params" --query Command.CommandId --output text)
echo "SSM command $command_id: deploy.sh $args"

# Hỏi trạng thái mỗi 5 giây, tối đa 15 phút (bằng executionTimeout ở trên)
status=Pending
for _ in $(seq 1 180); do
  sleep 5
  status=$(aws ssm get-command-invocation --command-id "$command_id" --instance-id "$instance_id" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "$status" in Success | Failed | Cancelled | TimedOut) break ;; esac
done

aws ssm get-command-invocation --command-id "$command_id" --instance-id "$instance_id" \
  --query StandardOutputContent --output text
errors=$(aws ssm get-command-invocation --command-id "$command_id" --instance-id "$instance_id" \
  --query StandardErrorContent --output text)
if [ -n "$errors" ] && [ "$errors" != None ]; then
  echo "--- stderr ---"
  echo "$errors" | tail -40
fi
echo "Kết quả trên EC2: $status"
[ "$status" = Success ]
