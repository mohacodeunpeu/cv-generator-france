"""
Generateur de CV France — CDI / alternance / stage.
Adapte du generateur VIE : meme profil Amine, sans references VIE.
- 1 page A4 garantie
- Titre/tagline adapte au role + type de contrat
- Experiences reordonnees par pertinence
- Design : header bleu marine + accent dore + QR code LinkedIn
"""

import io
import os
import re
import tempfile

from fpdf import FPDF
import amine_profile as _p


# ─── Profil (source : profile.py) ────────────────────────────────────────────

PROFILE = {
    "name":        _p.FULL_NAME,
    "phone":       _p.PHONE,
    "email":       _p.EMAIL,
    "city":        _p.CITY,
    "qr_url":      _p.LINKEDIN_URL,
    "video_cv_url": "",
}


# ─── Taglines par role ────────────────────────────────────────────────────────

_TAGLINE_BASE = {
    "product_marketing": "Brand & Product Manager | MBA Manager de Business Unit",
    "digital_marketing": "Digital Marketing Manager | MBA Manager de Business Unit",
    "financial_analyst": "Financial Analyst | MBA Manager de Business Unit",
    "data_analyst":      "Data & Business Analyst | MBA Manager de Business Unit",
    "purchasing":        "Acheteur & Category Manager | MBA Manager de Business Unit",
    "key_account":       "Key Account Manager | MBA Manager de Business Unit",
    "business_dev":      "Business Developer B2B | MBA Manager de Business Unit",
    "sales":             "Sales Manager | MBA Manager de Business Unit",
    "hr":                "Talent Acquisition | MBA Manager de Business Unit",
    "generic":           "Business Developer | MBA Manager de Business Unit",
}

_DISPO_SUFFIX = {
    "cdi":        "Disponible juin 2026",
    "alternance": "Alternance — sept. 2026",
    "stage":      "Stage — juil. 2026",
}


def _build_tagline(role: str, contrat: str) -> str:
    base  = _TAGLINE_BASE.get(role, _TAGLINE_BASE["generic"])
    dispo = _DISPO_SUFFIX.get(contrat, "Disponible 2026")
    return f"{base}  |  {dispo}"


# ─── Detection type d'entreprise ──────────────────────────────────────────────

_BIG_GROUPS = [
    "lvmh", "loreal", "l'oreal", "sanofi", "bnp", "axa", "societe generale",
    "total", "michelin", "renault", "danone", "hermes", "chanel", "kering",
    "air france", "edf", "engie", "orange", "capgemini", "deloitte", "pwc",
    "kpmg", "mckinsey", "bain", "bcg", "accenture", "hsbc", "natixis",
    "carrefour", "decathlon",
]

_STARTUP_KW = ["startup", "scale-up", "scaleup", "series", "saas", "fintech",
               "proptech", "agile", "growth", "product-led", "levee de fonds"]


def detect_company_type(entreprise: str, description: str = "") -> str:
    e = (entreprise or "").lower()
    d = (description or "").lower()
    if any(b in e for b in _BIG_GROUPS):
        return "grand_groupe"
    if any(s in f"{e} {d}" for s in _STARTUP_KW):
        return "startup"
    return "pme"


# ─── Vocabulaire sectoriel pour le resume ────────────────────────────────────

_SECTOR_VOCAB = {
    "banque":    ["compliance", "risk", "P&L", "front office", "client institutionnel"],
    "conseil":   ["deliverable", "business case", "engagement client", "recommandations"],
    "luxe":      ["image de marque", "clientele premium", "exclusivite", "savoir-faire"],
    "startup":   ["croissance rapide", "impact direct", "culture data", "autonomie"],
    "finance":   ["analyse credit", "due diligence", "modelisation", "cash flow"],
}


def _detect_sector_from_desc(description: str) -> str:
    d = (description or "").lower()
    if any(k in d for k in ["banque", "bancaire", "bank", "credit", "pret"]):
        return "banque"
    if any(k in d for k in ["cabinet", "conseil", "consulting", "audit", "advisory"]):
        return "conseil"
    if any(k in d for k in ["luxe", "premium", "maison", "haute couture", "joaillerie"]):
        return "luxe"
    if any(k in d for k in ["startup", "scale", "saas", "fintech", "growth"]):
        return "startup"
    if any(k in d for k in ["finance", "financier", "investissement", "gestion d'actifs"]):
        return "finance"
    return ""


