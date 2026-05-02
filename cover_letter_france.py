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

_CLOSINGS = {
    # contrat → mode → texte
    "alternance": {
        "sales":     "Cette alternance represente l'opportunite d'allier MBA et terrain commercial — ce que je cherche depuis le debut. Je suis disponible pour en discuter quand vous le souhaitez.",
        "corporate": "Cette alternance me permettrait de combiner ma formation MBA avec une experience analytique concrete. Je suis disponible pour un echange a votre convenance.",
        "people":    "Cette alternance est pour moi le meilleur moyen de progresser en RH tout en apportant quelque chose de concret des le premier jour. Disponible pour echanger.",
        "luxe":      "Cette alternance represente une vraie opportunite d'entrer dans l'univers du luxe avec un engagement serieux. Je reste disponible pour un entretien.",
        "urgent":    "Ce poste m'interesse et je suis disponible immediatement. N'hesitez pas a me contacter.",
        "_default":  "Cette alternance represente exactement l'equilibre que je recherche : progresser en MBA tout en apportant une contribution concrete depuis le premier mois. Je reste disponible.",
    },
    "stage": {
        "sales":     "Ce stage serait pour moi l'occasion de contribuer a un vrai objectif commercial et de prouver ce dont je suis capable en conditions reelles. Disponible a votre convenance.",
        "corporate": "Ce stage me permettrait de mettre en pratique les outils analytiques developpes en MBA dans un contexte operationnel exigeant. Je reste disponible pour en discuter.",
        "people":    "Ce stage est une vraie opportunite de contribuer concretement a vos processus RH. Je suis disponible pour en echanger.",
        "luxe":      "Ce stage serait pour moi l'entree dans un univers que je respecte et ou je suis pret a m'investir pleinement. Disponible pour un entretien.",
        "urgent":    "Je suis disponible immediatement pour ce poste. N'hesitez pas a me contacter.",
        "_default":  "Ce stage represente l'opportunite de mettre mes competences au service de vos projets dans un environnement exigeant. Je reste disponible.",
    },
    "cdi": {
        "sales":     "Je suis pret a m'engager sur des objectifs concrets et a delivrer rapidement. Un entretien de 30 minutes suffira a vous en convaincre — je reste disponible.",
        "corporate": "Je suis convaincu que ce poste correspond a la fois a ce que j'apporte aujourd'hui et a ce que je veux construire. Disponible pour un echange a votre convenance.",
        "people":    "Je serais ravi de vous montrer concretement comment je travaille sur un processus de recrutement reel. Je reste disponible pour un entretien.",
        "luxe":      "Je suis disponible pour un entretien et convaincu que nous trouverons rapidement ce qui nous convient mutuellement.",
        "urgent":    "Je suis disponible immediatement et serais heureux d'echanger avec vous a votre convenance.",
        "_default":  "Je reste disponible pour un echange a votre convenance.",
    },
}


