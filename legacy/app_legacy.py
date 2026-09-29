"""
API France CV Generator — FastAPI.
POST /generate -> ZIP (CV.pdf + lettre.pdf)
POST /chat     -> JSON streaming (IA copilot)
GET  /         -> formulaire HTML
"""

import io
import os
import zipfile
import re
from typing import List

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import cv_gen_france
import cover_letter_france
import amine_profile as _p

app = FastAPI(title="Generateur CV France")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text)[:30]


def _build_offer(poste: str, entreprise: str, description: str) -> dict:
    return {"titre": poste, "entreprise": entreprise, "description": description}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/generate")
async def generate(
    poste:       str = Form(...),
    entreprise:  str = Form(...),
    description: str = Form(default=""),
    contrat:     str = Form(default="cdi"),
):
    offer = _build_offer(poste, entreprise, description)
    try:
        cv_bytes     = cv_gen_france.generate(offer, contrat)
        letter_text  = cover_letter_france.generate(offer, contrat)
        letter_bytes = cover_letter_france.to_pdf(letter_text, offer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    slug_e = _slug(entreprise)
    slug_p = _slug(poste)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"CV_{slug_e}_{slug_p}.pdf", cv_bytes)
        zf.writestr(f"Lettre_{slug_e}_{slug_p}.pdf", letter_bytes)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Candidature_{slug_e}.zip"'},
    )


@app.post("/cv")
async def cv_only(
    poste:       str = Form(...),
    entreprise:  str = Form(...),
    description: str = Form(default=""),
    contrat:     str = Form(default="cdi"),
):
    offer = _build_offer(poste, entreprise, description)
    try:
        cv_bytes = cv_gen_france.generate(offer, contrat)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    slug = _slug(entreprise)
    return Response(
        content=cv_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CV_{slug}.pdf"'},
    )


@app.post("/lettre")
async def lettre_only(
    poste:       str = Form(...),
    entreprise:  str = Form(...),
    description: str = Form(default=""),
    contrat:     str = Form(default="cdi"),
):
    offer = _build_offer(poste, entreprise, description)
    try:
        letter_text  = cover_letter_france.generate(offer, contrat)
        letter_bytes = cover_letter_france.to_pdf(letter_text, offer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    slug = _slug(entreprise)
    return Response(
        content=letter_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Lettre_{slug}.pdf"'},
    )


@app.post("/best")
async def best_application(
    poste:       str = Form(...),
    entreprise:  str = Form(...),
    description: str = Form(default=""),
    contrat:     str = Form(default="cdi"),
):
    """Hook agressif + plan 30j + phrase humaine + secteur adapte."""
    offer = _build_offer(poste, entreprise, description)
    try:
        cv_bytes     = cv_gen_france.generate(offer, contrat)
        letter_text  = cover_letter_france.generate_best(offer, contrat)
        letter_bytes = cover_letter_france.to_pdf(letter_text, offer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    slug_e = _slug(entreprise)
    slug_p = _slug(poste)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"CV_{slug_e}_{slug_p}.pdf", cv_bytes)
        zf.writestr(f"Lettre_BEST_{slug_e}_{slug_p}.pdf", letter_bytes)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="BestApplication_{slug_e}.zip"'},
    )


# ─── Chat IA copilot ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = f"""Tu es le copilot IA de {_p.DISPLAY_NAME}, un assistant ultra-personnel qui connait son profil par coeur.

PROFIL D'AMINE :
- Nom : {_p.FULL_NAME}
- Email : {_p.EMAIL} | Tel : {_p.PHONE} | Ville : {_p.CITY}
- Formation : MBA Manager de Business Unit — PSB Paris School of Business (2025-2026, soutenance juin 2026)
  Bachelor Bac+3 Developpement Commercial — PSB Paris (2022-2025, obtenu)
  Certification Negociation Commerciale — Negotiation Business School (2025)
- Experiences :
  * Business Developer & Recruitment Officer — Agence 113 / DEFI GROUPE (Sept. 2025 - Present)
    360 KEUR/mois de portefeuille B2B, 30+ leads qualifies/mois, 300+ candidats/session recrutement
    HubSpot CRM, LinkedIn Sales Navigator, coordination POEI France Travail
  * Project Manager / Website Builder — Wix International, Lisbonne (2025)
    5+ sites clients livres en autonomie, +20% taux de clic moyen
  * Sales Advisor Premium — Printemps Haussmann (2024)
    +10% vs objectif mensuel, clientele internationale haut de gamme
  * Community Manager — GROW 360 (2023-2024)
    +35% engagement Instagram/LinkedIn en 6 mois
- Langues : Francais natif, Arabe natif, Anglais courant, Espagnol intermediaire, Chinois notions
- Outils : HubSpot CRM, Sales Navigator, Excel avance, Canva, Notion, Wix, Google Suite

TON ROLE :
Tu aides Amine a optimiser ses candidatures. Tu peux :
- Analyser une offre d'emploi et dire si elle lui correspond
- Suggerer comment personnaliser la lettre ou le CV
- Expliquer pourquoi tel poste est bien ou mal adapte a son profil
- Donner des conseils pour l'entretien selon le secteur
- Repondre a toutes les questions sur son profil, ses forces, ses experiences

STYLE : Francais, direct, professionnel mais humain. Pas de bullet points excessifs. Parle comme un conseiller de carriere qui connait bien la personne. Repenses concises (max 3-4 phrases sauf si on te demande plus). Si l'utilisateur ecrit en anglais, reponds en anglais."""


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    offer_context: str = ""   # titre + entreprise optionnel


@app.post("/chat")
async def chat(req: ChatRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Cle API non configuree. Ajoute ANTHROPIC_API_KEY dans ton environnement."
        )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erreur SDK: {e}")

    system = _SYSTEM_PROMPT
    if req.offer_context:
        system += f"\n\nCONTEXTE ACTUEL : L'utilisateur est en train de postuler pour : {req.offer_context}"

    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    async def stream_response():
        try:
            with client.messages.stream(
                model="claude-haiku-4-5",
                max_tokens=600,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"\n[Erreur: {e}]"

    return StreamingResponse(stream_response(), media_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
