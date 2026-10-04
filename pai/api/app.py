"""Application FastAPI : interface (PAI Studio en mode serveur), connexion, API /v1, routes historiques."""

from __future__ import annotations

import logging
import re
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .. import ENGINE_VERSION, obs, paths
from ..config import get_settings
from ..db.models import StoredFile
from ..db.repo import ensure_profile_doc
from ..db.session import init_db, session_scope
from . import jobs
from .auth import (COOKIE, CSRF_HEADER, Principal, change_password, current_principal, login_limiter, new_session_token,
                   require, revoke_sessions, verify_password)
from .security import CloudflareClientIp, SecurityHeaders, csp, unsign
from .public import router as public_router
from .v1 import OfferIn, router as v1_router, run_pack_job

templates = Jinja2Templates(directory=str(paths.TEMPLATES_DIR))
STUDIO_SERVER = paths.WEB_DIR / "dist" / "pai_studio_server.html"
LOGIN_COOKIE = "pai_login"


class RedactFileTokens(logging.Filter):
    """A10 : le jeton d'un lien de fichier signé n'apparaît jamais dans le journal d'accès."""

    PATTERN = re.compile(r"(/v1/files/)[^\s?\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self.PATTERN.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = self.PATTERN.sub(r"\1***", record.msg)
        return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactFileTokens) for f in access.filters):
        access.addFilter(RedactFileTokens())
    init_db()
    with session_scope() as s:
        ensure_profile_doc(s)
    jobs.start_inline_worker()
    yield
    jobs.stop_inline_worker()


def _set_session(resp: Response, token: str) -> None:
    cfg = get_settings()
    resp.set_cookie(COOKIE, token, max_age=cfg.session_ttl_hours * 3600, httponly=True, secure=cfg.cookie_secure,
                    samesite="strict", path="/")


def _with_nonce(html: str, nonce: str) -> str:
    """Ajoute le nonce CSP à chaque script en ligne (les scripts du CDN autorisé n'en ont pas besoin)."""
    return re.sub(r"<script(?![^>]*\bsrc=)", f'<script nonce="{nonce}"', html)


def _page(request: Request, mode: str, csrf: str, error: str = "", status: int = 200) -> Response:
    return templates.TemplateResponse(request=request, name="login.html.j2", status_code=status,
                                      context={"csrf": csrf, "error": error, "mode": mode})


