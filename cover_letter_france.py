"""
Generateur de lettre de motivation — 5 modes intelligents.
Adapte automatiquement depuis mode detecte + type d'entreprise.
"""

import io
from datetime import date

from fpdf import FPDF

from cv_gen_france import PROFILE, is_simple_job, _safe
import amine_profile as _p
from modes import (
    detect_mode, get_mode_letter, hook_for, human_phrase,
    detect_company_type, _MODES,
)


# ─── Closing ─────────────────────────────────────────────────────────────────

def _closing(contrat: str) -> str:
    if contrat == "alternance":
        return (
            "Cette alternance represente exactement l'equilibre que je recherche : "
            "progresser en MBA tout en apportant une contribution concrete depuis "
            "le premier mois. Je reste disponible pour un echange a votre convenance."
        )
    if contrat == "stage":
        return (
            "Ce stage represente l'opportunite de mettre mes competences au service "
            "de vos projets dans un environnement exigeant. "
            "Je reste disponible pour un echange a votre convenance."
        )
    return (
        "Je suis convaincu de pouvoir apporter une contribution concrete et rapide "
        "a votre equipe. Je reste disponible pour un echange a votre convenance."
    )


# ─── Mode URGENT (jobs terrain) ───────────────────────────────────────────────

def _generate_urgent(titre: str, entreprise: str, contrat: str) -> str:
    t = titre.lower()
    is_luxe = any(k in t for k in _p.LUXE_KEYWORDS)
    is_recr = any(k in t for k in _p.RECRUTEMENT_KEYWORDS)

    if is_luxe:
        hook = (
            f"Je vous adresse ma candidature pour le poste de {titre} chez {entreprise}. "
            f"Fort d'une experience en vente conseil premium au Printemps Haussmann "
            f"(+10% vs objectif, clientele internationale), je suis a l'aise dans "
            f"les environnements d'excellence et d'exigence."
        )
        corps = (
            "Attentif au detail, naturellement presentable et a l'aise avec une "
            "clientele diverse, je corresponds aux codes de votre environnement. "
            "Disponible immediatement."
        )
    elif is_recr:
        hook = (
            f"Je vous adresse ma candidature pour le poste de {titre} chez {entreprise}. "
            f"Recruitment Officer chez Agence 113 / DEFI GROUPE ou j'ai gere des "
            f"evenements reunissant 300+ candidats, je suis operationnel immediatement "
            f"en selection, accueil et coordination."
        )
        corps = (
            "Je sais travailler vite, garder les priorites en tete et maintenir "
            "un bon contact humain meme sous pression. Serieux, reactif, disponible."
        )
    else:
        hook = (
            f"Je vous adresse ma candidature pour le poste de {titre} chez {entreprise}. "
            f"Avec une experience en vente conseil (Printemps Haussmann) et relation "
            f"client, je suis operationnel immediatement et motive pour integrer "
            f"votre equipe."
        )
        corps = (
            "Ponctuel, serieux, a l'aise dans les environnements dynamiques. "
            "Je m'adapte vite et livre ce qu'on attend de moi."
        )

    closing_map = {
        "stage":      "Ce stage est une opportunite de contribuer concretement. Disponible des que possible.",
        "alternance": "Cette alternance m'interesse pour progresser tout en contribuant.",
    }
    closing = closing_map.get(contrat, "Disponible immediatement, serais ravi d'echanger avec vous.")

    return "\n\n".join([
        "Madame, Monsieur,",
        hook,
        corps,
        closing,
        f"Cordialement,\n{PROFILE['name']}\n{PROFILE['phone']} | {PROFILE['email']}",
    ])


# ─── Bridge contextuel ────────────────────────────────────────────────────────

