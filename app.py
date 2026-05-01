"""
API France CV Generator — FastAPI.
POST /generate -> ZIP (CV.pdf + lettre.pdf)
GET  /         -> formulaire HTML
"""

import io
import zipfile
import re
from datetime import datetime

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

import cv_gen_france
import cover_letter_france

app = FastAPI(title="Generateur CV France")
templates = Jinja2Templates(directory="templates")


def _slug(text: str) -> str:
    """Transforme un texte en slug safe pour nom de fichier."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text)[:30]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate")
async def generate(
    poste:       str = Form(...),
    entreprise:  str = Form(...),
    description: str = Form(default=""),
    contrat:     str = Form(default="cdi"),
):
    offer = {
        "titre":       poste,
        "entreprise":  entreprise,
        "description": description,
    }

    # Generation CV
    cv_bytes = cv_gen_france.generate(offer, contrat)

    # Generation lettre
    letter_text = cover_letter_france.generate(offer, contrat)
    letter_bytes = cover_letter_france.to_pdf(letter_text, offer)

    # ZIP
    slug_e = _slug(entreprise)
    slug_p = _slug(poste)
    cv_filename     = f"CV_{slug_e}_{slug_p}.pdf"
    letter_filename = f"Lettre_{slug_e}_{slug_p}.pdf"
    zip_filename    = f"Candidature_{slug_e}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(cv_filename, cv_bytes)
        zf.writestr(letter_filename, letter_bytes)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"'
        },
    )


@app.post("/cv")
async def cv_only(
    poste:       str = Form(...),
    entreprise:  str = Form(...),
    description: str = Form(default=""),
    contrat:     str = Form(default="cdi"),
):
    offer = {"titre": poste, "entreprise": entreprise, "description": description}
    cv_bytes = cv_gen_france.generate(offer, contrat)
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
    offer = {"titre": poste, "entreprise": entreprise, "description": description}
    letter_text  = cover_letter_france.generate(offer, contrat)
    letter_bytes = cover_letter_france.to_pdf(letter_text, offer)
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
    """
    Mode conversion maximale :
    - CV avec suffixe sectoriel si detecte
    - Lettre : hook le plus agressif + plan 30 jours + phrase humaine
    """
    offer = {
        "titre":       poste,
        "entreprise":  entreprise,
        "description": description,
    }

    cv_bytes     = cv_gen_france.generate(offer, contrat)
    letter_text  = cover_letter_france.generate_best(offer, contrat)
    letter_bytes = cover_letter_france.to_pdf(letter_text, offer)

    slug_e       = _slug(entreprise)
    slug_p       = _slug(poste)
    zip_filename = f"BestApplication_{slug_e}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"CV_{slug_e}_{slug_p}.pdf", cv_bytes)
        zf.writestr(f"Lettre_BEST_{slug_e}_{slug_p}.pdf", letter_bytes)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
