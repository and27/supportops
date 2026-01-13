import logging
import os

import jwt
from fastapi import HTTPException, Request
from jwt import InvalidTokenError, PyJWKClient

from .logging_utils import log_event

_jwks_client: PyJWKClient | None = None
_jwks_url: str | None = None


def auth_enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").lower() == "true"


def get_jwks_url() -> str | None:
    url = os.getenv("SUPABASE_JWKS_URL")
    if url:
        return url
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        return None
    return f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


def get_jwks_client(url: str) -> PyJWKClient:
    global _jwks_client, _jwks_url
    if _jwks_client and _jwks_url == url:
        return _jwks_client
    _jwks_client = PyJWKClient(url)
    _jwks_url = url
    return _jwks_client


def get_auth_user(request: Request) -> str | None:
    if not auth_enabled():
        return None
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="auth_required")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="auth_required")
    secret = os.getenv("SUPABASE_JWT_SECRET")
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")
    alg = header.get("alg")
    if not alg:
        raise HTTPException(status_code=401, detail="invalid_token")

    try:
        if secret and alg.startswith("HS"):
            payload = jwt.decode(
                token,
                secret,
                algorithms=[alg],
                options={"verify_aud": False},
            )
        else:
            jwks_url = get_jwks_url()
            if not jwks_url:
                raise HTTPException(status_code=500, detail="auth_not_configured")
            jwk_client = get_jwks_client(jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                options={"verify_aud": False},
            )
    except HTTPException:
        raise
    except Exception as exc:
        log_event(logging.ERROR, "auth_verify_failed", error=str(exc))
        raise HTTPException(status_code=401, detail="invalid_token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid_token")
    return user_id
