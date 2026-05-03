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
            # Variantes terrain pro
            "responsable zone","animateur commercial","animateur des ventes",
            "animateur reseau","charge de relation client","relation client",
            "charge de clientele","conseiller commercial","attache commercial",
            "directeur commercial","vp sales","head of sales","head of revenue",
            "sales manager","territory manager","area manager","regional manager",
            "responsable secteur","chef des ventes","inspecteur commercial",
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
                "Le poste de {poste} chez {entreprise} correspond directement "
                "au terrain sur lequel je travaille depuis deux ans. Business Developer "
                "B2B chez Agence 113 / DEFI GROUPE, je pilote un portefeuille a "
                "360 KEUR/mois en autonomie complete, du sourcing au closing. "
                "MBA Manager de Business Unit (PSB Paris, juin 2026), disponible {dispo}.",

                "360 KEUR/mois en autonomie complete — c'est le niveau que j'apporte "
                "au poste de {poste} chez {entreprise}. Business Developer B2B depuis "
                "deux ans chez Agence 113 / DEFI GROUPE, certifie Negotiation Business "
                "School (2025), MBA Manager de Business Unit en cours (PSB Paris, juin 2026).",

                "Sur le poste de {poste} chez {entreprise}, mon objectif est simple : "
                "operationnel des la premiere semaine, premiers resultats concrets dans "
                "le mois. Cycle commercial complet maitrise (30+ leads/mois, 360 KEUR/mois "
                "pilotes), MBA en cours (PSB Paris, juin 2026).",
            ],
            "pitch": (
                "Je couvre tout le cycle commercial de bout en bout : sourcing et "
                "qualification de leads, presentation, negociation et closing sur "
                "cibles B2B. HubSpot CRM (120+ comptes actifs) et LinkedIn Sales "
                "Navigator au quotidien. Certifie Negotiation Business School (2025), "
                "multilingue (FR/AR natifs, EN courant) — je livre en autonomie, "
                "sans avoir besoin d'etre encadre."
            ),
            "plan_30j": (
                "Dans les 30 premiers jours : cartographier les cibles prioritaires, "
                "qualifier 20+ prospects et alimenter le pipeline en autonomie. "
                "Je n'attends pas les instructions pour commencer — je structure et j'execute."
            ),
            "human": {
                "grand_groupe": (
                    "{entreprise} est exactement l'environnement dans lequel je veux "
                    "progresser : exigence elevee, cycles commerciaux complexes, "
                    "interlocuteurs de haut niveau. C'est ce qui fait sortir du lot "
                    "un commercial en deux ans."
                ),
                "startup": (
                    "Dans un environnement comme {entreprise}, chaque deal compte "
                    "doublement : pour le revenue et pour la credibilite du produit. "
                    "C'est exactement la pression dans laquelle je performe le mieux."
                ),
                "pme": (
                    "Ce qui me motive dans une structure comme {entreprise} : "
                    "l'impact est direct, les bons resultats se voient immediatement, "
                    "et il y a une vraie marge de manoeuvre pour celui qui execute."
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
            # Communication / evenementiel / coordination
            "communication","charge de communication","responsable communication",
            "evenementiel","evenement","coordinateur","charge de mission",
            "charge de projet","responsable marketing","marketing digital",
            "chef de mission","gestionnaire de projet","content manager",
            "responsable contenu","charge de contenu","media","relations presse",
            # Finance / gestion
            "gestionnaire","analyste","conseiller en gestion","patrimoine",
            "conseiller financier","conseiller bancaire","charge de clientele pro",
            "teleconseiller pro","responsable financier",
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
                    "Rejoindre {entreprise}, c'est travailler dans un environnement ou "
                    "la rigueur analytique est non negociable. C'est precisement le niveau "
                    "de standards que mon MBA et mon experience operationnelle m'ont prepare a tenir."
                ),
                "startup": (
                    "Dans une structure comme {entreprise}, l'analyse n'est pas un reporting "
                    "de plus — c'est ce qui guide les decisions rapides. C'est l'utilite "
                    "concrete du travail analytique qui me motive."
                ),
                "pme": (
                    "Ce qui m'attire chez {entreprise} : la taille permet d'avoir "
                    "une vraie vue d'ensemble du business, pas juste un silo. "
                    "Je travaille mieux quand je comprends pourquoi je produis ce que je produis."
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
                "session, coordination POEI) et Business Developer B2B, je combine "
                "rigueur process RH et lecture business — une combinaison rare "
                "dans les profils RH.",
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
                    "Les grands groupes comme {entreprise} ont la particularite d'avoir "
                    "des enjeux RH a la fois massifs et tres structures. C'est le contexte "
                    "dans lequel j'ai prouve que je peux tenir un volume important "
                    "sans perdre en qualite de selection."
                ),
                "startup": (
                    "Dans une startup comme {entreprise}, un bon recrutement peut "
                    "changer la trajectoire d'une equipe entiere. Je ne recrute pas "
                    "pour remplir des postes — je recrute pour construire quelque chose."
                ),
                "pme": (
                    "Dans une structure comme {entreprise}, chaque recrutement compte "
                    "vraiment — il n'y a pas de marge pour une mauvaise decision. "
                    "C'est la precision que j'apporte."
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
                    "{entreprise} represente pour moi l'aboutissement d'une demarche "
                    "deja commencee au Printemps Haussmann : servir une clientele qui "
                    "n'accepte pas l'approximation. Je suis pret a m'y engager "
                    "avec le meme niveau d'exigence."
                ),
                "startup": (
                    "Ce qui m'interesse chez {entreprise}, c'est la volonte de "
                    "construire quelque chose de nouveau dans un univers qui existe "
                    "depuis longtemps. Cette tension entre heritage et innovation, "
                    "c'est exactement ce qui rend le secteur stimulant."
                ),
                "pme": (
                    "Dans une maison comme {entreprise}, le rapport au produit est "
                    "different — plus direct, plus authentique. C'est ce type de "
                    "relation au metier que je recherche."
                ),
            },
        },
    },

    # ── 5. URGENT ────────────────────────────────────────────────────────────
    "urgent": {
        "detect_kw": [],  # detecte via SIMPLE_JOB_KEYWORDS apres scoring
        "cv": {
            "tagline": "Profil operationnel & relation client  |  Disponible immediatement",
            "summary": None,  # genere dynamiquement dans cv_gen_france
            "exp_order":   ["printemps", "defi"],
            "exp_variant": "default",
            "bullets_per": [2, 2],
            "skills": [
                "Vente et relation client (Printemps Haussmann, retail premium)",
                "A l'aise en equipe et autonomie terrain",
                "Multilingue : FR / AR natifs, EN courant, ES intermediaire",
                "Outils : Excel, Canva, Google Suite",
                "Disponible immediatement — Paris et IDF — Permis B",
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
    # France CAC40 + retail + luxe
    "lvmh","loreal","l'oreal","l oreal","sanofi","bnp","axa","societe generale","total",
    "totalenergies","michelin","renault","stellantis","danone","hermes","chanel",
    "kering","dior","air france","edf","engie","orange","air liquide","saint-gobain",
    "schneider","legrand","thales","safran","airbus","bouygues","vinci","capgemini",
    "sopra","deloitte","pwc","kpmg","mckinsey","bain","bcg","accenture","hsbc",
    "natixis","carrefour","leclerc","decathlon","leroy merlin","fnac","galeries lafayette",
    "printemps","sephora","gucci","cartier","bulgari","tiffany","yves saint laurent",
    "zara","inditex","h&m","uniqlo","saint laurent","van cleef","dior","givenchy",
    # Tech & conseil international
    "salesforce","google","microsoft","amazon","apple","meta","netflix","oracle",
    "sap","ibm","cisco","adobe","linkedin","slack","hubspot","zendesk","workday",
    "servicenow","stripe","adyen","paypal","spotify","uber","airbnb","booking",
    "doctolib","blablacar","leboncoin","cdiscount","rakuten","veepee",
    "publicis","havas","dentsu","wpp","omnicom","ipg",
    # Banque / assurance
    "credit agricole","bnp paribas","societe generale","lcl","cic","bred",
    "allianz","generali","covea","maif","macif","mma","groupama","ag2r",
    # RH / recrutement
    "adp","manpower","randstad","adecco","hays","michael page","robert half",
    "korn ferry","spencer stuart","egon zehnder","apec","france travail",
}

_STARTUP_KW = {
    "startup","scale-up","scaleup","series a","series b","seed","fintech","proptech",
    "saas","growth hacking","product-led","levee de fonds","agile squad",
}


def _norm(s: str) -> str:
    """Lowercase + strip accents courants pour comparaison robuste."""
    return (s.lower()
             .replace("é","e").replace("è","e").replace("ê","e")
             .replace("à","a").replace("â","a")
             .replace("ô","o").replace("û","u").replace("î","i")
             .replace("'","'").replace("’","'"))


def detect_company_type(entreprise: str, description: str = "") -> str:
    e = _norm(entreprise or "")
    d = _norm(description or "")
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

    # Score all non-urgent modes first — a real match always wins over urgent
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
    if scores[best] > 0:
        return best

    # No mode matched → urgent only if genuine simple-job keyword in title
    if any(kw in t for kw in _p.SIMPLE_JOB_KEYWORDS):
        return "urgent"

    return "sales"


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
    return summary.rstrip(".") + ". Mots-cles detectes : " + " | ".join(found) + "."