def _bridge(mode_id: str, description: str) -> str:
    """1 phrase qui relie l'offre a l'experience d'Amine via un mot-cle detecte."""
    desc = (description or "").lower()

    _BRIDGES = {
        "sales": {
            "pipeline":    "La dimension pipeline que vous portez correspond directement a ce que je maitrise chez Agence 113 / DEFI GROUPE : structurer, qualifier, closer en autonomie.",
            "negociation": "La dimension negociation au coeur de ce poste correspond a l'approche que j'applique au quotidien sur des cycles B2B a forts enjeux.",
            "hunting":     "Le profil hunter que vous decrivez, c'est exactement ma posture quotidienne : identifier, qualifier et closer en autonomie sur 360 KEUR/mois.",
            "partenariat": "Le developpement de partenariats strategiques que vous portez correspond directement aux 3 partenariats long terme que je conclus en moyenne par trimestre.",
        },
        "corporate": {
            "reporting":   "La dimension reporting que vous portez correspond a ce que je pratique : suivi 360 KEUR/mois, dashboards Excel, analyse hebdomadaire direction.",
            "digital":     "Les projets digitaux que vous decrivez correspondent directement a mon experience : 5+ sites clients livres en autonomie depuis Lisbonne.",
            "contenu":     "La strategie de contenu que vous portez correspond a ce que j'ai mis en place chez GROW 360 : +35% d'engagement en 6 mois.",
            "budget":      "Le suivi budgetaire que vous mentionnez correspond exactement a mon quotidien : 360 KEUR/mois analyses hebdomadairement.",
        },
        "people": {
            "sourcing":    "Le sourcing actif que vous decrivez correspond a ce que je pratique : LinkedIn, Indeed, France Travail, 300+ candidats qualifies par session.",
            "onboarding":  "L'onboarding que vous mentionnez correspond a mon experience de coordination POEI : 15 integrations geries en parallele par cycle.",
            "entretien":   "La conduite d'entretiens que vous portez correspond directement a ce que je pratique en sessions de recrutement massives.",
        },
        "luxe": {
            "premium":     "L'environnement premium que vous decrivez correspond exactement a ce que j'ai vecu au Printemps Haussmann : clientele internationale haut de gamme, depassement d'objectifs (+10%).",
            "service":     "L'excellence du service que vous portez correspond aux codes que j'ai integres au Printemps Haussmann aupres d'une clientele internationale exigeante.",
            "fidelisation":"La fidelisation clientele que vous mentionnez correspond a ce que j'ai pratique au quotidien en retail premium.",
        },
    }

    pool = _BRIDGES.get(mode_id, {})
    for kw, phrase in pool.items():
        if kw in desc:
            return phrase
    return ""


# ─── Generation standard ─────────────────────────────────────────────────────

def generate(offer: dict, contrat: str = "cdi") -> str:
    titre       = offer.get("titre", "le poste propose")
    entreprise  = offer.get("entreprise", "votre entreprise")
    description = offer.get("description", "")

    if is_simple_job(titre):
        return _generate_urgent(titre, entreprise, contrat)

    mode_id  = detect_mode(titre, description)
    mode_cfg = _MODES[mode_id]["letter"]
    ctype    = detect_company_type(entreprise, description)

    hook    = hook_for(mode_id, titre, entreprise, contrat, offer)
    bridge  = _bridge(mode_id, description)
    pitch   = mode_cfg["pitch"]
    plan    = mode_cfg["plan_30j"]
    human   = human_phrase(mode_id, ctype, entreprise)
    closing = _closing(contrat)

    paras = ["Madame, Monsieur,", hook]
    if bridge:
        paras.append(bridge)
    paras.append(pitch)
    if plan:
        paras.append(plan)
    if human:
        paras.append(human)
    paras.append(closing)
    paras.append(f"Cordialement,\n{PROFILE['name']}\n{PROFILE['phone']} | {PROFILE['email']}")

    return "\n\n".join(paras)


# ─── Mode BEST (conversion maximale) ─────────────────────────────────────────

_BEST_HOOKS = {
    "sales": (
        "{entreprise} — {poste}. Je ne vais pas tourner autour du pot : "
        "360 KEUR/mois en autonomie, 30+ leads qualifies par mois, cycle "
        "commercial complet. C'est le niveau que j'apporte depuis deux ans. "
        "MBA Manager de Business Unit (PSB Paris, juin 2026), "
        "certifie Negotiation Business School (2025)."
    ),
    "corporate": (
        "Je pilote 360 KEUR/mois au quotidien — KPIs, reporting, analyse "
        "budgetaire — tout en finissant mon MBA Manager de Business Unit "
        "(PSB Paris, juin 2026). Ce n'est pas theorie seule. Ce n'est pas "
        "terrain seul. C'est les deux en meme temps, et c'est precisement "
        "ce que le poste de {poste} chez {entreprise} requiert."
    ),
    "people": (
        "300 candidats qualifies en 3 heures. C'est ce que j'ai delivre "
        "en tant que Recruitment Officer chez Agence 113 / DEFI GROUPE. "
        "Double profil RH / Business Developer, MBA Manager de Business Unit "
        "en cours (PSB Paris, juin 2026). Le poste de {poste} chez "
        "{entreprise} correspond exactement a cette combinaison rare."
    ),
    "luxe": (
        "Depassement d'objectifs de +10% mensuel au Printemps Haussmann. "
        "Clientele internationale premium. Codes luxe integres dans la pratique, "
        "pas juste dans le discours. Le poste de {poste} chez {entreprise} est "
        "la suite logique de ce parcours."
    ),
}


