#!/bin/sh
set -eu

node <<'NODE'
const fs = require("fs");
const path = "/app/public/runtime-config.js";
const keys = [
  "NEXT_PUBLIC_API_BASE_URL",
  "NEXT_PUBLIC_COGNITO_DOMAIN",
  "NEXT_PUBLIC_COGNITO_CLIENT_ID",
  "NEXT_PUBLIC_COGNITO_REDIRECT_URI",
  "NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT",
  "NEXT_PUBLIC_COGNITO_LOGOUT_URI",
];

const config = {};
for (const key of keys) {
  if (Object.prototype.hasOwnProperty.call(process.env, key)) {
    config[key] = String(process.env[key] ?? "");
  }
}

const payload = `window.__AGENTCART_RUNTIME_CONFIG__ = ${JSON.stringify(config)};\n`;
fs.writeFileSync(path, payload, "utf8");
NODE

exec "$@"
