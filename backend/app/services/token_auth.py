from __future__ import annotations

import base64
import json
from functools import lru_cache
from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClient


def parse_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def decode_claims_without_verification(token: str) -> dict[str, Any]:
    payload = token.split(".")
    if len(payload) < 2:
        return {}
    encoded = payload[1] + "=" * (-len(payload[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
        loaded = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


@lru_cache(maxsize=16)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True)


def verify_cognito_token(
    token: str,
    *,
    region: str | None,
    user_pool_id: str | None,
    app_client_id: str | None,
) -> dict[str, Any]:
    region_value = (region or "").strip()
    pool_value = (user_pool_id or "").strip()
    if not region_value or not pool_value:
        raise ValueError(
            "Auth is enabled but Cognito settings are incomplete. "
            "Set COGNITO_REGION and COGNITO_USER_POOL_ID."
        )

    issuer = f"https://cognito-idp.{region_value}.amazonaws.com/{pool_value}"
    jwks_url = f"{issuer}/.well-known/jwks.json"
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except InvalidTokenError as exc:
        raise ValueError("Token verification failed.") from exc

    if not isinstance(claims, dict):
        raise ValueError("Token claims payload is invalid.")

    expected_client = (app_client_id or "").strip()
    if expected_client:
        token_use = str(claims.get("token_use") or "").strip().lower()
        if token_use == "id":
            if str(claims.get("aud") or "").strip() != expected_client:
                raise ValueError("Token audience does not match Cognito app client.")
        elif token_use == "access":
            if str(claims.get("client_id") or "").strip() != expected_client:
                raise ValueError("Token client_id does not match Cognito app client.")
        else:
            raise ValueError("Token use claim is invalid.")

    return claims