def _closing(contrat: str, mode_id: str = "_default") -> str:
    bank = _CLOSINGS.get(contrat, _CLOSINGS["cdi"])
    return bank.get(mode_id, bank.get("_default", "Je reste disponible pour un echange a votre convenance."))


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
            f"Experience en vente conseil et relation client (Printemps Haussmann), "
            f"je suis disponible immediatement et motive pour rejoindre votre equipe."
        )
        corps = (
            "Je suis ponctuel, serieux, et je m'adapte vite a un nouvel environnement. "
            "Le rythme dynamique ne me fait pas peur — c'est justement le contexte "
            "dans lequel je donne le meilleur de moi-meme."
        )

    closing_map = {
        "stage":      "Ce stage serait pour moi l'occasion de contribuer concretement et d'apprendre sur le terrain. Disponible des que possible.",
        "alternance": "Cette alternance m'interesse autant pour progresser que pour apporter quelque chose de concret des le premier jour.",
    }
    closing = closing_map.get(contrat, "Je suis disponible immediatement et serais heureux d'echanger avec vous a votre convenance.")

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
            "pipeline":    "Vous cherchez quelqu'un qui structure et fait tourner un pipeline en autonomie. C'est precisement ce que je fais chez Agence 113 / DEFI GROUPE : 30+ opportunites qualifiees suivies en temps reel, 360 KEUR/mois de portefeuille gere seul.",
            "negociation": "La negociation est au coeur de mon quotidien : cycles B2B avec decideurs, traitement des objections, closing. C'est une competence que j'ai aussi formalisee via la Negotiation Business School (certifie 2025).",
            "hunting":     "Profil hunter — c'est exactement comme ca que je me definis. Identifier, qualifier, pitcher et closer en autonomie sur 360 KEUR/mois sans avoir besoin qu'on me pousse.",
            "partenariat": "Je construis en moyenne 3 partenariats long terme par trimestre chez DEFI GROUPE. Developper des relations durables avec des decideurs, c'est quelque chose que je fais naturellement.",
        },
        "corporate": {
            "reporting":   "Le reporting, je le pratique au quotidien : suivi de 360 KEUR/mois d'activite, dashboards Excel (TCD, formules avancees), synthese hebdomadaire pour la direction.",
            "digital":     "J'ai pilote 5+ projets digitaux de A a Z en autonomie depuis Lisbonne — brief client, design, optimisation UX et mise en ligne. La gestion de projet digital n'est pas theorique pour moi.",
            "contenu":     "J'ai mis en place une strategie de contenu chez GROW 360 qui a genere +35% d'engagement en 6 mois. Planification, production, analyse — j'ai gere les trois en parallele.",
            "budget":      "Le suivi budgetaire est mon quotidien chez DEFI GROUPE : 360 KEUR/mois analyses, ecarts identifies, synthese direction produite chaque semaine.",
        },
        "people": {
            "sourcing":    "Le sourcing actif, je le pratique sur LinkedIn, Indeed et France Travail en parallele. Resultat : 300+ candidats qualifies accueillis par session de recrutement.",
            "onboarding":  "J'ai coordonne des integrations POEI avec France Travail — 15 personnes gerees en parallele sur chaque cycle, du brief administratif au suivi terrain.",
            "entretien":   "Je conduis des entretiens de qualification dans des conditions de volume important. Aller vite tout en evaluant bien — c'est quelque chose que j'ai appris en conditions reelles.",
        },
        "luxe": {
            "premium":     "J'ai travaille aupres d'une clientele internationale haut de gamme au Printemps Haussmann — Europeens, Asiatiques, Moyen-Orient. Le service premium n'est pas une posture, c'est un reflexe.",
            "service":     "L'excellence du service, je l'ai vecue de l'interieur au Printemps Haussmann : chaque detail compte, chaque interaction reflete l'image de la maison. +10% vs objectif mensuel en maintenant ces standards.",
            "fidelisation":"La fidelisation clientele, c'est ce qui separait les bons mois des excellents au Printemps Haussmann. Retravailler un client deja satisfait est la vente la plus efficace.",
        },
    }

    pool = _BRIDGES.get(mode_id, {})
    for kw, phrase in pool.items():
        if kw in desc:
            return phrase
    return ""


# ─── Anti-duplication ────────────────────────────────────────────────────────

def _overlap(a: str, b: str, threshold: int = 3) -> bool:
    """True si les 2 textes partagent trop de mots cles significatifs."""
    stop = {"le","la","les","un","une","des","de","du","et","en","au","aux",
            "ce","que","qui","je","mon","ma","mes","vous","votre","vos",
            "dans","sur","par","pour","avec","sans","est","sont","a","c"}
    wa = {w for w in a.lower().split() if len(w) > 4 and w not in stop}
    wb = {w for w in b.lower().split() if len(w) > 4 and w not in stop}
    return len(wa & wb) >= threshold


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
    closing = _closing(contrat, mode_id)

    # Anti-duplication : supprime bridge si contenu trop proche du pitch
    if bridge and _overlap(bridge, pitch):
        bridge = ""

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
    closing = _closing(contrat, mode_id)

    if bridge and _overlap(bridge, pitch):
        bridge = ""

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
