#!/bin/sh
# postgres 컨테이너를 처음 초기화할 때(데이터 볼륨이 비어있을 때)만 실행된다.
# dev DB(${POSTGRES_DB})는 그대로 두고, 테스트 전용 DB를 추가로 생성한다.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE trading_platform_test;
EOSQL