def generate_best(offer: dict, contrat: str = "cdi") -> str:
    titre       = offer.get("titre", "le poste propose")
    entreprise  = offer.get("entreprise", "votre entreprise")
    description = offer.get("description", "")

    if is_simple_job(titre):
        return _generate_urgent(titre, entreprise, contrat)

    mode_id  = detect_mode(titre, description)
    mode_cfg = _MODES[mode_id]["letter"]
    ctype    = detect_company_type(entreprise, description)

    tmpl = _BEST_HOOKS.get(mode_id, _BEST_HOOKS["sales"])
    hook  = tmpl.format(poste=titre, entreprise=entreprise)
    bridge = _bridge(mode_id, description)
    pitch  = mode_cfg["pitch"]
    plan   = mode_cfg["plan_30j"]
    human  = human_phrase(mode_id, ctype, entreprise)
    closing = _closing(contrat)

    paras = ["Madame, Monsieur,", hook]
    if bridge:
        paras.append(bridge)
    paras.append(pitch)
    if plan:
        paras.append(plan)
    if human:
        paras.append(human)
    paras.append(closing)
    paras.append(f"Cordialement,\n{PROFILE['name']}\n{PROFILE['phone']} | {PROFILE['email']}")

    return "\n\n".join(paras)


# ─── Conversion lettre -> PDF ─────────────────────────────────────────────────

class _LetterPdf(FPDF):
    NAVY = (15, 35, 85)
    GOLD = (193, 154, 60)
    GREY = (50, 50, 55)

    def __init__(self, titre: str, entreprise: str):
        super().__init__()
        self._titre = titre
        self._entreprise = entreprise

    def header(self):
        self.set_fill_color(*self.NAVY)
        self.rect(0, 0, 210, 18, style="F")
        self.set_xy(14, 4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(255, 255, 255)
        self.cell(0, 6, _safe(PROFILE["name"]), ln=1)
        self.set_x(14)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(200, 210, 230)
        self.cell(0, 4, _safe(f"{PROFILE['phone']}  |  {PROFILE['email']}  |  {PROFILE['city']}"), ln=1)
        self.set_fill_color(*self.GOLD)
        self.rect(0, 18, 210, 0.7, style="F")
        self.set_y(22)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 155)
        self.cell(0, 3.5,
                  _safe(f"Lettre de motivation — {self._titre} chez {self._entreprise}"),
                  align="C")


def to_pdf(letter_text: str, offer: dict = None) -> bytes:
    offer      = offer or {}
    titre      = offer.get("titre", "poste")
    entreprise = offer.get("entreprise", "entreprise")

    pdf = _LetterPdf(titre, entreprise)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_y(26)
    pdf.set_x(130)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 85)
    pdf.cell(0, 5, _safe(f"Paris, le {date.today().strftime('%d/%m/%Y')}"), ln=1)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_x(14)
    pdf.set_text_color(15, 35, 85)
    pdf.cell(0, 5, _safe(f"Candidature : {titre}"), ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 85)
    pdf.set_x(14)
    pdf.cell(0, 5, _safe(entreprise), ln=1)
    pdf.ln(6)

    for i, para in enumerate(letter_text.split("\n\n")):
        pdf.set_x(14)
        if i == 0:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(15, 35, 85)
            pdf.cell(0, 6, _safe(para), ln=1)
            pdf.ln(2)
        elif para.startswith("Cordialement"):
            pdf.ln(4)
            for j, line in enumerate(para.split("\n")):
                pdf.set_x(14)
                pdf.set_font("Helvetica", "B" if j == 0 else "", 10 if j == 0 else 9)
                pdf.set_text_color(50, 50, 55)
                pdf.cell(0, 5, _safe(line), ln=1)
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 55)
            pdf.multi_cell(182, 5.5, _safe(para))
            pdf.ln(3)

    out = pdf.output(dest="S")
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)