def _sector_suffix(description: str) -> str:
    """Phrase additionnelle adaptee au secteur detecte."""
    sector = _detect_sector_from_desc(description)
    if sector == "banque":
        return " Sensibilise a la culture risk/compliance et a la rigueur propre aux environnements bancaires."
    if sector == "conseil":
        return " A l'aise avec la culture deliverable et la pression client propres au conseil."
    if sector == "luxe":
        return " Comprend les codes du premium : precision, coherence de marque, clientele exigeante (Printemps Haussmann)."
    if sector == "startup":
        return " Recherche un environnement ou l'impact est visible rapidement et ou l'autonomie est un atout."
    return ""


# ─── Resumes par role ─────────────────────────────────────────────────────────

SUMMARY_BASE = {
    "product_marketing": (
        "MBA Manager de Business Unit (PSB Paris, juin 2026). Gestion de projets "
        "digitaux intl (Wix, Lisbonne) et community management (GROW 360, Paris). "
        "Capable de structurer une demarche produit et la decliner en actions "
        "marketing concretes sur des marches multiculturels."
    ),
    "digital_marketing": (
        "MBA Business Unit en cours (PSB Paris, juin 2026). Experience operationnelle "
        "en community management (GROW 360) et projets digitaux a l'international. "
        "Maitrise des leviers d'engagement et lecture rigoureuse des KPIs."
    ),
    "financial_analyst": (
        "MBA Manager de Business Unit en cours (PSB Paris, juin 2026), module "
        "controle de gestion. Pilote au quotidien une activite a 360 KEUR/mois : "
        "KPIs, reporting direction, lecture business des chiffres."
    ),
    "data_analyst": (
        "MBA Business Unit en cours (PSB Paris, juin 2026). Pilotage quotidien de "
        "KPIs commerciaux. Forme a l'analyse et au storytelling de donnees pour "
        "traduire un dataset en insight actionnable."
    ),
    "purchasing": (
        "MBA Business Unit en cours (PSB Paris, juin 2026). Negotiation Business "
        "School certifie (2025). Experience de negociation B2B sur portefeuille "
        "a 360 KEUR/mois, multilingue, transposable aux enjeux achats."
    ),
    "key_account": (
        "Business Developer B2B chez Agence 113 / DEFI GROUPE (360 KEUR/mois). "
        "MBA Manager de Business Unit en cours (PSB Paris, juin 2026). Profil "
        "hunter-farmer, multilingue, oriente partenariats strategiques long terme."
    ),
    "business_dev": (
        "Business Developer B2B chez Agence 113 / DEFI GROUPE, 360 KEUR/mois. "
        "MBA Manager de Business Unit en cours (PSB Paris, juin 2026). Cycle "
        "commercial complet, HubSpot CRM, Sales Navigator, negociation B2B."
    ),
    "sales": (
        "Business Developer B2B chez Agence 113 / DEFI GROUPE (360 KEUR/mois) "
        "et ex-Sales Advisor Printemps Haussmann. MBA Manager de Business Unit en "
        "cours a PSB Paris. Profil multilingue oriente resultats."
    ),
    "hr": (
        "Recruitment Officer chez Agence 113 / DEFI GROUPE : 300+ candidats geres, "
        "coordination POEI, sourcing actif. Double competence RH/business, renforcee "
        "par le MBA Manager de Business Unit en cours (PSB Paris, juin 2026)."
    ),
    "generic": (
        "MBA Manager de Business Unit en cours (PSB Paris, juin 2026). Business "
        "Developer B2B (360 KEUR/mois), experience internationale Lisbonne, "
        "multilingue (FR/AR natifs, EN courant). Profil junior ambitieux."
    ),
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
                "Developpement portefeuille B2B 360 KEUR/mois : cycle complet en autonomie.",
                "Negociation directe decideurs via HubSpot : 3 partenariats LT conclus/trim.",
                "Pipeline structure : 30+ opportunites qualifiees suivies en temps reel.",
            ],
            "marketing": [
                "Pilotage activite 360 KEUR/mois : 5 KPIs suivis, reporting hebdo direction.",
                "Acquisition B2B ciblee : 30+ contacts qualifies/mois via prospection active.",
                "Coordination production/com/RH : livraison sans retard sur 6 mois.",
            ],
            "finance": [
                "Suivi budgetaire 360 KEUR/mois : analyse marges et ecarts hebdomadaires.",
                "Reporting mensuel direction via dashboards Excel (TCD, formules avancees).",
                "Analyse rentabilite client : 3 leviers d'optimisation identifies et appliques.",
            ],
            "hr": [
                "Events recrutement : 300+ candidats qualifies et accueillis par session.",
                "Coordination POEI France Travail : 15 integrations geries en parallele.",
                "Pilotage KPIs RH : suivi taux de placement et reporting mensuel management.",
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
            "marketing": [
                "Projets digitaux clients intl : brief, contenu, A/B tests, livraison.",
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
                "Depassement objectifs de vente (+10% vs. cible mensuelle) sur zone premium.",
                "Fidelisation clientele internationale : taux de retour eleve sur portefeuille.",
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

BULLET_VARIANT = {
    "product_marketing": "marketing",
    "digital_marketing": "marketing",
    "financial_analyst": "finance",
    "data_analyst":      "finance",
    "purchasing":        "commerce",
    "key_account":       "commerce",
    "business_dev":      "commerce",
    "sales":             "commerce",
    "hr":                "hr",
    "generic":           "default",
}

ROLE_PRIORITY = {
    "product_marketing": ["wix", "grow", "defi", "printemps"],
    "digital_marketing": ["grow", "wix", "defi", "printemps"],
    "financial_analyst": ["defi", "wix", "printemps", "grow"],
    "data_analyst":      ["defi", "wix", "printemps", "grow"],
    "purchasing":        ["defi", "wix", "printemps", "grow"],
    "key_account":       ["defi", "printemps", "wix", "grow"],
    "business_dev":      ["defi", "printemps", "wix", "grow"],
    "sales":             ["defi", "printemps", "wix", "grow"],
    "hr":                ["defi", "grow", "wix", "printemps"],
    "generic":           ["defi", "wix", "printemps", "grow"],
}

BULLETS_PER_POSITION = [3, 2, 2, 2]


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


# ─── Competences ──────────────────────────────────────────────────────────────

SKILLS_BY_ROLE = {
    "product_marketing": [
        "Strategie produit, positionnement, pricing (MBA)",
        "Gestion de projets digitaux intl (Wix, Lisbonne)",
        "Community Management et contenu (GROW 360, Paris)",
        "Lecture KPI, taux de conversion, ROI marketing",
        "Coordination marketing / ventes / R&D",
    ],
    "digital_marketing": [
        "Community Management et reseaux sociaux (GROW 360)",
        "Pilotage campagnes digitales et lecture KPI/ROI",
        "Outils : Canva, Notion, Google Suite, Wix",
        "UX et conversion (projets clients intl)",
        "Strategie de contenu multiculturelle",
    ],
    "financial_analyst": [
        "Controle de gestion et lecture financiere (MBA)",
        "Pilotage de KPIs commerciaux a 360 KEUR/mois",
        "Reporting, analyse d'ecarts, dashboards Excel",
        "Pack Office avance (TCD, formules, VBA)",
        "Rigueur analytique et orientation business",
    ],
    "data_analyst": [
        "Analyse de donnees et pilotage KPIs (MBA)",
        "Gestion d'indicateurs commerciaux au quotidien",
        "Excel avance, notions Power BI / Tableau",
        "Storytelling de donnees pour les decideurs",
        "Esprit critique et rigueur methodologique",
    ],
    "purchasing": [
        "Negociation B2B (Negotiation Business School, 2025)",
        "Analyse de besoins et structuration d'offres",
        "Multilinguisme : FR/AR natifs, EN courant, ES inter.",
        "Pack Office avance et CRM HubSpot",
        "Suivi de performance et reporting",
    ],
    "key_account": [
        "Portefeuille B2B a 360 KEUR/mois en autonomie",
        "Cycle commercial complet (prospection -> closing)",
        "HubSpot CRM, LinkedIn Sales Navigator",
        "Negotiation Business School (certifie 2025)",
        "Multilinguisme et adaptabilite culturelle",
    ],
    "business_dev": [
        "Business Development B2B (360 KEUR/mois)",
        "Cycle commercial : prospection -> closing",
        "HubSpot CRM, LinkedIn Sales Navigator",
        "Negotiation Business School (certifie 2025)",
        "Multilinguisme : FR / AR / EN / ES",
    ],
    "sales": [
        "Vente B2B et B2C premium (DEFI + Printemps)",
        "Depassement regulier d'objectifs commerciaux",
        "Negotiation Business School (certifie 2025)",
        "HubSpot CRM, LinkedIn Sales Navigator",
        "Multilinguisme et relation client haut de gamme",
    ],
    "hr": [
        "Recrutement : 300+ candidats geres en events",
        "Coordination POEI avec France Travail",
        "Outils : Indeed, France Travail, LinkedIn",
        "Animation d'evenements et entretiens",
        "Habilitation SST (Croix-Rouge Francaise)",
    ],
    "generic": [
        "Cycle commercial et negociation B2B",
        "Gestion de projets intl (Lisbonne)",
        "HubSpot CRM, LinkedIn Sales Navigator",
        "Pack Office avance et Google Suite",
        "FR / EN / AR / ES",
    ],
}

LANGUAGES = [
    ("Francais",  "Natif"),
    ("Arabe",     "Natif"),
    ("Anglais",   "Courant"),
    ("Espagnol",  "Intermediaire"),
    ("Chinois",   "Notions"),
]


# ─── Disponibilite par contrat ────────────────────────────────────────────────

_DISPO_LINE = {
    "cdi":        "Disponibilite : CDI, juin 2026  |  Mobilite : Permis B, remote OK",
    "alternance": "Disponibilite : Alternance (2 ans, sept. 2026)  |  Rythme : 3j/2j ou 4j/1j  |  Permis B",
    "stage":      "Disponibilite : Stage (4-6 mois, juil. 2026)  |  Mobilite : Paris + IDF  |  Permis B",
}


# ─── Detection sous-role ──────────────────────────────────────────────────────

_SUB_ROLES = [
    ("product_marketing", ["chef de produit", "product marketing", "product manager",
                           "brand manager", "brand specialist", "global brand",
                           "category manager", "trade marketing", "shopper marketing"]),
    ("digital_marketing", ["digital marketing", "growth", "performance marketing",
                           "content marketing", "social media", "community manager",
                           "seo", "sea", "campaign", "acquisition"]),
    ("financial_analyst", ["financial analyst", "controller", "controlling",
                           "fp&a", "business analyst", "controle de gestion",
                           "audit", "treasury", "tresor"]),
    ("data_analyst",      ["data analyst", "sales analyt", "business intelligence",
                           "bi analyst", "analytics"]),
    ("purchasing",        ["acheteur", "purchaser", "buyer", "achat",
                           "procurement", "sourcing", "category"]),
    ("key_account",       ["key account", "key client", "grand compte",
                           "account manager", "account executive"]),
    ("business_dev",      ["business dev", "bizdev", "developpement commercial",
                           "business developer", "sdr"]),
    ("sales",             ["sales", "commercial", "vente", "ventes", "closing"]),
    ("hr",                ["talent", "recruitment", "recrutement", "hrbp",
                           "people", "human resources", "ressources humaines"]),
]


def detect_role(titre: str, description: str = "") -> str:
    titre_l = (titre or "").lower()
    full_l  = titre_l + " " + (description or "").lower()
    for role, kws in _SUB_ROLES:
        if any(kw in titre_l for kw in kws):
            return role
    for role, kws in _SUB_ROLES:
        if any(kw in full_l for kw in kws):
            return role
    return "generic"


def is_simple_job(titre: str) -> bool:
    """Detecte les jobs terrain/operationnels sans besoin de MBA pitch."""
    return any(kw in (titre or "").lower() for kw in _p.SIMPLE_JOB_KEYWORDS)


# ─── Summaries mode urgence (jobs simples) ───────────────────────────────────

_SUMMARY_SIMPLE = {
    "luxe": (
        "Conseiller de vente avec experience en environnement premium (Printemps Haussmann). "
        "A l'aise avec une clientele internationale exigeante. "
        "Disponible immediatement, serieux et presente."
    ),
    "commercial": (
        "Profil commercial terrain avec experience de vente B2B et retail. "
        "Habitue aux objectifs, disponible immediatement. "
        "Multilingue, a l'aise avec toutes clienteles."
    ),
    "recrutement": (
        "Experience en recrutement operationnel (300+ candidats geres). "
        "A l'aise dans la relation humaine et la selection. "
        "Disponible immediatement, reactif et organise."
    ),
    "default": (
        "Profil operationnel avec experience en vente, relation client et gestion. "
        "Disponible immediatement. Serieux, ponctuel, oriente terrain. "
        "Multilingue (FR/AR/EN), s'adapte rapidement."
    ),
}


def _simple_summary(titre: str) -> str:
    t = titre.lower()
    if any(k in t for k in _p.LUXE_KEYWORDS):
        return _SUMMARY_SIMPLE["luxe"]
    if any(k in t for k in _p.COMMERCIAL_KEYWORDS):
        return _SUMMARY_SIMPLE["commercial"]
    if any(k in t for k in _p.RECRUTEMENT_KEYWORDS):
        return _SUMMARY_SIMPLE["recrutement"]
    return _SUMMARY_SIMPLE["default"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe(text: str) -> str:
    if not text:
        return ""
    repl = {
        "—": "-", "–": "-", "'": "'", "'": "'",
        "’": "'", "“": '"', "”": '"',
        "…": "...", " ": " ", " ": " ",
        "•": "-", "→": "->", "▸": "-",
        "€": "EUR", "œ": "oe", "Œ": "OE",
        "æ": "ae", "Æ": "AE",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


def _extract_tools(description: str) -> list:
    """Detection basique des outils mentionnes dans l'offre."""
    known = [
        "salesforce", "sap", "power bi", "tableau", "jira", "confluence",
        "hubspot", "notion", "asana", "monday", "figma", "adobe",
        "google analytics", "data studio", "looker", "sql", "python",
    ]
    desc_l = (description or "").lower()
    return [t for t in known if t in desc_l]


# ─── QR Code ──────────────────────────────────────────────────────────────────

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
    NAVY   = (15, 35, 85)
    GOLD   = (193, 154, 60)
    GREY   = (60, 60, 65)
    LIGHT  = (245, 247, 250)
    DARK_X = (90, 90, 95)

    tagline = "Business Developer | MBA Manager de Business Unit  |  Disponible 2026"

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
        self.set_x(14)
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
        line = school + (f"  -  {note}" if note else "")
        self.cell(0, 3.7, _safe(line), ln=1)

    def two_columns_skills_languages(self, skills: list, languages: list):
        start_y = self.get_y()
        col_w   = 86

        self.set_xy(14, start_y)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self.NAVY)
        self.cell(col_w, 5.5, _safe("COMPETENCES CLES"), ln=2)
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

        self.set_xy(108, start_y)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self.NAVY)
        self.cell(col_w, 5.5, _safe("LANGUES"), ln=2)
        ly = self.get_y()
        self.set_fill_color(*self.GOLD)
        self.rect(108, ly - 0.4, 20, 0.6, style="F")
        self.set_y(ly + 0.4)

        self.set_font("Helvetica", "", 8.5)
        for lang, level in languages:
            self.set_x(108)
            self.set_text_color(*self.NAVY)
            self.set_font("Helvetica", "B", 8.5)
            self.cell(28, 4.0, _safe(lang), ln=0)
            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(*self.GREY)
            self.cell(0, 4.0, _safe(level), ln=1)
        langs_end_y = self.get_y()

        self.set_y(max(skills_end_y, langs_end_y) + 1.5)

    def tools_strip(self, contrat: str = "cdi", extra_tools: list = None):
        self.set_x(14)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*self.NAVY)
        self.cell(0, 5.5, _safe("OUTILS & DISPONIBILITE"), ln=1)
        y = self.get_y()
        self.set_fill_color(*self.GOLD)
        self.rect(14, y - 0.4, 20, 0.6, style="F")
        self.set_y(y + 0.4)

        base = (
            "CRM : HubSpot, Sales Navigator  |  Marketing : Canva, Notion, Wix  |  "
            "Bureautique : Excel avance, Google Suite  |  "
        ) + _DISPO_LINE.get(contrat, _DISPO_LINE["cdi"])

        if extra_tools:
            unique = [t for t in extra_tools if t.lower() not in base.lower()][:3]
            if unique:
                base = base + "  |  " + ", ".join(unique)

        self.set_x(14)
        self.set_font("Helvetica", "", 8.3)
        self.set_text_color(*self.GREY)
        self.multi_cell(182, 3.8, _safe(base))


# ─── Point d'entree ───────────────────────────────────────────────────────────

def generate(offer: dict, contrat: str = "cdi") -> bytes:
    """
    Genere un CV PDF France adapte a l'offre et au type de contrat.
    contrat: 'cdi' | 'alternance' | 'stage'
    """
    titre       = offer.get("titre", "")
    description = offer.get("description", "")
    role        = detect_role(titre, description)
    extra_tools = _extract_tools(description)
    simple      = is_simple_job(titre)

    # Mode urgence : tagline direct sans jargon MBA
    if simple:
        tagline = f"Profil operationnel & relation client  |  Disponible immediatement"
    else:
        tagline = _build_tagline(role, contrat)

    pdf = _CVPdf(format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.tagline = tagline
    pdf.add_page()

    # QR code
    qr_url = (PROFILE.get("video_cv_url") or PROFILE.get("qr_url") or "").strip()
    qr_label = "Voir mon CV video" if PROFILE.get("video_cv_url") else "Voir mon LinkedIn"
    qr_path = _make_qr_png(qr_url) if qr_url else ""
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

    # Resume : mode urgence = phrase courte et directe
    if simple:
        summary = _simple_summary(titre)
    else:
        summary = SUMMARY_BASE.get(role, SUMMARY_BASE["generic"])
        sector_sfx = _sector_suffix(description)
        if sector_sfx:
            summary = summary.rstrip(".") + "." + sector_sfx

    pdf.section("Profil")
    pdf.paragraph(summary, font_size=8.7)

    pdf.section("Experience professionnelle")
    # Mode urgence : priorite Printemps (vente terrain) + DEFI, bullets courts
    if simple:
        order   = ["printemps", "defi", "grow", "wix"]
        variant = "default"
        bullets_per = [2, 2, 1, 1]
    else:
        variant      = BULLET_VARIANT.get(role, "default")
        order        = ROLE_PRIORITY.get(role, ROLE_PRIORITY["generic"])
        bullets_per  = BULLETS_PER_POSITION

    by_id = {e["id"]: e for e in EXPERIENCES}
    for pos, exp_id in enumerate(order):
        exp = by_id.get(exp_id)
        if not exp:
            continue
        n_bullets   = bullets_per[pos] if pos < len(bullets_per) else 1
        all_bullets = exp["bullets"].get(variant) or exp["bullets"]["default"]
        bullets     = all_bullets[:n_bullets]
        sub         = f"{exp['company']}   |   {exp['city']}"
        pdf.experience_item(exp["title"], exp["period"], sub, bullets)

    pdf.section("Formation")
    # Mode urgence : ne montrer que les 2 plus recents (pas SST)
    edu_list = EDUCATION[:2] if simple else EDUCATION
    for title, school, period, note in edu_list:
        pdf.education_item(title, school, period, note)

    pdf.ln(0.8)
    # Competences mode urgence : simples, terrain
    if simple:
        skills = [
            "Vente et conseil client (B2B et retail premium)",
            "Relation client et fidelisation",
            "Travail en equipe et autonomie",
            "Outils : Excel, Canva, Google Suite",
            "Multilinguisme : FR / AR / EN / ES",
        ]
    else:
        skills = SKILLS_BY_ROLE.get(role, SKILLS_BY_ROLE["generic"])
    pdf.two_columns_skills_languages(skills, LANGUAGES)

    # Disponibilite mode urgence : toujours immediate
    if simple:
        dispo = "Disponibilite : Immediatement  |  Mobilite : Paris et IDF  |  Permis B"
        pdf.set_x(14)
        pdf.set_font("Helvetica", "", 8.3)
        pdf.set_text_color(*pdf.GREY)
        pdf.multi_cell(182, 3.8, _safe(f"DISPONIBILITE  |  {dispo}"))
    else:
        pdf.tools_strip(contrat, extra_tools)

    out = pdf.output(dest="S")
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
