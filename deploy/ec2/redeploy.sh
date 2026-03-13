#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f "docker-compose.prod.yml" ]]; then
  echo "Run this script from repository root."
  exit 1
fi

git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build

echo "Redeploy finished."
