"""
5 modes intelligents — detectes automatiquement depuis job_title + description.
Source de verite unique pour CV + lettre. Plus de 100 templates metiers.
"""

import hashlib
import amine_profile as _p


# ═══════════════════════════════════════════════════════════════════════════════
# DEFINITION DES 5 MODES
# ═══════════════════════════════════════════════════════════════════════════════

_MODES = {

    # ── 1. SALES ─────────────────────────────────────────────────────────────
    "sales": {
        "detect_kw": [
            "business dev","bizdev","commercial","vente","sales","closing",
            "prospection","sdr","bdr","key account","account manager","kam",
            "grand compte","developpement commercial","hunting","hunter",
            "account executive","revenue","responsable commercial","ventes",
            "charge d'affaires","ingenieur commercial",
        ],
        "cv": {
            "tagline": "Business Developer B2B  |  MBA Manager de Business Unit",
            "summary": (
                "Business Developer B2B chez Agence 113 / DEFI GROUPE, pilotant un "
                "portefeuille a 360 KEUR/mois en autonomie complete. MBA Manager de "
                "Business Unit (PSB Paris, juin 2026). Cycle commercial maitrise de "
                "bout en bout : prospection, qualification, negociation, closing. "
                "HubSpot CRM, Sales Navigator, certifie Negotiation Business School (2025)."
            ),
            "exp_order":   ["defi", "printemps", "wix", "grow"],
            "exp_variant": "commerce",
            "bullets_per": [3, 2, 2, 1],
            "skills": [
                "Business Development B2B (360 KEUR/mois, autonomie complete)",
                "Cycle commercial complet : prospection - negociation - closing",
                "CRM HubSpot (120+ comptes) | LinkedIn Sales Navigator",
                "Certification Negotiation Business School (2025)",
                "FR / AR natifs | EN courant | ES intermediaire",
            ],
        },
        "letter": {
            "hooks": [
                "{poste} chez {entreprise} correspond exactement au terrain sur lequel "
                "je travaille depuis deux ans. Business Developer B2B chez Agence 113 / "
                "DEFI GROUPE, je pilote un portefeuille a 360 KEUR/mois en autonomie "
                "complete, de la prospection au closing. MBA Manager de Business Unit "
                "(PSB Paris, juin 2026), disponible {dispo}.",

                "Deux ans a piloter 360 KEUR/mois en autonomie complete. "
                "C'est ce que j'apporte au poste de {poste} chez {entreprise}. "
                "Business Developer B2B chez Agence 113 / DEFI GROUPE, certifie "
                "Negotiation Business School (2025), MBA Manager de Business Unit "
                "en cours (PSB Paris, juin 2026).",

                "Sur le poste de {poste} chez {entreprise}, mon objectif est precis : "
                "operationnel des la premiere semaine, premiers resultats dans le mois. "
                "Business Developer a 360 KEUR/mois, 30+ leads qualifies/mois, "
                "cycle complet maitrise. MBA en cours (PSB Paris, juin 2026).",
            ],
            "pitch": (
                "Mon experience couvre tout le cycle commercial : sourcing, "
                "qualification, presentation, negociation et closing sur cibles B2B "
                "exigeantes. Je maitrise HubSpot CRM au quotidien (120+ comptes actifs) "
                "et LinkedIn Sales Navigator pour la prospection ciblee. "
                "Certifie Negotiation Business School (2025), multilingue "
                "(FR/AR natifs, EN courant), je delivre en autonomie sans encadrement."
            ),
            "plan_30j": (
                "Dans les 30 premiers jours : cartographier le marche cible, "
                "qualifier 20+ prospects dans le pipeline et identifier les 3 profils "
                "a fort potentiel. Je n'attends pas qu'on me guide — je structure "
                "et j'execute."
            ),
            "human": {
                "grand_groupe": (
                    "Ce qui m'attire chez {entreprise}, c'est la combinaison ressources "
                    "et exigence : les grands groupes forment des commerciaux qui savent "
                    "executer a un niveau que peu d'environnements permettent d'atteindre."
                ),
                "startup": (
                    "J'ai une nette preference pour les environnements ou les decisions "
                    "se prennent vite et ou l'impact commercial est visible immediatement. "
                    "C'est ce que {entreprise} represente pour moi."
                ),
                "pme": (
                    "Ce qui m'attire dans une structure comme {entreprise}, c'est la "
                    "proximite avec les decisions et la capacite de voir directement "
                    "l'impact de son travail commercial."
                ),
            },
        },
    },

    # ── 2. CORPORATE ─────────────────────────────────────────────────────────
    "corporate": {
        "detect_kw": [
            "financial analyst","analyste financier","controle de gestion","fp&a",
            "data analyst","business analyst","consultant","conseil","audit",
            "reporting","digital marketing","marketing manager","product manager",
            "chef de produit","brand manager","category manager","project manager",
            "chef de projet","purchasing","acheteur","procurement","trade marketing",
            "marketing strategique","category","tresorerie","risk","compliance",
            "chef de projet digital","growth","performance marketing","seo","sea",
        ],
        "cv": {
            "tagline": "MBA Manager de Business Unit  |  PSB Paris School of Business",
            "summary": (
                "MBA Manager de Business Unit en cours (PSB Paris, juin 2026). "
                "Pilotage operationnel d'une activite a 360 KEUR/mois : KPIs, "
                "reporting direction, suivi budgetaire. Gestion de projets digitaux "
                "internationaux (Wix, Lisbonne, 5+ clients livres). "
                "Profil analytique oriente business, autonome, multilingue."
            ),
            "exp_order":   ["defi", "wix", "grow", "printemps"],
            "exp_variant": "finance",
            "bullets_per": [3, 2, 2, 1],
            "skills": [
                "Controle de gestion | Pilotage KPIs | Reporting direction (MBA PSB)",
                "Dashboards Excel avances : TCD, formules, analyse d'ecarts",
                "Gestion de projets digitaux intl (5+ clients, Lisbonne 2025)",
                "Community management et strategie de contenu (GROW 360, +35%)",
                "Pack Office avance | Canva | Notion | Wix | Google Suite",
            ],
        },
        "letter": {
            "hooks": [
                "Actuellement en MBA Manager de Business Unit a PSB Paris (soutenance "
                "juin 2026), je pilote en parallele une activite a 360 KEUR/mois : "
                "KPIs, reporting direction, analyse budgetaire. Cette double competence "
                "terrain / academique correspond directement aux besoins du poste de "
                "{poste} chez {entreprise}.",

                "Le poste de {poste} chez {entreprise} requiert quelqu'un qui comprend "
                "le business avant de comprendre les chiffres. C'est exactement la "
                "logique que j'ai construite : MBA Manager de Business Unit en cours "
                "(PSB Paris, juin 2026) et pilotage operationnel de 360 KEUR/mois "
                "en parallele.",

                "Je vous adresse ma candidature pour le poste de {poste} chez "
                "{entreprise}. En MBA Manager de Business Unit (PSB Paris, juin 2026) "
                "et fort d'une experience de pilotage terrain a forts enjeux "
                "(360 KEUR/mois, KPIs, reporting direction), je souhaite mettre "
                "cette double competence analytique et operationnelle a votre service.",
            ],
            "pitch": (
                "Mon MBA m'apporte la rigueur methodologique (controle de gestion, "
                "strategie, finance). Mon experience terrain m'apporte la lecture "
                "business : 360 KEUR/mois a piloter, 5+ projets digitaux livres "
                "en autonomie, +35% d'engagement sur une strategie de contenu en 6 mois. "
                "Ce n'est pas theorie seule ni terrain seul — c'est les deux simultanes."
            ),
            "plan_30j": (
                "Dans les 30 premiers jours : maitrise complete de vos outils et "
                "process, production d'un premier livrable structurant, identification "
                "d'au moins un levier d'optimisation dans vos donnees ou operations."
            ),
            "human": {
                "grand_groupe": (
                    "Les grandes structures forment des profils capables d'executer avec "
                    "rigueur dans des environnements complexes. C'est exactement le niveau "
                    "d'exigence que je recherche en rejoignant {entreprise}."
                ),
                "startup": (
                    "Ce qui m'attire dans un environnement comme {entreprise}, c'est "
                    "la vitesse de decision et la possibilite de voir rapidement l'impact "
                    "concret de son travail analytique."
                ),
                "pme": (
                    "Dans une structure comme {entreprise}, le travail analytique a un "
                    "impact direct et visible — c'est exactement ce que je recherche."
                ),
            },
        },
    },

    # ── 3. PEOPLE / HR ───────────────────────────────────────────────────────
    "people": {
        "detect_kw": [
            "talent acquisition","talent","recrutement","recruitment","hrbp",
            "sourcer","chasseur de tete","rh","ressources humaines",
            "people manager","campus manager","charge de recrutement",
            "responsable rh","generaliste rh","people ops","people partner",
        ],
        "cv": {
            "tagline": "Talent Acquisition & RH Operationnelle  |  MBA Manager de Business Unit",
            "summary": (
                "Recruitment Officer chez Agence 113 / DEFI GROUPE : 300+ candidats "
                "qualifies par session, coordination POEI France Travail (15 integrations "
                "par cycle), sourcing actif multi-canaux. MBA Manager de Business Unit "
                "en cours (PSB Paris, juin 2026). Double profil RH / Business : parle "
                "le langage des managers autant que des candidats. Multilingue."
            ),
            "exp_order":   ["defi", "grow", "wix", "printemps"],
            "exp_variant": "hr",
            "bullets_per": [3, 2, 2, 1],
            "skills": [
                "Recrutement operationnel : 300+ candidats geres par evenement",
                "Coordination POEI France Travail (15 integrations / cycle)",
                "Sourcing actif : LinkedIn, Indeed, France Travail",
                "Animation d'evenements de recrutement et conduite d'entretiens",
                "Habilitation SST — Croix-Rouge Francaise (2024)",
            ],
        },
        "letter": {
            "hooks": [
                "J'ai coordonne en 3 heures un evenement reunissant 300+ candidats "
                "qualifies. C'est le niveau operationnel que j'apporte au poste de "
                "{poste} chez {entreprise}. Recruitment Officer chez Agence 113 / "
                "DEFI GROUPE et MBA Manager de Business Unit en cours (PSB Paris, "
                "juin 2026).",

                "La RH qui delivre, c'est celle qui comprend le business. Mon double "
                "profil — Business Developer B2B en autonomie et Recruitment Officer — "
                "me donne exactement cette double lecture. Le poste de {poste} chez "
                "{entreprise} requiert precisement cette combinaison.",

                "Je vous adresse ma candidature pour le poste de {poste} chez "
                "{entreprise}. Recruitment Officer operationnel (300+ candidats / "
                "session, coordination POEI) et Business Developer B2B, je combines "
                "la rigueur process RH et le sens business — une combinaison rare.",
            ],
            "pitch": (
                "J'ai pilote de A a Z des sessions de recrutement massives : "
                "organisation logistique, accueil et qualification de 300+ candidats, "
                "coordination avec France Travail pour les integrations POEI, "
                "reporting management. En parallele, mon role commercial m'a appris "
                "ce que les managers attendent vraiment des profils integres — "
                "un atout rare et direct dans un poste RH."
            ),
            "plan_30j": (
                "Dans les 30 premiers jours : maitrise du pipeline de candidats actifs, "
                "co-animation d'un premier evenement de recrutement, et identification "
                "des 3 profils prioritaires a sourcer pour vos postes ouverts."
            ),
            "human": {
                "grand_groupe": (
                    "Les grandes structures ont des besoins RH complexes et des volumes "
                    "importants. C'est exactement le contexte dans lequel j'ai prouve "
                    "ma capacite a delivrer chez {entreprise}."
                ),
                "startup": (
                    "Dans un environnement comme {entreprise}, le recrutement est un "
                    "levier de croissance direct. C'est cette vision que j'apporte : "
                    "RH comme business partner, pas comme support."
                ),
                "pme": (
                    "Dans une structure comme {entreprise}, le recrutement a un impact "
                    "direct et mesurable. C'est l'environnement ou j'aime travailler."
                ),
            },
        },
    },

    # ── 4. LUXE / PREMIUM ────────────────────────────────────────────────────
    "luxe": {
        "detect_kw": [
            "luxe","premium","haute couture","joaillerie","horlogerie",
            "brand ambassador","conseiller de vente luxe","retail luxe",
            "fashion","maison","haut de gamme","bijouterie","parfumerie",
            "cosmetique premium","mode","luxury","prestige",
        ],
        "cv": {
            "tagline": "Conseiller Premium  |  Printemps Haussmann  |  MBA Manager de Business Unit",
            "summary": (
                "Sales Advisor premium au Printemps Haussmann : +10% vs objectif "
                "mensuel, accompagnement d'une clientele internationale haut de gamme. "
                "Business Developer B2B en parallele (360 KEUR/mois, DEFI GROUPE). "
                "MBA Manager de Business Unit en cours (PSB Paris, juin 2026). "
                "Presentable, multilingue (FR/AR/EN/ES), codes luxe integres."
            ),
            "exp_order":   ["printemps", "defi", "wix", "grow"],
            "exp_variant": "default",
            "bullets_per": [3, 2, 2, 1],
            "skills": [
                "Vente conseil premium (Printemps Haussmann, +10% vs objectif)",
                "Relation client internationale et haut de gamme",
                "Codes du luxe : service, precision, excellence relationnelle",
                "Multilinguisme : FR / AR natifs, EN courant, ES intermediaire",
                "Adaptabilite culturelle et presentabilite confirmees",
            ],
        },
        "letter": {
            "hooks": [
                "Mon experience de Sales Advisor au Printemps Haussmann — "
                "depassement d'objectifs de +10% mensuel, accompagnement quotidien "
                "d'une clientele internationale premium — m'a donne les codes que "
                "votre univers requiert. Je souhaite les mettre au service du poste "
                "de {poste} chez {entreprise}.",

                "Le luxe n'est pas qu'un secteur, c'est une culture : la precision "
                "du detail, la coherence de l'image, l'excellence du service. Une "
                "culture que j'ai acquise au Printemps Haussmann. Le poste de "
                "{poste} chez {entreprise} en est le prolongement naturel.",

                "Je vous adresse ma candidature pour le poste de {poste} chez "
                "{entreprise}. Fort d'une experience en vente conseil premium "
                "(Printemps Haussmann, +10% vs objectif, clientele internationale "
                "haut de gamme) et d'un MBA en cours (PSB Paris), je corresponds "
                "aux standards d'excellence de votre maison.",
            ],
            "pitch": (
                "Au Printemps Haussmann, j'ai appris que le luxe se joue dans le "
                "detail : la qualite de l'accueil, la precision du conseil produit, "
                "la coherence de chaque interaction avec l'image de la marque. J'ai "
                "aussi appris a adapter mon approche a des clienteles de cultures "
                "tres differentes — Europeens, Asiatiques, Moyen-Orient. "
                "Multilingue (FR/AR/EN/ES), presentable, naturellement a l'aise "
                "dans les environnements d'excellence."
            ),
            "plan_30j": (
                "Dans les 30 premiers jours : maitrise complete de votre univers "
                "produit et des codes de la maison, integration dans les processus "
                "de votre equipe, et premier deliverable autonome aupres de "
                "votre clientele."
            ),
            "human": {
                "grand_groupe": (
                    "Rejoindre {entreprise}, c'est integrer une maison qui a fait de "
                    "l'excellence une culture. C'est precisement ce niveau d'exigence "
                    "qui me motive."
                ),
                "startup": (
                    "Ce qui m'attire chez {entreprise}, c'est l'ambition de "
                    "democratiser le premium sans compromis sur la qualite."
                ),
                "pme": (
                    "Ce qui m'attire dans une maison comme {entreprise}, c'est "
                    "l'authenticite — la passion du produit avant tout."
                ),
            },
        },
    },

    # ── 5. URGENT ────────────────────────────────────────────────────────────
    "urgent": {
        "detect_kw": [],  # detecte via SIMPLE_JOB_KEYWORDS
        "cv": {
            "tagline": "Profil operationnel & relation client  |  Disponible immediatement",
            "summary": None,  # genere dynamiquement dans cv_gen_france
            "exp_order":   ["printemps", "defi", "grow", "wix"],
            "exp_variant": "default",
            "bullets_per": [2, 2, 1, 1],
            "skills": [
                "Vente et conseil client (B2B et retail premium)",
                "Relation client et fidelisation",
                "Travail en equipe et autonomie terrain",
                "Outils : Excel, Canva, Google Suite",
                "Multilinguisme : FR / AR / EN / ES",
            ],
        },
        "letter": {
            "hooks": [],
            "pitch": "",
            "plan_30j": "",
            "human": {"grand_groupe": "", "startup": "", "pme": ""},
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# DETECTION ENTREPRISE
# ═══════════════════════════════════════════════════════════════════════════════

_BIG_GROUPS = {
    "lvmh","loreal","l'oreal","sanofi","bnp","axa","societe generale","total",
    "totalenergies","michelin","renault","stellantis","danone","hermes","chanel",
    "kering","dior","air france","edf","engie","orange","air liquide","saint-gobain",
    "schneider","legrand","thales","safran","airbus","bouygues","vinci","capgemini",
    "sopra","deloitte","pwc","kpmg","mckinsey","bain","bcg","accenture","hsbc",
    "natixis","carrefour","leclerc","decathlon","leroy merlin","fnac","galeries lafayette",
    "printemps","sephora","gucci","cartier","bulgari","tiffany","yves saint laurent",
}

_STARTUP_KW = {
    "startup","scale-up","scaleup","series a","series b","seed","fintech","proptech",
    "saas","growth hacking","product-led","levee de fonds","agile squad",
}


def detect_company_type(entreprise: str, description: str = "") -> str:
    e = (entreprise or "").lower()
    d = (description or "").lower()
    if any(b in e for b in _BIG_GROUPS):
        return "grand_groupe"
    if any(s in f"{e} {d}" for s in _STARTUP_KW):
        return "startup"
    return "pme"


# ═══════════════════════════════════════════════════════════════════════════════
# API PUBLIQUE
# ═══════════════════════════════════════════════════════════════════════════════

def detect_mode(titre: str, description: str = "") -> str:
    t    = (titre or "").lower()
    full = f"{t} {(description or '').lower()}"

    if any(kw in t for kw in _p.SIMPLE_JOB_KEYWORDS):
        return "urgent"

    scores: dict[str, int] = {m: 0 for m in _MODES if m != "urgent"}
    for mode_id, cfg in _MODES.items():
        if mode_id == "urgent":
            continue
        for kw in cfg["detect_kw"]:
            if kw in t:
                scores[mode_id] += 2
            elif kw in full:
                scores[mode_id] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "sales"


def get_mode_cv(titre: str, description: str = "") -> dict:
    mode_id = detect_mode(titre, description)
    return {**_MODES[mode_id]["cv"], "id": mode_id}


def get_mode_letter(titre: str, description: str = "") -> dict:
    mode_id = detect_mode(titre, description)
    return {**_MODES[mode_id]["letter"], "id": mode_id}


def hook_for(mode_id: str, titre: str, entreprise: str,
             contrat: str, offer: dict) -> str:
    hooks = _MODES[mode_id]["letter"]["hooks"]
    if not hooks:
        return ""
    key = f"{offer.get('titre','')}{offer.get('entreprise','')}{offer.get('description','')[:40]}"
    idx = int(hashlib.md5(key.encode()).hexdigest(), 16) % len(hooks)
    _C = {
        "cdi":        "en CDI",
        "alternance": "en alternance",
        "stage":      "pour un stage",
    }.get(contrat, "")
    dispo = {
        "cdi":        "en CDI, juin 2026",
        "alternance": "en alternance, sept. 2026",
        "stage":      "pour un stage, juil. 2026",
    }.get(contrat, "")
    return (hooks[idx]
            .format(
                poste=titre or "ce poste",
                entreprise=entreprise or "votre entreprise",
                contrat_label=_C,
                dispo=dispo,
            ))


def human_phrase(mode_id: str, company_type: str, entreprise: str) -> str:
    phrases = _MODES[mode_id]["letter"].get("human", {})
    tmpl = phrases.get(company_type, phrases.get("pme", ""))
    return tmpl.format(entreprise=entreprise or "votre structure") if tmpl else ""


# ═══════════════════════════════════════════════════════════════════════════════
# ATS KEYWORD INJECTION
# ═══════════════════════════════════════════════════════════════════════════════

_ATS_POOL: dict[str, dict[str, str]] = {
    "sales": {
        "pipeline":          "pipeline commercial",
        "hunting":           "approche hunting",
        "crm":               "CRM HubSpot",
        "b2b":               "B2B",
        "negociation":       "negociation",
        "prospection":       "prospection active",
        "closing":           "closing",
        "partenariat":       "partenariats strategiques",
        "key account":       "gestion grands comptes",
        "portefeuille":      "portefeuille clients",
        "upsell":            "upsell / cross-sell",
        "forecast":          "forecast commercial",
    },
    "corporate": {
        "budget":            "suivi budgetaire 360 KEUR/mois",
        "forecast":          "forecast et analyse d'ecarts",
        "reporting":         "reporting direction",
        "kpi":               "pilotage KPIs",
        "consolidation":     "notions consolidation (MBA)",
        "data":              "lecture data / dashboards",
        "digital":           "projets digitaux intl (Lisbonne)",
        "contenu":           "strategie de contenu (+35% engagement)",
        "go-to-market":      "demarche go-to-market (MBA)",
        "roadmap":           "lecture roadmap produit",
        "benchmark":         "benchmark et analyse competitive",
    },
    "people": {
        "sourcing":          "sourcing actif multi-canaux",
        "assessment":        "evaluation et qualification candidats",
        "onboarding":        "coordination POEI / onboarding",
        "vivier":            "gestion de vivier candidats",
        "employer brand":    "marque employeur",
        "entretien":         "conduite d'entretiens",
        "integration":       "suivi integration collaborateurs",
    },
    "luxe": {
        "clientele premium": "clientele internationale premium (Printemps)",
        "service":           "excellence du service client",
        "conseil":           "vente conseil en environnement premium",
        "fidelisation":      "fidelisation clientele haut de gamme",
        "codes":             "codes luxe integres",
        "international":     "clientele internationale multi-cultures",
    },
}


def ats_inject(summary: str, mode_id: str, description: str) -> str:
    """Injecte jusqu'a 3 mots-cles ATS detectes dans la description dans le resume."""
    desc  = (description or "").lower()
    pool  = _ATS_POOL.get(mode_id, {})
    found = [label for kw, label in pool.items() if kw in desc][:3]
    if not found:
        return summary
    return summary.rstrip(".") + ". Competences matchees : " + " · ".join(found) + "."
