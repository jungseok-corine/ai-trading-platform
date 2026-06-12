#!/usr/bin/env bash
# 이미 실행 중인 postgres 컨테이너에 테스트 전용 DB(trading_platform_test)를 생성한다.
# dev DB(trading_platform)의 데이터는 건드리지 않는다.
#
# 사용법:
#   ./scripts/create-test-db.sh
#
# 새로 docker compose up을 하는 경우에는 docker/initdb/01-create-test-db.sh가
# 자동으로 실행되므로 이 스크립트는 필요 없다. 기존에 띄워둔(데이터 볼륨이 이미 있는)
# 컨테이너에 대해서만 사용한다.
set -euo pipefail

CONTAINER_NAME="${POSTGRES_CONTAINER:-backend-db-1}"
DB_USER="${POSTGRES_USER:-trading}"
TEST_DB_NAME="${TEST_DB_NAME:-trading_platform_test}"

if docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -lqt | cut -d'|' -f1 | grep -qw "$TEST_DB_NAME"; then
  echo "Database '$TEST_DB_NAME' already exists. Nothing to do."
else
  echo "Creating database '$TEST_DB_NAME' on container '$CONTAINER_NAME'..."
  docker exec "$CONTAINER_NAME" createdb -U "$DB_USER" "$TEST_DB_NAME"
  echo "Done."
fi
