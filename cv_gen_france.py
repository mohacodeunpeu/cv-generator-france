"""
Generateur de CV France — 5 modes intelligents.
Adapte automatiquement selon job_title + description.
1 page A4 garantie.
"""

import io
import os
import re
import tempfile

from fpdf import FPDF
import amine_profile as _p
from modes import detect_mode, get_mode_cv, detect_company_type, ats_inject

# ─── Profil (source : amine_profile.py) ──────────────────────────────────────

PROFILE = {
    "name":        _p.FULL_NAME,
    "phone":       _p.PHONE,
    "email":       _p.EMAIL,
    "city":        _p.CITY,
    "qr_url":      _p.LINKEDIN_URL,
    "video_cv_url": "",
}


# ─── Experiences ──────────────────────────────────────────────────────────────

EXPERIENCES = [
    {
        "id":      "defi",
        "title":   "Business Developer & Recruitment Officer",
        "company": "Agence 113 - DEFI GROUPE",
        "city":    "Paris",
        "period":  "Sept. 2025 - Present",
        "bullets": {
            "default": [
                "Pilotage portefeuille B2B 360 KEUR/mois : 30+ leads qualifies/mois.",
                "Suivi CRM HubSpot (120+ comptes) : taux de relance maintenu a 85%.",
                "Events recrutement : 300+ candidats qualifies par session.",
            ],
            "commerce": [
                "Developpement portefeuille B2B 360 KEUR/mois : cycle complet autonome.",
                "Negociation directe decideurs via HubSpot : 3 partenariats LT/trimestre.",
                "Pipeline structure : 30+ opportunites qualifiees suivies en temps reel.",
            ],
            "finance": [
                "Suivi budgetaire 360 KEUR/mois : analyse marges et ecarts hebdomadaires.",
                "Reporting mensuel direction via dashboards Excel (TCD, formules avancees).",
                "Analyse rentabilite client : 3 leviers d'optimisation identifies et appliques.",
            ],
            "hr": [
                "Events recrutement : 300+ candidats qualifies et accueillis par session.",
                "Coordination POEI France Travail : 15 integrations geries en parallele.",
                "Pilotage KPIs RH : taux de placement et reporting mensuel management.",
            ],
        },
    },
    {
        "id":      "wix",
        "title":   "Project Manager / Website Builder",
        "company": "Wix - International",
        "city":    "Lisbonne, Portugal",
        "period":  "2025",
        "bullets": {
            "default": [
                "Livraison 5+ sites clients intl en autonomie : brief, design, mise en ligne.",
                "Optimisation UX/conversion : +20% taux de clic moyen sur landing pages.",
            ],
            "finance": [
                "Gestion de projet A a Z : budget, planning, livraison sans retard.",
                "Optimisation conversion via analytics : +20% taux de clic landing pages.",
            ],
        },
    },
    {
        "id":      "printemps",
        "title":   "Sales Advisor - Premium Retail",
        "company": "Printemps Haussmann",
        "city":    "Paris",
        "period":  "2024",
        "bullets": {
            "default": [
                "Depassement objectifs de vente (+10% vs. cible mensuelle).",
                "Fidelisation clientele internationale premium : taux de retour eleve.",
                "Accompagnement haut de gamme : conseil produit multi-cultures (FR/EN/AR).",
            ],
        },
    },
    {
        "id":      "grow",
        "title":   "Community Manager",
        "company": "GROW 360",
        "city":    "Paris",
        "period":  "2023 - 2024",
        "bullets": {
            "default": [
                "Strategie editoriale : +35% engagement (Instagram, LinkedIn) en 6 mois.",
                "Planification 10+ posts/semaine (3 formats), 0 retard de publication.",
            ],
        },
    },
]


# ─── Formation ────────────────────────────────────────────────────────────────

