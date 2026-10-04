"""Sécurité HTTP : clé de signature, jetons signés (sessions, URL de fichiers), en-têtes, CSP à nonce."""

from __future__ import annotations

import ipaddress
import logging
import secrets
from functools import lru_cache
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from ..config import get_settings

log = logging.getLogger("pai.security")


@lru_cache(maxsize=1)
def secret_key() -> str:
    key = get_settings().secret_key
    if key:
        return key
    if get_settings().is_production:
        raise RuntimeError("SECRET_KEY manquante en production (python -m pai secret)")
    log.warning("SECRET_KEY absente : clé éphémère générée (sessions perdues au redémarrage).")
    return secrets.token_urlsafe(48)


def serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt=salt)


def sign(data: dict[str, Any], salt: str) -> str:
    return serializer(salt).dumps(data)


def unsign(token: str, salt: str, max_age: int) -> dict[str, Any] | None:
    try:
        value = serializer(salt).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return value if isinstance(value, dict) else None


CDN = "https://cdn.jsdelivr.net"


def csp(nonce: str | None = None) -> str:
    script = f"'self' {CDN}" + (f" 'nonce-{nonce}'" if nonce else "")
    return (f"default-src 'self'; script-src {script}; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:; connect-src 'self'; "
            "worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        headers = response.headers
        headers.setdefault("Content-Security-Policy", csp())
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if get_settings().is_production:
            headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path.startswith(("/v1/", "/login", "/auth/")):
            headers["Cache-Control"] = "no-store"
        return response


class CloudflareClientIp:
    """Accès « cloudflare » : l'IP du client est CF-Connecting-IP, que Cloudflare pose (et écrase) à chaque requête.
    X-Forwarded-For garde en tête ce que le client a envoyé : s'y fier laisserait contourner la limite de connexions.
    Inactif pour tout autre accès (Caddy remplace lui-même X-Forwarded-For), car l'en-tête y serait falsifiable."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and get_settings().access == "cloudflare":
            for name, value in scope.get("headers") or []:
                if name == b"cf-connecting-ip":
                    try:
                        ip = str(ipaddress.ip_address(value.decode("latin-1").strip()))
                    except ValueError:
                        break
                    scope = {**scope, "client": (ip, 0)}
                    break
        await self.app(scope, receive, send)
