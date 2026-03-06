import os
import time
import requests
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException, status
from jose import jwt
from jose.exceptions import JWTError

# Simple in-memory JWKS cache (good enough for dev/hackathon)
_JWKS_CACHE: Dict[str, Any] = {"keys": None, "expires_at": 0}


def _get_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def _issuer() -> str:
    region = _get_env("COGNITO_REGION")
    user_pool_id = _get_env("COGNITO_USER_POOL_ID")
    return f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"


def _jwks_url() -> str:
    return f"{_issuer()}/.well-known/jwks.json"


def _get_jwks() -> Dict[str, Any]:
    now = int(time.time())
    if _JWKS_CACHE["keys"] and now < _JWKS_CACHE["expires_at"]:
        return _JWKS_CACHE["keys"]

    resp = requests.get(_jwks_url(), timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch JWKS: {resp.status_code} {resp.text}")

    data = resp.json()
    _JWKS_CACHE["keys"] = data
    _JWKS_CACHE["expires_at"] = now + 60 * 60  # cache 1 hour
    return data


def verify_cognito_jwt(token: str) -> Dict[str, Any]:
    """
    Verifies a Cognito JWT (use id_token for app identity).
    Returns decoded claims.
    """
    app_client_id = _get_env("COGNITO_APP_CLIENT_ID")
    issuer = _issuer()
    jwks = _get_jwks()

    try:
        headers = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid JWT header")

    kid = headers.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="JWT missing kid")

    key: Optional[Dict[str, Any]] = None
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            key = k
            break

    if not key:
        raise HTTPException(status_code=401, detail="Public key not found for token")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=app_client_id,
            issuer=issuer,
            options={"verify_at_hash": False},
        )
        return claims
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"JWT verification failed: {str(e)}")


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    FastAPI dependency. Expects: Authorization: Bearer <id_token>
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization must be Bearer token",
        )

    token = parts[1]
    claims = verify_cognito_jwt(token)

    if "sub" not in claims:
        raise HTTPException(status_code=401, detail="JWT missing sub claim")

    return claims