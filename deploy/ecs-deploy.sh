#!/usr/bin/env bash
# Roll an image out to the ECS cluster: run its migrations, then move api,
# worker and beat to it and wait until they settle. Run by
# .github/workflows/deploy.yml; works the same from a shell with credentials.
#
#   AWS_REGION=eu-west-1 ECS_CLUSTER=backend-template deploy/ecs-deploy.sh <image uri>
#
# Task definition families are named <cluster>-<name>. Each new revision copies
# the family's latest one and swaps only the image of its "app" container, so
# configuration registered since the last deploy (env, CPU, memory) rides along.
# Nothing is rolled out if the migrations fail. A service whose deployment
# circuit breaker rolled it back fails the script.
set -euo pipefail

image="$1"
services=(api worker beat)

ecs() { aws ecs --region "$AWS_REGION" "$@"; }

register() {
  local definition
  definition="$(
    ecs describe-task-definition --task-definition "$ECS_CLUSTER-$1" --query taskDefinition |
      jq --arg image "$image" '
        (.containerDefinitions[] | select(.name == "app") | .image) = $image
        | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
              .compatibilities, .registeredAt, .registeredBy, .deregisteredAt)'
  )"
  ecs register-task-definition --cli-input-json "$definition" \
    --query taskDefinition.taskDefinitionArn --output text
}

echo "== migrations"
migrate="$(register migrate)"
network="$(ecs describe-services --cluster "$ECS_CLUSTER" --services api \
  --query 'services[0].networkConfiguration' --output json)"
task="$(ecs run-task --cluster "$ECS_CLUSTER" --launch-type FARGATE \
  --task-definition "$migrate" --network-configuration "$network" \
  --query 'tasks[0].taskArn' --output text)"
ecs wait tasks-stopped --cluster "$ECS_CLUSTER" --tasks "$task"
aws logs get-log-events --region "$AWS_REGION" --log-group-name "/ecs/$ECS_CLUSTER" \
  --log-stream-name "$ECS_CLUSTER-migrate/app/${task##*/}" --start-from-head \
  --query 'events[].message' --output text | tr '\t' '\n' || true
exit_code="$(ecs describe-tasks --cluster "$ECS_CLUSTER" --tasks "$task" \
  --query 'tasks[0].containers[?name==`app`].exitCode | [0]' --output text)"
if [ "$exit_code" != 0 ]; then
  echo "migrations exited with $exit_code; nothing rolled out" >&2
  exit 1
fi

declare -A revision
for s in "${services[@]}"; do
  revision[$s]="$(register "$s")"
  ecs update-service --cluster "$ECS_CLUSTER" --service "$s" \
    --task-definition "${revision[$s]}" >/dev/null
  echo "== $s -> ${revision[$s]##*/}"
done

ecs wait services-stable --cluster "$ECS_CLUSTER" --services "${services[@]}"

failed=0
for s in "${services[@]}"; do
  running="$(ecs describe-services --cluster "$ECS_CLUSTER" --services "$s" \
    --query 'services[0].taskDefinition' --output text)"
  if [ "$running" != "${revision[$s]}" ]; then
    echo "$s rolled back to ${running##*/}" >&2
    failed=1
  fi
done
exit "$failed"