def create_app() -> FastAPI:
    app = FastAPI(title="PAI — Personal Application Intelligence", version=ENGINE_VERSION, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    app.add_middleware(CloudflareClientIp)
    app.include_router(v1_router)
    app.include_router(public_router)

    @app.middleware("http")
    async def request_ids(request: Request, call_next):  # noqa: ANN001, ANN202
        """request_id par requête (en-tête X-Request-ID repris s'il est sûr), propagé aux jobs et aux appels IA ;
        une ligne JSON par requête : méthode, route (jamais l'URL brute ni la query string), statut, durée."""
        rid = obs.new_request_id(request.headers.get("x-request-id"))
        token = obs.request_id_var.set(rid)
        start, status = time.monotonic(), 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", "") or "(hors route)"
            if path not in ("/health", "/api/health"):
                obs.event("request", method=request.method, path=path, status=status,
                          duration_ms=int((time.monotonic() - start) * 1000))
            obs.request_id_var.reset(token)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "engine": ENGINE_VERSION}

    # ── Connexion ───────────────────────────────────────────────────────────
    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request) -> Response:
        token = secrets.token_urlsafe(16)
        resp = _page(request, "login", token)
        resp.set_cookie(LOGIN_COOKIE, token, max_age=900, httponly=True, secure=get_settings().cookie_secure, samesite="strict")
        return resp

    @app.post("/login", include_in_schema=False)
    def login(request: Request, username: str = Form(..., max_length=80), password: str = Form(..., max_length=512),
              csrf: str = Form(...)) -> Response:
        if not secrets.compare_digest(csrf, request.cookies.get(LOGIN_COOKIE, "")):
            raise HTTPException(status_code=403, detail="Formulaire expiré : rechargez la page")
        ip = request.client.host if request.client else "?"
        key = f"{ip}:{username.strip().lower()}"
        if not login_limiter().hit(key):
            return _page(request, "login", csrf, "Trop de tentatives : réessayez dans quelques minutes.", 429)
        user = verify_password(username.strip(), password)
        if user is None:
            return _page(request, "login", csrf, "Identifiant ou mot de passe incorrect.", 401)
        login_limiter().reset(key)
        token, _ = new_session_token(user)
        resp = RedirectResponse("/change-password" if user.must_change_password else "/", status_code=303)
        _set_session(resp, token)
        resp.delete_cookie(LOGIN_COOKIE)
        return resp

    @app.post("/logout", include_in_schema=False)
    async def logout(request: Request) -> Response:
        principal = current_principal(request)
        form = await request.form()
        sent = request.headers.get(CSRF_HEADER) or str(form.get("csrf", ""))
        if principal is not None and principal.kind == "session" and secrets.compare_digest(sent, principal.csrf):
            revoke_sessions(principal.name)
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/change-password", response_class=HTMLResponse, include_in_schema=False)
    def change_page(request: Request) -> Response:
        principal = current_principal(request)
        if principal is None or principal.kind != "session":
            return RedirectResponse("/login", status_code=303)
        return _page(request, "change", principal.csrf)

    @app.post("/change-password", include_in_schema=False)
    def change(request: Request, old: str = Form(..., max_length=512), new: str = Form(..., max_length=512),
               csrf: str = Form(...)) -> Response:
        principal = current_principal(request)
        if principal is None or principal.kind != "session" or not secrets.compare_digest(csrf, principal.csrf):
            raise HTTPException(status_code=403, detail="Session invalide")
        user = change_password(principal.name, old, new)
        if user is None:
            return _page(request, "change", csrf, "Ancien mot de passe incorrect, ou nouveau trop court (12 caractères) ou identique.", 400)
        token, _ = new_session_token(user)
        resp = RedirectResponse("/", status_code=303)
        _set_session(resp, token)
        return resp

    # ── Interface ───────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def studio(request: Request) -> Response:
        principal = current_principal(request)
        if principal is None or principal.kind != "session":
            return RedirectResponse("/login", status_code=303)
        if principal.must_change:
            return RedirectResponse("/change-password", status_code=303)
        if not STUDIO_SERVER.exists():
            return HTMLResponse("<p>Interface non construite : lancez <code>python -m pai build-studio --server</code>.</p>", status_code=503)
        nonce = secrets.token_urlsafe(16)
        html = _with_nonce(STUDIO_SERVER.read_text(encoding="utf-8"), nonce)
        html = html.replace("<head>", f'<head><meta name="pai-csrf" content="{principal.csrf}">', 1)
        return HTMLResponse(html, headers={"Content-Security-Policy": csp(nonce), "Cache-Control": "no-store"})

    @app.get("/openapi.json", include_in_schema=False)
    def openapi(_: Principal = require("read")) -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False)
    def docs(_: Principal = require("read")) -> HTMLResponse:
        nonce = secrets.token_urlsafe(16)
        page = get_swagger_ui_html(openapi_url="/openapi.json", title="PAI API", swagger_favicon_url="data:,")
        return HTMLResponse(_with_nonce(page.body.decode("utf-8"), nonce), headers={"Content-Security-Policy": csp(nonce)})

    # ── Routes historiques (compatibilité) : authentifiées, désormais 100 % factuelles ──
    def _legacy(poste: str, entreprise: str, description: str) -> dict:
        text = description if len(description.strip()) >= 80 else f"{poste} — {entreprise}\n\n{description}".strip()
        if len(text) < 80:
            raise HTTPException(status_code=422, detail="Collez le texte complet de l'offre (80 caractères minimum).")
        return run_pack_job(OfferIn(offer_text=text, role=poste, company=entreprise).model_dump(by_alias=True))

    def _file(url: str | None) -> bytes:
        data = unsign(url.rsplit("/", 1)[-1], "file", 3600) if url else None
        with session_scope() as s:
            row = s.get(StoredFile, data["f"]) if data else None
            if row is None:
                raise HTTPException(status_code=500, detail="Document non produit")
            return row.data

    def _legacy_response(r: dict, key: str, media: str, filename: str) -> Response:
        return Response(_file(r["application_pack"][key]), media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-PAI-Generation": r["generation_id"]})

    @app.post("/cv", include_in_schema=False)
    def legacy_cv(poste: str = Form(...), entreprise: str = Form(...), description: str = Form(""), contrat: str = Form("cdi"),
                  _: Principal = require("generate")) -> Response:
        return _legacy_response(_legacy(poste, entreprise, description), "cv_pdf", "application/pdf", "CV.pdf")

    @app.post("/lettre", include_in_schema=False)
    def legacy_letter(poste: str = Form(...), entreprise: str = Form(...), description: str = Form(""), contrat: str = Form("cdi"),
                      _: Principal = require("generate")) -> Response:
        return _legacy_response(_legacy(poste, entreprise, description), "letter_pdf", "application/pdf", "Lettre.pdf")

    @app.post("/generate", include_in_schema=False)
    @app.post("/best", include_in_schema=False)
    def legacy_pack(poste: str = Form(...), entreprise: str = Form(...), description: str = Form(""), contrat: str = Form("cdi"),
                    _: Principal = require("generate")) -> Response:
        return _legacy_response(_legacy(poste, entreprise, description), "zip", "application/zip", "Candidature.zip")

    return app
