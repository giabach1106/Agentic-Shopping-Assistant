#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-supplement}"
TARGET="${2:-1600}"

if [[ ! -f "docker-compose.prod.yml" ]]; then
  echo "Run this script from repository root."
  exit 1
fi

docker compose -f docker-compose.prod.yml exec -T backend \
  sh -lc "PYTHONPATH=/app python scripts/warmup_domain_corpus.py --domain ${DOMAIN} --target ${TARGET}"