EDUCATION = [
    ("MBA - Manager de Business Unit",
     "PSB Paris School of Business",
     "Paris  2025-2026",
     "Soutenance juin 2026"),
    ("Bachelor Bac+3 - Developpement Commercial",
     "PSB Paris School of Business",
     "Paris  2022-2025",
     "Obtenu"),
    ("Certification Negociation Commerciale",
     "Negotiation Business School (en ligne)",
     "2025",
     "Certifie"),
    ("Habilitation SST - Sauveteur Secouriste Travail",
     "Croix-Rouge Francaise",
     "Paris  2024",
     ""),
]

LANGUAGES = [
    ("Francais",  "Natif"),
    ("Arabe",     "Natif"),
    ("Anglais",   "Courant"),
    ("Espagnol",  "Intermediaire"),
    ("Chinois",   "Notions"),
]

_DISPO_LINE = {
    "cdi":        "Disponibilite : CDI, juin 2026  |  Mobilite : Permis B, remote OK",
    "alternance": "Disponibilite : Alternance (2 ans, sept. 2026)  |  Rythme : 3j/2j ou 4j/1j",
    "stage":      "Disponibilite : Stage (4-6 mois, juil. 2026)  |  Mobilite : Paris + IDF",
}

# Summaries mode urgence (jobs simples / terrain)
_SUMMARY_URGENT = {
    "luxe": (
        "Conseiller de vente experience en environnement premium (Printemps Haussmann). "
        "A l'aise avec une clientele internationale exigeante. "
        "Disponible immediatement, serieux et presente."
    ),
    "commercial": (
        "Profil commercial terrain avec experience B2B et retail premium. "
        "Habitude aux objectifs, disponible immediatement. "
        "Multilingue, a l'aise avec toutes clienteles."
    ),
    "default": (
        "Profil operationnel avec experience en vente et relation client. "
        "Disponible immediatement. Serieux, ponctuel, oriente terrain. "
        "Multilingue (FR/AR/EN), s'adapte rapidement."
    ),
}


