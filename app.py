"""
API France CV Generator — FastAPI.
POST /generate -> ZIP (CV.pdf + lettre.pdf)
GET  /         -> formulaire HTML
"""

import io
import zipfile
import re

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

import cv_gen_france
import cover_letter_france

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
