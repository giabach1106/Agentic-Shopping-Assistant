#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./deploy/ec2/configure_and_deploy.sh \
    --domain-root kiroz.xyz \
    --acme-email you@example.com \
    --cognito-domain your-domain.auth.us-east-1.amazoncognito.com \
    --cognito-client-id your_client_id \
    --cognito-user-pool-id us-east-1_XXXXXXX \
    [--aws-region us-east-1] \
    [--cognito-region us-east-1] \
    [--app-subdomain app] \
    [--api-subdomain api] \
    [--mock-model true]
EOF
}

DOMAIN_ROOT=""
ACME_EMAIL=""
COGNITO_DOMAIN=""
COGNITO_CLIENT_ID=""
COGNITO_USER_POOL_ID=""
AWS_REGION="us-east-1"
COGNITO_REGION=""
APP_SUBDOMAIN="app"
API_SUBDOMAIN="api"
MOCK_MODEL="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain-root)
      DOMAIN_ROOT="$2"
      shift 2
      ;;
    --acme-email)
      ACME_EMAIL="$2"
      shift 2
      ;;
    --cognito-domain)
      COGNITO_DOMAIN="$2"
      shift 2
      ;;
    --cognito-client-id)
      COGNITO_CLIENT_ID="$2"
      shift 2
      ;;
    --cognito-user-pool-id)
      COGNITO_USER_POOL_ID="$2"
      shift 2
      ;;
    --aws-region)
      AWS_REGION="$2"
      shift 2
      ;;
    --cognito-region)
      COGNITO_REGION="$2"
      shift 2
      ;;
    --app-subdomain)
      APP_SUBDOMAIN="$2"
      shift 2
      ;;
    --api-subdomain)
      API_SUBDOMAIN="$2"
      shift 2
      ;;
    --mock-model)
      MOCK_MODEL="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${DOMAIN_ROOT}" || -z "${ACME_EMAIL}" || -z "${COGNITO_DOMAIN}" || -z "${COGNITO_CLIENT_ID}" || -z "${COGNITO_USER_POOL_ID}" ]]; then
  echo "Missing required arguments."
  usage
  exit 1
fi

if [[ -z "${COGNITO_REGION}" ]]; then
  COGNITO_REGION="${AWS_REGION}"
fi

if [[ ! -f "docker-compose.prod.yml" ]]; then
  echo "Run this script from repository root."
  exit 1
fi

APP_DOMAIN="${APP_SUBDOMAIN}.${DOMAIN_ROOT}"
API_DOMAIN="${API_SUBDOMAIN}.${DOMAIN_ROOT}"

mkdir -p backend/data deploy/ec2

cat > .env <<EOF
APP_NAME=Agentic Shopping Assistant API
AGENT_SQLITE_PATH=backend/data/agent_memory.sqlite3
AGENT_REDIS_URL=redis://localhost:6379/0
AGENT_REDIS_KEY_PREFIX=agentic-shopping-assistant:checkpoint
AGENT_CORS_ALLOW_ORIGINS=https://${APP_DOMAIN}
AGENT_REQUIRE_AUTH=true
AGENT_VERIFY_JWT_SIGNATURE=true

AWS_REGION=${AWS_REGION}
COGNITO_REGION=${COGNITO_REGION}
COGNITO_USER_POOL_ID=${COGNITO_USER_POOL_ID}
COGNITO_APP_CLIENT_ID=${COGNITO_CLIENT_ID}
NOVA_DEFAULT_MODEL_ID=us.amazon.nova-2-pro-v1:0
NOVA_FALLBACK_MODEL_ID=us.amazon.nova-2-lite-v1:0
MOCK_MODEL=${MOCK_MODEL}
RUNTIME_MODE=prod
UI_EXECUTOR_BACKEND=mock
STOP_BEFORE_PAY=true
ALLOW_DEV_FALLBACK_IN_PROD=false

MODEL_TIMEOUT_SECONDS=10
MODEL_LATENCY_THRESHOLD_SECONDS=6
MODEL_MAX_RETRIES=2
MAX_MODEL_CALLS_PER_SESSION=40
MAX_ESTIMATED_COST_PER_SESSION_USD=0.35
ESTIMATED_COST_PER_CALL_PRO_USD=0.01
ESTIMATED_COST_PER_CALL_LITE_USD=0.004

NEXT_PUBLIC_API_BASE_URL=https://${API_DOMAIN}
NEXT_PUBLIC_COGNITO_DOMAIN=${COGNITO_DOMAIN}
NEXT_PUBLIC_COGNITO_CLIENT_ID=${COGNITO_CLIENT_ID}
NEXT_PUBLIC_COGNITO_REDIRECT_URI=https://${APP_DOMAIN}
NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT=true
NEXT_PUBLIC_COGNITO_LOGOUT_URI=https://${APP_DOMAIN}
REQUIRE_COGNITO_ENV=true

CADDY_ACME_EMAIL=${ACME_EMAIL}
CADDY_APP_DOMAIN=${APP_DOMAIN}
CADDY_API_DOMAIN=${API_DOMAIN}
EOF

docker compose -f docker-compose.prod.yml up -d --build

echo "Deployment finished."
echo "Frontend URL: https://${APP_DOMAIN}"
echo "Backend URL:  https://${API_DOMAIN}/health"