def _urgent_summary(titre: str) -> str:
    t = titre.lower()
    if any(k in t for k in _p.LUXE_KEYWORDS):
        return _SUMMARY_URGENT["luxe"]
    if any(k in t for k in _p.COMMERCIAL_KEYWORDS):
        return _SUMMARY_URGENT["commercial"]
    return _SUMMARY_URGENT["default"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe(text: str) -> str:
    if not text:
        return ""
    for src, dst in {
        "—":"-","–":"-","'":"'","'":"'","'":"'",""":'"',""":'"',
        "…":"...","•":"-","→":"->","€":"EUR","œ":"oe","Œ":"OE","æ":"ae",
    }.items():
        text = text.replace(src, dst)
    return text


def _extract_tools(description: str) -> list:
    known = ["salesforce","sap","power bi","tableau","jira","confluence","hubspot",
             "notion","asana","monday","figma","adobe","google analytics","looker","sql","python"]
    d = (description or "").lower()
    return [t for t in known if t in d]


def _make_qr_png(url: str) -> str:
    try:
        import qrcode
    except ImportError:
        return ""
    qr = qrcode.QRCode(version=1, box_size=10, border=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="white", back_color=(15, 35, 85))
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


# ─── PDF class ────────────────────────────────────────────────────────────────

class _CVPdf(FPDF):
    NAVY  = (15, 35, 85)
    GOLD  = (193, 154, 60)
    GREY  = (60, 60, 65)
    DARK_X = (90, 90, 95)

    tagline = ""

    def header(self):
        self.set_fill_color(*self.NAVY)
        self.rect(0, 0, 210, 29, style="F")
        self.set_xy(14, 5.5)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(255, 255, 255)
        self.cell(0, 6.5, _safe(PROFILE["name"]), ln=1)
        self.set_x(14)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*self.GOLD)
        self.cell(0, 4.5, _safe(self.tagline), ln=1)
        self.set_x(14)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(210, 220, 235)
        contact = f"{PROFILE['phone']}  |  {PROFILE['email']}  |  {PROFILE['city']}"
        self.cell(0, 4.5, _safe(contact), ln=1)
        self.set_fill_color(*self.GOLD)
        self.rect(0, 29, 210, 0.8, style="F")
        self.set_y(32)

    def footer(self):
        self.set_y(-10)
        self.set_fill_color(*self.GOLD)
        self.rect(0, 285, 210, 0.4, style="F")
        self.set_y(-8.5)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 155)
        self.cell(0, 3.5,
                  _safe(f"{PROFILE['name']}  |  {PROFILE['phone']}  |  {PROFILE['email']}"),
                  align="C")

    def section(self, title: str):
        self.ln(0.8)
        self.set_x(14)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self.NAVY)
        self.cell(0, 5.5, _safe(title.upper()), ln=1)
        x, y = 14, self.get_y()
        self.set_fill_color(*self.GOLD)
        self.rect(x, y - 0.4, 20, 0.6, style="F")
        self.set_y(y + 0.4)

    def paragraph(self, text: str, font_size: float = 8.8):
        self.set_x(14)
        self.set_font("Helvetica", "", font_size)
        self.set_text_color(*self.GREY)
        self.multi_cell(182, 4.0, _safe(text))
        self.ln(0.3)

    def experience_item(self, title: str, period: str, sub: str, bullets: list):
        self.set_x(14)
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*self.NAVY)
        self.cell(120, 4.5, _safe(title), ln=0)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*self.DARK_X)
        self.cell(0, 4.5, _safe(period), align="R", ln=1)
        self.set_x(14)
        self.set_font("Helvetica", "I", 8.5)
        self.set_text_color(*self.GREY)
        self.cell(0, 3.8, _safe(sub), ln=1)
        self.set_font("Helvetica", "", 8.7)
        self.set_text_color(*self.GREY)
        for b in bullets:
            self.set_x(16)
            self.cell(3, 3.8, "-")
            self.multi_cell(178, 3.8, _safe(b))
        self.ln(0.6)

    def education_item(self, title: str, school: str, period: str, note: str):
        self.set_x(14)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.NAVY)
        self.cell(140, 4.0, _safe(title), ln=0)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*self.DARK_X)
        self.cell(0, 4.0, _safe(period), align="R", ln=1)
        self.set_x(14)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*self.GREY)
        self.cell(0, 3.7, _safe(school + (f"  -  {note}" if note else "")), ln=1)

    def two_columns(self, skills: list, languages: list):
        start_y = self.get_y()
        col_w   = 86

        # Left: skills
        self.set_xy(14, start_y)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self.NAVY)
        self.cell(col_w, 5.5, "COMPETENCES CLES", ln=2)
        gy = self.get_y()
        self.set_fill_color(*self.GOLD)
        self.rect(14, gy - 0.4, 20, 0.6, style="F")
        self.set_y(gy + 0.4)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*self.GREY)
        for s in skills:
            self.set_x(16)
            self.cell(3, 3.8, "-")
            self.multi_cell(col_w - 5, 3.8, _safe(s))
        skills_end_y = self.get_y()

        # Right: languages
        self.set_xy(108, start_y)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self.NAVY)
        self.cell(col_w, 5.5, "LANGUES", ln=2)
        ly = self.get_y()
        self.set_fill_color(*self.GOLD)
        self.rect(108, ly - 0.4, 20, 0.6, style="F")
        self.set_y(ly + 0.4)
        for lang, level in languages:
            self.set_x(108)
            self.set_font("Helvetica", "B", 8.5)
            self.set_text_color(*self.NAVY)
            self.cell(28, 4.0, _safe(lang), ln=0)
            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(*self.GREY)
            self.cell(0, 4.0, _safe(level), ln=1)
        langs_end_y = self.get_y()
        self.set_y(max(skills_end_y, langs_end_y) + 1.5)

    def tools_strip(self, contrat: str = "cdi", extra: list = None):
        self.set_x(14)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self.NAVY)
        self.cell(0, 5.5, "OUTILS & DISPONIBILITE", ln=1)
        y = self.get_y()
        self.set_fill_color(*self.GOLD)
        self.rect(14, y - 0.4, 20, 0.6, style="F")
        self.set_y(y + 0.4)
        base = (
            "CRM : HubSpot, Sales Navigator  |  Marketing : Canva, Notion, Wix  |  "
            "Bureautique : Excel avance, Google Suite  |  "
        ) + _DISPO_LINE.get(contrat, _DISPO_LINE["cdi"])
        if extra:
            unique = [t for t in extra if t.lower() not in base.lower()][:3]
            if unique:
                base += "  |  " + ", ".join(unique)
        self.set_x(14)
        self.set_font("Helvetica", "", 8.3)
        self.set_text_color(*self.GREY)
        self.multi_cell(182, 3.8, _safe(base))


