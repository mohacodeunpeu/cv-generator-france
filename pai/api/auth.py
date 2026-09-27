"""Authentification : un seul utilisateur (argon2), session signée (cookie Secure/HttpOnly/SameSite),
CSRF (double soumission), limitation des tentatives de connexion, clés d'API hachées à droits limités.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from ..config import get_settings
from ..db.models import ApiKey, AuditLog, User, utcnow
from ..db.session import session_scope
from .security import sign, unsign

COOKIE = "pai_session"
CSRF_HEADER = "X-CSRF-Token"
SCOPES = {"read", "analyze", "generate", "feedback", "outcomes", "benchmark", "admin"}
_hasher = PasswordHasher()


# ── Utilisateur ─────────────────────────────────────────────────────────────
def create_user(username: str, password: str, must_change: bool = False) -> None:
    if len(password) < 12:
        raise ValueError("Mot de passe trop court (12 caractères minimum).")
    from ..db.session import init_db

    init_db()
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == username))
        if user is None:
            s.add(User(username=username, password_hash=_hasher.hash(password), must_change_password=must_change))
        else:
            user.password_hash, user.must_change_password = _hasher.hash(password), must_change
            user.sessions_valid_after = utcnow()  # réinitialisation : sessions existantes révoquées
        s.add(AuditLog(actor="cli", action="create_user", target=username))


def verify_password(username: str, password: str) -> User | None:
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == username))
        if user is None:
            _hasher.hash(password)  # temps constant approximatif
            return None
        try:
            _hasher.verify(user.password_hash, password)
        except VerificationError:
            return None
        if _hasher.check_needs_rehash(user.password_hash):
            user.password_hash = _hasher.hash(password)
        user.last_login_at = utcnow()
        s.add(AuditLog(actor=username, action="login", target=""))
        s.expunge(user)
        return user


def change_password(username: str, old: str, new: str) -> User | None:
    """Change le mot de passe et révoque toutes les sessions existantes. Renvoie l'utilisateur ou None."""
    if len(new) < 12 or new == old or verify_password(username, old) is None:
        return None
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == username))
        assert user is not None
        user.password_hash, user.must_change_password = _hasher.hash(new), False
        user.sessions_valid_after = utcnow()
        s.add(AuditLog(actor=username, action="change_password", target=""))
        s.flush()
        s.expunge(user)
        return user


def revoke_sessions(username: str) -> None:
    """Déconnexion : toutes les sessions émises jusqu'ici deviennent invalides (côté serveur)."""
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == username))
        if user is not None:
            user.sessions_valid_after = utcnow()
            s.add(AuditLog(actor=username, action="logout", target=""))


# ── Limitation des tentatives ─────────────────────────────────────────────────
@dataclass
class RateLimiter:
    limit: int
    window: float
    _hits: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


_limiter: RateLimiter | None = None


def login_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        cfg = get_settings()
        _limiter = RateLimiter(cfg.login_rate_limit, float(cfg.login_rate_window_seconds))
    return _limiter


def reset_login_limiter() -> None:
    global _limiter
    _limiter = None


# ── Sessions et CSRF ────────────────────────────────────────────────────────
def _epoch(dt: datetime) -> float:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def new_session_token(user: User) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    payload = {"u": user.username, "c": csrf, "m": bool(user.must_change_password), "t": time.time()}
    return sign(payload, "session"), csrf


def read_session(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    data = unsign(token, "session", get_settings().session_ttl_hours * 3600)
    if not data:
        return None
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == data.get("u")))
        if user is None:
            return None
        if user.sessions_valid_after is not None and float(data.get("t", 0)) <= _epoch(user.sessions_valid_after):
            return None
        data["m"] = bool(user.must_change_password)
    return data


# ── Clés d'API ──────────────────────────────────────────────────────────────
def _key_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_api_key(name: str, scopes: Iterable[str]) -> str:
    scopes = sorted(set(scopes))
    unknown = set(scopes) - SCOPES
    if unknown:
        raise ValueError(f"Droits inconnus : {sorted(unknown)}")
    raw = "pai_" + secrets.token_urlsafe(32)
    with session_scope() as s:
        s.add(ApiKey(name=name, prefix=raw[:10], key_hash=_key_hash(raw), scopes=list(scopes)))
        s.add(AuditLog(actor="admin", action="create_api_key", target=name, detail={"scopes": scopes}))
    return raw


def api_key_scopes(raw: str) -> tuple[str, list[str]] | None:
    with session_scope() as s:
        key = s.scalar(select(ApiKey).where(ApiKey.key_hash == _key_hash(raw), ApiKey.revoked_at.is_(None)))
        return (key.name, list(key.scopes)) if key else None


# ── Dépendances FastAPI ─────────────────────────────────────────────────────
@dataclass
class Principal:
    name: str
    kind: str          # session | api_key
    scopes: set[str]
    csrf: str = ""
    must_change: bool = False


def current_principal(request: Request) -> Principal | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        found = api_key_scopes(auth[7:].strip())
        if found:
            return Principal(name=f"api:{found[0]}", kind="api_key", scopes=set(found[1]))
        return None
    data = read_session(request)
    if data:
        return Principal(name=data["u"], kind="session", scopes=set(SCOPES), csrf=data["c"], must_change=bool(data.get("m")))
    return None


def require(*scopes: str):
    def dependency(request: Request) -> Principal:
        principal = current_principal(request)
        if principal is None:
            raise HTTPException(status_code=401, detail="Authentification requise")
        if principal.kind == "session" and request.method not in ("GET", "HEAD", "OPTIONS"):
            if not secrets.compare_digest(request.headers.get(CSRF_HEADER, ""), principal.csrf):
                raise HTTPException(status_code=403, detail="Jeton CSRF invalide")
        missing = set(scopes) - principal.scopes
        if missing:
            raise HTTPException(status_code=403, detail=f"Droits insuffisants : {sorted(missing)}")
        return principal

    return Depends(dependency)
