from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import io
import re
import zipfile

from pai.config import settings
from pai.profile import get_master_profile
from pai.analyzer import analyze_offer
from pai.strategy import build_strategy
from pai.pdf_renderer import render_cv_pdf, render_letter_pdf

app = FastAPI(title="PAI — Personal Application Intelligence", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value or "document")[:40]


def _build_offer(poste: str, entreprise: str, description: str, url: str = "") -> dict:
    return {
        "job_title": poste or "poste non fourni",
        "company": entreprise or "entreprise non fournie",
        "description": description or "",
        "offer_url": url or "",
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="pai_dashboard.html", context={"app_name": settings.app_name})


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/api/v1/profile")
async def profile():
    return get_master_profile()


@app.post("/api/v1/analyze-job")
async def analyze_job(payload: dict):
    offer_text = payload.get("offer_text") or payload.get("description") or ""
    job_title = payload.get("job_title") or ""
    company = payload.get("company") or ""
    offer_url = payload.get("offer_url") or ""
    analysis = analyze_offer(offer_text=offer_text, job_title=job_title, company=company, offer_url=offer_url)
    return analysis.model_dump()


@app.post("/api/v1/generate-strategy")
async def generate_strategy(payload: dict):
    profile = get_master_profile()
    analysis = analyze_offer(
        offer_text=payload.get("offer_text") or payload.get("description") or "",
        job_title=payload.get("job_title") or "",
        company=payload.get("company") or "",
        offer_url=payload.get("offer_url") or "",
    )
    strategy = build_strategy(profile, analysis)
    return strategy.model_dump()


@app.post("/api/v1/generate-cv")
async def generate_cv(payload: dict):
    profile = get_master_profile()
    analysis = analyze_offer(
        offer_text=payload.get("offer_text") or payload.get("description") or "",
        job_title=payload.get("job_title") or "",
        company=payload.get("company") or "",
        offer_url=payload.get("offer_url") or "",
    )
    strategy = build_strategy(profile, analysis)
    pdf_bytes = render_cv_pdf(profile=profile, offer=payload, strategy=strategy)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=PAI_CV.pdf"})


@app.post("/api/v1/generate-pack")
async def generate_pack(payload: dict):
    profile = get_master_profile()
    analysis = analyze_offer(
        offer_text=payload.get("offer_text") or payload.get("description") or "",
        job_title=payload.get("job_title") or "",
        company=payload.get("company") or "",
        offer_url=payload.get("offer_url") or "",
    )
    strategy = build_strategy(profile, analysis)
    cv_bytes = render_cv_pdf(profile=profile, offer=payload, strategy=strategy)
    letter_bytes = render_letter_pdf(profile=profile, offer=payload, strategy=strategy)
    slug = _slug(payload.get("company") or "pack")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"CV_{slug}.pdf", cv_bytes)
        zf.writestr(f"Lettre_{slug}.pdf", letter_bytes)
    buf.seek(0)
    return Response(content=buf.read(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="PAI_ApplicationPack_{slug}.zip"'})


@app.post("/generate")
async def legacy_generate(
    poste: str = Form(...),
    entreprise: str = Form(...),
    description: str = Form(default=""),
    contrat: str = Form(default="cdi"),
):
    offer = _build_offer(poste, entreprise, description)
    profile = get_master_profile()
    analysis = analyze_offer(offer_text=description, job_title=poste, company=entreprise)
    strategy = build_strategy(profile, analysis)
    cv_bytes = render_cv_pdf(profile=profile, offer=offer, strategy=strategy)
    letter_bytes = render_letter_pdf(profile=profile, offer=offer, strategy=strategy)
    slug = _slug(entreprise)
    slug_p = _slug(poste)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"CV_{slug}_{slug_p}.pdf", cv_bytes)
        zf.writestr(f"Lettre_{slug}_{slug_p}.pdf", letter_bytes)
    buf.seek(0)
    return Response(content=buf.read(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="PAI_{slug}.zip"'})


@app.post("/cv")
async def legacy_cv(
    poste: str = Form(...),
    entreprise: str = Form(...),
    description: str = Form(default=""),
    contrat: str = Form(default="cdi"),
):
    offer = _build_offer(poste, entreprise, description)
    profile = get_master_profile()
    analysis = analyze_offer(offer_text=description, job_title=poste, company=entreprise)
    strategy = build_strategy(profile, analysis)
    pdf_bytes = render_cv_pdf(profile=profile, offer=offer, strategy=strategy)
    slug = _slug(entreprise)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="CV_{slug}.pdf"'})


@app.post("/lettre")
async def legacy_letter(
    poste: str = Form(...),
    entreprise: str = Form(...),
    description: str = Form(default=""),
    contrat: str = Form(default="cdi"),
):
    offer = _build_offer(poste, entreprise, description)
    profile = get_master_profile()
    analysis = analyze_offer(offer_text=description, job_title=poste, company=entreprise)
    strategy = build_strategy(profile, analysis)
    pdf_bytes = render_letter_pdf(profile=profile, offer=offer, strategy=strategy)
    slug = _slug(entreprise)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="Lettre_{slug}.pdf"'})


@app.post("/best")
async def legacy_best(
    poste: str = Form(...),
    entreprise: str = Form(...),
    description: str = Form(default=""),
    contrat: str = Form(default="cdi"),
):
    offer = _build_offer(poste, entreprise, description)
    profile = get_master_profile()
    analysis = analyze_offer(offer_text=description, job_title=poste, company=entreprise)
    strategy = build_strategy(profile, analysis)
    cv_bytes = render_cv_pdf(profile=profile, offer=offer, strategy=strategy)
    letter_bytes = render_letter_pdf(profile=profile, offer=offer, strategy=strategy)
    slug = _slug(entreprise)
    slug_p = _slug(poste)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"CV_BEST_{slug}_{slug_p}.pdf", cv_bytes)
        zf.writestr(f"Lettre_BEST_{slug}_{slug_p}.pdf", letter_bytes)
    buf.seek(0)
    return Response(content=buf.read(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="PAI_Best_{slug}.zip"'})


@app.post("/chat")
async def chat(payload: dict):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY is not configured.")
    try:
        import anthropic
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Anthropic SDK unavailable: {exc}") from exc

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = (
        "Tu es le copilote PAI. Tu réponds en français, tu restes factuel, tu ne crées pas d'inventions. "
        "Tu aides à analyser une offre, à positionner le profile, à proposer un angle de CV et de lettre."
    )
    messages = payload.get("messages", [])
    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": msg.get("role", "user"), "content": msg.get("content", "")} for msg in messages],
        )
        text = response.content[0].text if response.content else ""
        return {"answer": text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