# ─── Fonctions publiques (utilisees par cover_letter_france) ──────────────────

def detect_role(titre: str, description: str = "") -> str:
    """Compat: retourne le mode_id (remplace l'ancien detect_role)."""
    return detect_mode(titre, description)


def is_simple_job(titre: str) -> bool:
    return any(kw in (titre or "").lower() for kw in _p.SIMPLE_JOB_KEYWORDS)


# ─── Point d'entree ───────────────────────────────────────────────────────────

def generate(offer: dict, contrat: str = "cdi") -> bytes:
    titre       = offer.get("titre", "")
    description = offer.get("description", "")
    mode        = get_mode_cv(titre, description)
    mode_id     = mode["id"]
    extra_tools = _extract_tools(description)
    simple      = mode_id == "urgent"

    # Tagline
    if simple:
        tagline = mode["tagline"]
    else:
        dispo = {
            "cdi":        "Disponible juin 2026",
            "alternance": "Alternance sept. 2026",
            "stage":      "Stage juil. 2026",
        }.get(contrat, "Disponible 2026")
        tagline = f"{mode['tagline']}  |  {dispo}"

    pdf = _CVPdf(format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.tagline = tagline
    pdf.add_page()

    # QR code LinkedIn
    qr_url = (PROFILE.get("video_cv_url") or PROFILE.get("qr_url") or "").strip()
    qr_label = "Voir mon CV video" if PROFILE.get("video_cv_url") else "LinkedIn"
    qr_path  = _make_qr_png(qr_url) if qr_url else ""
    if qr_path:
        try:
            pdf.image(qr_path, x=179, y=4, w=20, h=20)
            pdf.set_xy(179, 24)
            pdf.set_font("Helvetica", "B", 5.5)
            pdf.set_text_color(*pdf.GOLD)
            pdf.cell(20, 3, _safe(qr_label), align="C")
        except Exception:
            pass
        finally:
            try:
                os.unlink(qr_path)
            except Exception:
                pass

    # Resume
    if simple:
        summary = _urgent_summary(titre)
    else:
        summary = mode["summary"]
        summary = ats_inject(summary, mode_id, description)

    pdf.section("Profil")
    pdf.paragraph(summary, font_size=8.7)

    # Experiences
    order   = mode["exp_order"]
    variant = mode["exp_variant"]
    bper    = mode["bullets_per"]
    by_id   = {e["id"]: e for e in EXPERIENCES}

    pdf.section("Experience professionnelle")
    for pos, exp_id in enumerate(order):
        exp = by_id.get(exp_id)
        if not exp:
            continue
        n = bper[pos] if pos < len(bper) else 1
        bullets_src = exp["bullets"].get(variant) or exp["bullets"]["default"]
        sub = f"{exp['company']}   |   {exp['city']}"
        pdf.experience_item(exp["title"], exp["period"], sub, bullets_src[:n])

    # Formation
    pdf.section("Formation")
    edu = EDUCATION[:2] if simple else EDUCATION
    for title, school, period, note in edu:
        pdf.education_item(title, school, period, note)

    pdf.ln(0.8)

    # Competences
    if simple:
        skills = mode["skills"]
        pdf.two_columns(skills, LANGUAGES)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "", 8.3)
        pdf.set_text_color(*pdf.GREY)
        pdf.multi_cell(182, 3.8, _safe("DISPONIBILITE  |  Immediatement  |  Paris et IDF  |  Permis B"))
    else:
        pdf.two_columns(mode["skills"], LANGUAGES)
        pdf.tools_strip(contrat, extra_tools)

    out = pdf.output(dest="S")
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)
