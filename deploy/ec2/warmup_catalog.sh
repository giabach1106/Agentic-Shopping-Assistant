#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-1600}"

if [[ ! -f "docker-compose.prod.yml" ]]; then
  echo "Run this script from repository root."
  exit 1
fi

docker compose -f docker-compose.prod.yml exec -T backend \
  python scripts/warmup_supplements_catalog.py --target "${TARGET}"
