"""Authentication for the public API.

Identity lives in the Next.js app (Auth.js). After sign-in it mints a short-lived HS256 JWT
for the browser to present as ``Authorization: Bearer <token>``; this module verifies it.

Three access levels:

* anonymous  — no header; read-only endpoints only
* user       — valid token; personal workspace endpoints
* admin      — valid token whose email is in ``SMP_ADMIN_EMAILS`` (or the legacy
               ``X-API-Key`` machine credential); run trigger, universe, desk defaults

When neither ``SMP_AUTH_JWT_SECRET`` nor ``SMP_API_KEY`` is configured (local development),
mutations stay open and a warning is logged at startup. Production settings refuse to boot
in that state.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Literal

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

TOKEN_AUDIENCE = "desk-api"
TOKEN_ISSUER = "desk-web"
_ALGORITHMS = ["HS256"]

Role = Literal["user", "admin"]


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: str
    email: str | None
    name: str | None
    image: str | None
    role: Role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


API_KEY_USER = AuthUser(id="api-key", email=None, name="API key", image=None, role="admin")


def role_for(email: str | None, settings: Settings) -> Role:
    """Admin status is decided here, from the server-side allowlist — never from the token."""
    if email and email.strip().lower() in settings.admin_email_set:
        return "admin"
    return "user"


def decode_api_token(token: str, settings: Settings | None = None) -> AuthUser:
    """Verify a token minted by the web app. Raises ``jwt.PyJWTError`` on any problem."""
    settings = settings or get_settings()
    if not settings.auth_jwt_secret:
        raise jwt.InvalidTokenError("Token auth is not configured")
    claims = jwt.decode(
        token,
        settings.auth_jwt_secret,
        algorithms=_ALGORITHMS,
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
        options={"require": ["exp", "iat", "sub"]},
        leeway=30,
    )
    sub = str(claims["sub"]).strip()
    if not sub or len(sub) > 64:
        raise jwt.InvalidTokenError("Invalid subject")
    email = claims.get("email")
    email = str(email).strip().lower()[:320] if email else None
    name = claims.get("name")
    image = claims.get("picture") or claims.get("image")
    return AuthUser(
        id=sub,
        email=email,
        name=str(name)[:200] if name else None,
        image=str(image)[:2000] if image else None,
        role=role_for(email, settings),
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def _api_key_valid(candidate: str | None, settings: Settings) -> bool:
    expected = settings.api_key
    if not expected or not candidate:
        return False
    return secrets.compare_digest(candidate.encode(), expected.encode())


# ------------------------------------------------------------------- dependencies


def optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthUser | None:
    """Resolve the caller if a bearer token is present; anonymous callers get ``None``.

    A *present but invalid* token is rejected with 401 rather than silently downgraded, so a
    signed-in user with an expired token sees a clear error instead of anonymous data.
    """
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("Malformed Authorization header")
    settings = get_settings()
    try:
        user = decode_api_token(token.strip(), settings)
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Session token expired") from exc
    except jwt.PyJWTError as exc:
        logger.info("Rejected bearer token: %s", exc)
        raise _unauthorized("Invalid session token") from exc
    request.state.user = user
    return user


def require_user(user: AuthUser | None = Depends(optional_user)) -> AuthUser:
    if user is None:
        raise _unauthorized("Sign in to use this feature")
    return user


def require_admin(
    user: AuthUser | None = Depends(optional_user),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthUser:
    """Admin-only mutations. Accepts an admin bearer token or the machine ``X-API-Key``."""
    settings = get_settings()
    if _api_key_valid(x_api_key, settings):
        return API_KEY_USER
    if user is not None:
        if user.is_admin:
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    if not settings.auth_enabled and not settings.requires_api_key:
        # Local development with no auth configured at all: keep the desk usable.
        return API_KEY_USER
    if x_api_key is not None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid API key",
            headers={"WWW-Authenticate": "API-Key"},
        )
    raise _unauthorized("Admin sign-in required")


def rate_limit_key(request: Request) -> str:
    """Rate-limit signed-in users per account and everyone else per client IP."""
    user = getattr(request.state, "user", None)
    if isinstance(user, AuthUser):
        return f"user:{user.id}"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"
