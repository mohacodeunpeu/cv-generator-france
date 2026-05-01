"""
Lettre de motivation France — CDI / alternance / stage.
Adapte du generateur VIE : pas de contexte pays, pas de duree de mission.
Ton : corporate francais, concret, personnel.
"""

import hashlib
import io
import os
import tempfile

from fpdf import FPDF

from cv_gen_france import detect_role, is_simple_job, PROFILE, _safe
import amine_profile as _p

# ─── Rotation deterministe des hooks ─────────────────────────────────────────

def _hook_index(offer: dict, n: int) -> int:
    key = f"{offer.get('titre', '')}{offer.get('entreprise', '')}{offer.get('description', '')[:50]}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % n


# ─── Hooks d'ouverture par role + contrat ────────────────────────────────────

def _hook(role: str, titre: str, entreprise: str, contrat: str, offer: dict) -> str:
    poste = (titre or "ce poste").strip()
    idx   = _hook_index(offer, 4)

    _C = {
        "cdi":        "rejoindre votre equipe en CDI",
        "alternance": "rejoindre votre equipe en alternance",
        "stage":      "effectuer un stage au sein de votre equipe",
    }.get(contrat, "rejoindre votre equipe")

    if role in ("product_marketing", "digital_marketing"):
        variants = [
            (
                f"C'est avec un fort interet que je vous adresse ma candidature "
                f"pour le poste de {poste} chez {entreprise}. Diplome en cours de "
                f"MBA Manager de Business Unit a PSB Paris (soutenance juin 2026), "
                f"avec une experience concrete en gestion de projets digitaux a "
                f"l'international (Wix, Lisbonne) et en community management "
                f"(GROW 360, Paris), je souhaite {_C}."
            ),
            (
                f"Mon double profil - gestion de projets digitaux a l'international "
                f"et community management - correspond directement aux besoins du "
                f"poste de {poste} chez {entreprise}. En MBA Manager de Business "
                f"Unit a PSB Paris (juin 2026), je cherche a mettre ces competences "
                f"au service d'une equipe ambitieuse."
            ),
            (
                f"Le marketing qui laisse des traces, c'est celui qui se mesure. "
                f"C'est la culture que j'ai construite chez GROW 360 (Paris) et "
                f"en projets clients depuis Lisbonne : briefer, produire, mesurer, "
                f"ajuster. Le poste de {poste} chez {entreprise} est le terrain "
                f"ideal pour mettre cette discipline au service de votre equipe."
            ),
            (
                f"Chaque projet digital que j'ai mene - de Lisbonne a Paris - a "
                f"confirme une chose : je m'epanouis la ou marketing, produit et "
                f"donnees se croisent. Le poste de {poste} chez {entreprise} est "
                f"exactement cet environnement. MBA Manager de Business Unit "
                f"(PSB Paris, juin 2026), disponible pour {_C}."
            ),
        ]
        return variants[idx % len(variants)]

    if role in ("financial_analyst", "data_analyst"):
        variants = [
            (
                f"Je me permets de vous adresser ma candidature pour le poste de "
                f"{poste} chez {entreprise}. En MBA Manager de Business Unit a "
                f"PSB Paris (juin 2026) et actuellement en charge du pilotage "
                f"operationnel d'une activite a 360 KEUR/mois, je souhaite valoriser "
                f"cette double culture analyse/business au service de vos enjeux."
            ),
            (
                f"La finance n'est utile que si elle eclaire les decisions business. "
                f"C'est cette conviction qui guide ma candidature pour le poste de "
                f"{poste} chez {entreprise}. MBA Manager de Business Unit (PSB Paris, "
                f"juin 2026), je pilote au quotidien des indicateurs a forts enjeux."
            ),
            (
                f"Deux ans a piloter une activite a forts enjeux chiffres m'ont "
                f"appris a lire un business dans ses donnees, pas seulement dans "
                f"ses resultats. C'est cette lecture que je veux developper en "
                f"rejoignant {entreprise} sur le poste de {poste}."
            ),
            (
                f"Les meilleures decisions financieres viennent de gens qui ont "
                f"vecu le business operationnellement. En pilotant 360 KEUR/mois "
                f"au quotidien, j'ai construit cette double lecture qui fait la "
                f"difference. C'est ce que je veux apporter a {entreprise}."
            ),
        ]
        return variants[idx % len(variants)]

    if role == "purchasing":
        variants = [
            (
                f"Je vous adresse ma candidature pour le poste de {poste} chez "
                f"{entreprise}. Forme a la negociation en pratique (Business "
                f"Developer B2B, 360 KEUR/mois) et en formation (Negotiation "
                f"Business School certifie 2025, MBA Business Unit en cours), "
                f"je souhaite transposer cette competence aux enjeux achats."
            ),
            (
                f"Negocier, c'est comprendre ce que l'autre partie veut vraiment "
                f"avant son prix. C'est l'approche que j'applique depuis deux ans "
                f"en Business Development B2B, et que je souhaite mettre au service "
                f"du poste de {poste} chez {entreprise}."
            ),
            (
                f"Maitriser une negociation, c'est comprendre les contraintes de "
                f"l'autre partie avant de defendre les siennes. C'est l'approche "
                f"que j'ai construite en B2B et que je veux transposer aux achats "
                f"en rejoignant {entreprise} sur le poste de {poste}."
            ),
            (
                f"Du B2B aux achats, la logique reste la meme : comprendre les "
                f"contraintes de l'autre pour mieux structurer les siennes. "
                f"Certifie Negotiation Business School (2025), Business Developer "
                f"a 360 KEUR/mois, je postule pour le poste de {poste} chez "
                f"{entreprise}."
            ),
        ]
        return variants[idx % len(variants)]

    if role == "hr":
        variants = [
            (
                f"Je suis particulierement motive par le poste de {poste} chez "
                f"{entreprise}. Recruitment Officer chez Agence 113 / DEFI GROUPE "
                f"ou je gere des sessions reunissant plus de 300 candidats, et "
                f"en MBA Manager de Business Unit (PSB Paris, juin 2026), je "
                f"combine experience operationnelle RH et hauteur strategique."
            ),
            (
                f"Avoir gere en 3 heures un evenement reunissant 300+ candidats "
                f"m'a appris une chose : la RH qui marche, c'est celle qui comprend "
                f"le business. C'est pourquoi le poste de {poste} chez {entreprise} "
                f"me correspond directement."
            ),
            (
                f"La RH qui delivre, c'est celle qui parle le langage du business. "
                f"Mon double profil - Business Developer B2B en autonomie et "
                f"Recruitment Officer - me donne exactement cette double lecture "
                f"que le poste de {poste} chez {entreprise} requiert."
            ),
            (
                f"300 candidats en un evenement, 15 integrations POEI geries en "
                f"parallele : c'est la RH operationnelle que je pratique au "
                f"quotidien. Le poste de {poste} chez {entreprise} correspond "
                f"exactement a ce que je veux developper."
            ),
        ]
        return variants[idx % len(variants)]

    # Commerce / Sales / Key Account / BizDev / generic
    if contrat == "alternance":
        variants = [
            (
                f"Actuellement Business Developer B2B chez Agence 113 / DEFI "
                f"GROUPE (360 KEUR/mois), je complete mon MBA Manager de Business "
                f"Unit a PSB Paris (soutenance juin 2026) et cherche une alternance "
                f"qui me permette d'appliquer mes competences commerciales chez "
                f"{entreprise} sur le poste de {poste}."
            ),
            (
                f"Deux ans de terrain en Business Development m'ont donne une chose "
                f"rare : la capacite a etre operationnel des la premiere semaine. "
                f"C'est ce que j'apporte a {entreprise} sur le poste de {poste}, "
                f"en complement du recul strategique de mon MBA."
            ),
            (
                f"Une alternance, c'est un echange : j'apporte une experience "
                f"terrain solide (B2B, 360 KEUR/mois, autonomie complete), "
                f"{entreprise} m'apporte la profondeur strategique d'un grand "
                f"groupe. Le poste de {poste} est exactement cet echange."
            ),
            (
                f"360 KEUR/mois en autonomie complete, c'est le terrain que j'ai "
                f"eu avant meme de finir mon MBA. C'est cette maturite que je "
                f"souhaite mettre au service de {entreprise} sur le poste de {poste}."
            ),
        ]
        return variants[idx % len(variants)]

    if contrat == "stage":
        variants = [
            (
                f"Je vous adresse ma candidature pour le poste de {poste} chez "
                f"{entreprise}. En MBA Manager de Business Unit a PSB Paris "
                f"(juin 2026) et fort d'une experience terrain en Business "
                f"Development B2B (360 KEUR/mois), je souhaite contribuer "
                f"concretement a vos projets lors de ce stage."
            ),
            (
                f"Un stage, c'est la possibilite de confronter ce qu'on sait "
                f"faire a la realite d'un grand groupe. Avec deux ans de terrain "
                f"en B2B et un MBA en cours, je suis en mesure d'etre operationnel "
                f"des la premiere semaine chez {entreprise} sur le poste de {poste}."
            ),
            (
                f"Mon objectif pour ce stage chez {entreprise} est simple : "
                f"apporter des resultats concrets sur le poste de {poste}, "
                f"pas juste observer. Business Developer B2B en autonomie "
                f"(360 KEUR/mois), MBA Manager de Business Unit en cours "
                f"(PSB Paris, juin 2026)."
            ),
            (
                f"Chaque experience que j'ai eue - B2B, projets clients intl, "
                f"community management - m'a appris a livrer en autonomie. "
                f"C'est cette posture que je souhaite apporter a {entreprise} "
                f"sur le poste de {poste}."
            ),
        ]
        return variants[idx % len(variants)]

    # CDI commerce/sales/generic
    variants = [
        (
            f"Actuellement Business Developer B2B chez Agence 113 / DEFI GROUPE, "
            f"ou je pilote un portefeuille generant 360 KEUR/mois, et diplome en "
            f"cours de MBA Manager de Business Unit a PSB Paris (soutenance juin "
            f"2026), je souhaite mettre mon experience commerciale au service de "
            f"votre equipe sur le poste de {poste} chez {entreprise}."
        ),
        (
            f"360 KEUR/mois en autonomie complete : c'est le niveau d'engagement "
            f"que j'apporte depuis deux ans. Pour le poste de {poste} chez "
            f"{entreprise}, je suis pret a livrer des resultats concrets depuis "
            f"le premier mois. MBA Manager de Business Unit (PSB Paris, juin 2026)."
        ),
        (
            f"J'ai pris deux ans pour construire une experience B2B solide avant "
            f"de postuler a des postes comme celui-ci. Aujourd'hui, le poste de "
            f"{poste} chez {entreprise} est la prochaine etape logique. Business "
            f"Developer a 360 KEUR/mois, MBA en cours (PSB Paris, juin 2026)."
        ),
        (
            f"Sur le poste de {poste} chez {entreprise}, mon objectif est clair : "
            f"etre operationnel des la premiere semaine et delivrer des resultats "
            f"mesurables. Business Developer B2B (360 KEUR/mois) et MBA Manager "
            f"de Business Unit en cours (PSB Paris, juin 2026)."
        ),
    ]
    return variants[idx % len(variants)]


# ─── Pitch par role ───────────────────────────────────────────────────────────

def _pitch(role: str) -> str:
    if role == "product_marketing":
        return (
            "Mon experience en gestion de projets digitaux pour clients "
            "internationaux (Lisbonne), combinee aux modules de strategie "
            "produit et d'analyse de marche de mon MBA, me permet de comprendre "
            "rapidement les enjeux de positionnement, de pricing et de cycle de "
            "vie produit. J'ai egalement coordonne des actions de notoriete et "
            "d'engagement chez GROW 360 (Paris), ce qui m'a appris a transformer "
            "un brief en actions mesurables avec un ROI clair."
        )
    if role == "digital_marketing":
        return (
            "Mon experience de community management chez GROW 360 (Paris) et de "
            "gestion de projets digitaux pour clients internationaux m'a appris "
            "a piloter des campagnes multicanales avec des KPIs concrets : "
            "engagement, taux de conversion, ROI campagne. Je sais structurer "
            "une strategie de contenu et l'ajuster en continu selon les donnees."
        )
    if role == "financial_analyst":
        return (
            "Mon MBA Manager de Business Unit a PSB Paris inclut des modules "
            "approfondis de controle de gestion, analyse de la performance et "
            "lecture financiere strategique. En parallele, je pilote au quotidien "
            "une activite a forts enjeux (360 KEUR/mois) : KPIs commerciaux, "
            "reporting, lecture business des chiffres. Cette double competence "
            "finance/business est un atout direct pour le partenariat avec les "
            "equipes operationnelles."
        )
    if role == "data_analyst":
        return (
            "Forme au pilotage par la donnee dans mon MBA, je manipule au quotidien "
            "des indicateurs commerciaux pour orienter mes decisions. Je sais "
            "transformer un dataset brut en insight actionnable en commencant par "
            "les bonnes questions business avant de plonger dans la technique. "
            "Mon objectif : des analyses qui servent les decideurs."
        )
    if role == "purchasing":
        return (
            "Habitue a negocier des partenariats strategiques avec des enjeux "
            "financiers concrets (portefeuille B2B a 360 KEUR/mois), je transpose "
            "cette approche cote achats : recherche de fournisseurs, comparaison "
            "TCO, negociation de conditions, suivi de la performance. Mon "
            "multilinguisme (FR/AR natifs, EN courant, ES intermediaire) facilite "
            "les relations avec les fournisseurs internationaux."
        )
    if role == "key_account":
        return (
            "Business Developer B2B chez Agence 113 / DEFI GROUPE avec un "
            "portefeuille a 360 KEUR/mois, je gere des comptes strategiques en "
            "mode hunter-farmer. Cycle de vente long, prospection au closing, "
            "gestion de la relation post-signature : ce mode de travail se "
            "transpose directement aux exigences d'un poste Key Account."
        )
    if role == "business_dev":
        return (
            "Business Developer B2B chez Agence 113 / DEFI GROUPE, je pilote "
            "une activite a 360 KEUR/mois en autonomie complete sur tout le "
            "cycle commercial : prospection, qualification, negociation, closing. "
            "Je maitrise HubSpot CRM et LinkedIn Sales Navigator au quotidien et "
            "sais structurer un pipeline de A a Z."
        )
    if role == "sales":
        return (
            "Business Developer B2B chez Agence 113 / DEFI GROUPE avec 360 KEUR "
            "de CA mensuel, je sais transformer une opportunite froide en client "
            "signe. Maitrise du cycle complet, des outils CRM (HubSpot, Sales "
            "Navigator) et de la negociation B2B sur des cibles exigeantes."
        )
    if role == "hr":
        return (
            "J'ai pilote operationnellement des process de recrutement a grande "
            "echelle : organisation d'evenements reunissant 300+ candidats, "
            "sourcing actif, coordination du service POEI, entretiens, reporting. "
            "Cette double experience RH/business est rare et m'a appris a parler "
            "le langage des managers comme des candidats."
        )
    return (
        "Mon parcours combine pilotage operationnel B2B en France et gestion de "
        "projets internationaux depuis Lisbonne, avec un MBA Manager de Business "
        "Unit (PSB Paris, juin 2026) qui m'a apporte methodes et rigueur. "
        "J'apporte autonomie, orientation resultats et adaptabilite."
    )


# ─── Livrables concrets ───────────────────────────────────────────────────────

def _deliverables(role: str) -> str:
    if role == "product_marketing":
        return (
            "Concretement, je peux contribuer des le debut : lecture rapide des "
            "etudes de marche pour nourrir les decisions produit, coordination "
            "operationnelle entre marketing, ventes et R&D, adaptation du "
            "positionnement aux specificites des marches locaux."
        )
    if role == "digital_marketing":
        return (
            "Concretement : prise en main de vos campagnes digitales avec lecture "
            "KPI/ROI rigoureuse, production de contenu adapte a vos cibles, "
            "ajustement en continu selon les donnees reelles."
        )
    if role == "financial_analyst":
        return (
            "Concretement : construction de reportings clairs et actionnables pour "
            "vos decideurs, participation aux exercices de budget et forecast, "
            "pont finance/operationnels grace a mon experience business terrain."
        )
    if role == "data_analyst":
        return (
            "Concretement : industrialisation de reportings reguliers sur Excel / "
            "Power BI, identification des insights actionnables dans vos donnees, "
            "traduction des analyses en recommandations claires pour les decideurs."
        )
    if role == "purchasing":
        return (
            "Concretement : analyses categorielles pour eclairer les decisions "
            "achats, negociation directe avec des fournisseurs en plusieurs langues, "
            "suivi structure de la performance fournisseurs."
        )
    if role == "key_account":
        return (
            "Concretement : prise en main rapide d'un portefeuille de comptes "
            "strategiques, deploiement d'une approche structuree (plan de compte, "
            "business review), negociation des conditions cadres."
        )
    if role in ("business_dev", "sales"):
        return (
            "Concretement : ouverture de nouveaux comptes ou developpement d'un "
            "portefeuille existant, structuration du pipeline avec une rigueur "
            "d'execution prouvee, closing de deals complexes."
        )
    if role == "hr":
        return (
            "Concretement : pilotage de process de recrutement de A a Z, animation "
            "d'evenements employeur, lien RH/business grace a mon experience "
            "operationnelle."
        )
    return "Concretement : rigueur, autonomie et resultats mesurables des le debut."


# ─── Pont offre <-> experience ────────────────────────────────────────────────

def _bridge(offer: dict, role: str) -> str:
    desc     = (offer.get("description") or "").lower()
    _GENERIC = {"reporting", "analyse", "budget", "forecast", "dashboard", "kpi",
                "suivi", "planification", "gestion", "coordination"}

    _ACTIONS_MARKETING = ["campagne", "contenu", "engagement", "seo", "sea",
                          "social", "acquisition", "conversion", "analytics"]
    _ACTIONS_COMMERCE  = ["prospection", "negociation", "closing", "partenariat",
                          "developpement", "client", "portefeuille", "pipeline"]
    _ACTIONS_FINANCE   = ["consolidation", "forecast", "budget", "controle",
                          "audit", "reporting", "analyse", "rentabilite"]

    if role in ("product_marketing", "digital_marketing"):
        found = next((a for a in _ACTIONS_MARKETING if a in desc), "")
        if found:
            return (
                f"La dimension {found} que vous portez correspond aux missions "
                f"que j'ai menees de bout en bout : a Lisbonne (Wix, projets "
                f"digitaux clients) et a Paris (GROW 360, engagement et contenu), "
                f"j'ai appris a transformer un brief en resultats mesurables."
            )
        return (
            "Le pilotage marketing de bout en bout que vous decrivez correspond "
            "exactement aux projets que j'ai menes entre Lisbonne et Paris."
        )

    if role in ("financial_analyst", "data_analyst"):
        found = next((a for a in _ACTIONS_FINANCE if a in desc), "")
        if found:
            return (
                f"La dimension {found} au coeur de ce poste correspond directement "
                f"a ce que je pratique : suivi budgetaire d'une activite a "
                f"360 KEUR/mois, dashboards Excel avances, reporting mensuel direction."
            )
        return (
            "Le pilotage financier que vous portez correspond a ce que je pratique "
            "au quotidien : 360 KEUR/mois suivis en temps reel, reporting direction, "
            "lecture business des indicateurs."
        )

    if role in ("business_dev", "sales", "key_account"):
        found = next((a for a in _ACTIONS_COMMERCE if a in desc
                      and a not in _GENERIC), "")
        if found:
            return (
                f"La dimension {found} au coeur de ce poste correspond directement "
                f"au travail que je mene chez Agence 113 / DEFI GROUPE : structurer "
                f"un pipeline, qualifier et closer en autonomie sur 360 KEUR/mois."
            )
        return (
            "Le developpement commercial que vous portez correspond directement "
            "a ce que je pratique : structurer un pipeline, negocier en autonomie "
            "et delivrer sur un portefeuille a 360 KEUR/mois."
        )

    if role == "purchasing":
        return (
            "La logique achats - comprendre les contraintes de l'autre partie "
            "avant de defendre les siennes - est l'approche que j'ai construite "
            "en B2B et que je veux transposer a votre categorie."
        )

    if role == "hr":
        return (
            "Le recrutement qui delivre, c'est celui qui comprend le business. "
            "Mon double profil Business Developer / Recruitment Officer m'a donne "
            "exactement cette double lecture."
        )

    return ""


# ─── Type d'entreprise ───────────────────────────────────────────────────────

_BIG_GROUPS = [
    "lvmh", "l'oreal", "loreal", "sanofi", "bnp paribas", "bnp", "axa",
    "societe generale", "credit agricole", "total energies", "totalenergies",
    "michelin", "renault", "stellantis", "danone", "hermes", "chanel", "kering",
    "dior", "air france", "edf", "engie", "orange", "air liquide", "saint-gobain",
    "schneider", "legrand", "thales", "safran", "airbus", "bouygues", "vinci",
    "capgemini", "sopra", "deloitte", "pwc", "kpmg", "mckinsey", "bain", "bcg",
    "roland berger", "accenture", "hsbc", "societe generale", "natixis",
    "carrefour", "leclerc", "decathlon", "leroy merlin", "fnac",
]

_STARTUP_KEYWORDS = [
    "startup", "scale-up", "scaleup", "series a", "series b", "seed",
    "levee de fonds", "fintech", "proptech", "saas", "growth hacking",
    "agile", "squad", "tribe", "product-led",
]


def detect_company_type(entreprise: str, description: str = "") -> str:
    """Retourne 'grand_groupe' | 'startup' | 'pme'."""
    e_low = (entreprise or "").lower()
    d_low = (description or "").lower()
    if any(b in e_low for b in _BIG_GROUPS):
        return "grand_groupe"
    combined = f"{e_low} {d_low}"
    if any(s in combined for s in _STARTUP_KEYWORDS):
        return "startup"
    return "pme"


# ─── Plan 30 jours ────────────────────────────────────────────────────────────

def _thirty_day_plan(role: str, company_type: str) -> str:
    """Ce que je vais concretement accomplir dans les 30 premiers jours."""
    _plans = {
        "business_dev": (
            "Dans les 30 premiers jours, mon objectif est precis : "
            "cartographier le marche cible, qualifier 20+ prospects dans le pipeline "
            "et identifier les 3 profils de clients a plus fort potentiel. "
            "Je n'attends pas qu'on me dise comment — je structure et j'execute."
        ),
        "key_account": (
            "Dans les 30 premiers jours : audit complet du portefeuille existant, "
            "identification des comptes a potentiel sous-exploite, et premier "
            "business review avec les 5 comptes prioritaires."
        ),
        "financial_analyst": (
            "Dans les 30 premiers jours : maitrise complete de vos outils et process, "
            "production d'un premier reporting actionnable, et identification "
            "d'au moins un ecart ou une optimisation dans les chiffres actuels."
        ),
        "product_marketing": (
            "Dans les 30 premiers jours : immersion complete dans votre roadmap "
            "produit, analyse de 3 segments clients et premier brief de campagne "
            "teste avec les equipes terrain."
        ),
        "digital_marketing": (
            "Dans les 30 premiers jours : audit de vos performances digitales "
            "actuelles, identification des 2-3 leviers a fort ROI, et premier "
            "A/B test lance sur le canal prioritaire."
        ),
        "data_analyst": (
            "Dans les 30 premiers jours : comprehension complete de votre "
            "architecture de donnees, production d'un premier dashboard actionnable "
            "et identification d'un insight non-exploite dans vos datasets actuels."
        ),
        "purchasing": (
            "Dans les 30 premiers jours : audit du panel fournisseurs existant, "
            "identification des categories a potentiel de renegalisation, et "
            "premier benchmark prix sur la categorie prioritaire."
        ),
    }
    plan = _plans.get(role, (
        "Dans les 30 premiers jours : integration complete, maitrise de vos outils "
        "et premier deliverable concret. Je suis operationnel sans periode de chauffe."
    ))

    # Adapter le ton selon le type d'entreprise
    if company_type == "startup":
        plan = plan.replace(
            "Dans les 30 premiers jours",
            "Ce qui me motive dans un environnement comme le votre : l'impact "
            "est mesurable rapidement. Dans les 30 premiers jours"
        )
    return plan


# ─── Phrase humaine par type d'entreprise ─────────────────────────────────────

def _human_phrase(company_type: str, role: str) -> str:
    if company_type == "grand_groupe":
        return (
            "Ce qui m'attire dans votre structure, c'est precisement la combinaison "
            "de ressources et d'exigence : les grands groupes forment des gens qui "
            "savent executer a un niveau que peu d'environnements permettent d'atteindre."
        )
    if company_type == "startup":
        return (
            "J'ai une preference marquee pour les environnements ou les decisions "
            "se prennent vite et ou l'impact est visible rapidement. C'est ce que "
            "votre structure represente pour moi."
        )
    return (
        "Ce qui m'attire dans votre structure, c'est la proximite avec les "
        "decisions et la capacite de voir directement l'impact de son travail."
    )


# ─── Cloture par type de contrat ──────────────────────────────────────────────

def _closing(contrat: str) -> str:
    if contrat == "alternance":
        return (
            "Cette alternance chez vous represente exactement l'equilibre que je "
            "recherche : continuer a progresser en MBA tout en apportant une "
            "contribution concrete des le premier mois. Je reste disponible pour "
            "un echange a votre convenance."
        )
    if contrat == "stage":
        return (
            "Ce stage represente l'opportunite de mettre mes competences au service "
            "de vos projets et d'apprendre dans un environnement exigeant. "
            "Je reste disponible pour un echange a votre convenance."
        )
    return (
        "Je suis convaincu de pouvoir apporter une contribution concrete et rapide "
        "a votre equipe. Je reste disponible pour un echange a votre convenance."
    )


# ─── Lettre mode urgence (jobs simples terrain) ──────────────────────────────

def _generate_simple(titre: str, entreprise: str, contrat: str) -> str:
    """Lettre courte et directe pour jobs terrain / alimentaires."""
    t = titre.lower()
    is_luxe = any(k in t for k in _p.LUXE_KEYWORDS)
    is_recr = any(k in t for k in _p.RECRUTEMENT_KEYWORDS)

    if is_luxe:
        hook = (
            f"Je vous adresse ma candidature pour le poste de {titre} chez {entreprise}. "
            f"Ayant travaille comme Sales Advisor au Printemps Haussmann ou j'ai "
            f"depasse mes objectifs de vente de 10% et accompagne une clientele "
            f"internationale premium, je suis a l'aise dans les environnements "
            f"exigeants et orientes excellence."
        )
        corps = (
            "Je suis presente, attentif au detail et capable de conseiller avec "
            "naturel une clientele diverse. La culture du service de votre enseigne "
            "correspond exactement a ce que j'aime dans ce metier."
        )
    elif is_recr:
        hook = (
            f"Je vous adresse ma candidature pour le poste de {titre} chez {entreprise}. "
            f"Recruitment Officer chez Agence 113 / DEFI GROUPE ou j'ai gere des "
            f"evenements reunissant 300+ candidats, je suis a l'aise dans la "
            f"selection, l'accueil et la coordination."
        )
        corps = (
            "Je sais travailler vite, garder les priorites en tete et maintenir "
            "un bon contact humain meme sous pression. Serieux et reactif."
        )
    else:
        hook = (
            f"Je vous adresse ma candidature pour le poste de {titre} chez {entreprise}. "
            f"Avec une experience en vente conseil (Printemps Haussmann) et en "
            f"relation client, je suis operationnel immediatement et motive pour "
            f"integrer votre equipe."
        )
        corps = (
            "Je suis ponctuel, serieux et a l'aise dans les environnements "
            "dynamiques. Je m'adapte vite et livre ce qu'on attend de moi."
        )

    closing_map = {
        "stage":      "Ce stage est une opportunite de contribuer concretement. Disponible des que possible.",
        "alternance": "Cette alternance m'interesse pour progresser en pratique tout en continuant ma formation.",
    }
    closing = closing_map.get(contrat,
        "Je suis disponible immediatement et serais ravi d'echanger avec vous.")

    return "\n\n".join([
        "Madame, Monsieur,",
        hook,
        corps,
        closing,
        f"Cordialement,\n{PROFILE['name']}\n{PROFILE['phone']} | {PROFILE['email']}"
    ])


# ─── Generation de la lettre ─────────────────────────────────────────────────

def generate(offer: dict, contrat: str = "cdi") -> str:
    titre       = offer.get("titre", "le poste propose")
    entreprise  = offer.get("entreprise", "votre entreprise")
    description = offer.get("description", "")
    role        = detect_role(titre, description)

    # Mode urgence : lettre courte directe
    if is_simple_job(titre):
        return _generate_simple(titre, entreprise, contrat)

    ctype   = detect_company_type(entreprise, description)
    hook    = _hook(role, titre, entreprise, contrat, offer)
    bridge  = _bridge(offer, role)
    pitch   = _pitch(role)
    deliver = _deliverables(role)
    plan    = _thirty_day_plan(role, ctype)
    human   = _human_phrase(ctype, role)
    closing = _closing(contrat)

    paras = ["Madame, Monsieur,", hook]
    if bridge:
        paras.append(bridge)
    paras.append(pitch)
    paras.append(deliver)
    paras.append(plan)
    paras.append(human)
    paras.append(closing)
    paras.append(
        f"Cordialement,\n{PROFILE['name']}\n{PROFILE['phone']} | {PROFILE['email']}"
    )

    return "\n\n".join(paras)


# ─── Mode best (conversion maximale) ────────────────────────────────────────

def generate_best(offer: dict, contrat: str = "cdi") -> str:
    """
    Version maximale : hook agressif (idx=0 = le plus direct pour le role),
    bridge specifique, pitch complet, plan 30 jours, phrase humaine, cloture forte.
    """
    titre       = offer.get("titre", "le poste propose")
    entreprise  = offer.get("entreprise", "votre entreprise")
    description = offer.get("description", "")
    role        = detect_role(titre, description)
    ctype       = detect_company_type(entreprise, description)

    # Hook le plus direct : forcer idx=0 (premier variant = le plus percutant)
    best_offer = dict(offer)
    # Modifier le hash pour toujours tomber sur idx=0
    best_offer["_best_mode"] = "force_idx_0"

    class _ForceIdx0:
        pass

    # Bypass rotation — utiliser hook idx 0 directement
    poste = titre.strip()
    _C = {
        "cdi": "rejoindre votre equipe en CDI",
        "alternance": "rejoindre votre equipe en alternance",
        "stage": "effectuer un stage au sein de votre equipe",
    }.get(contrat, "rejoindre votre equipe")

    # Hook agressif par role — version la plus percutante
    _BEST_HOOKS = {
        "business_dev": (
            f"Actuellement Business Developer B2B chez Agence 113 / DEFI GROUPE, "
            f"ou je pilote un portefeuille generant 360 KEUR/mois, et diplome en "
            f"cours de MBA Manager de Business Unit a PSB Paris (soutenance juin "
            f"2026), je souhaite mettre mon experience commerciale au service de "
            f"votre equipe sur le poste de {poste} chez {entreprise}."
        ),
        "key_account": (
            f"Deux ans a piloter 30+ comptes B2B en autonomie complete — c'est ce "
            f"que j'apporte au poste de {poste} chez {entreprise}. Business "
            f"Developer chez Agence 113 / DEFI GROUPE (360 KEUR/mois), certifie "
            f"Negotiation Business School (2025), MBA Manager de Business Unit en "
            f"cours (PSB Paris, juin 2026)."
        ),
        "financial_analyst": (
            f"Deux ans a piloter une activite a forts enjeux chiffres m'ont appris "
            f"a lire un business dans ses donnees, pas seulement dans ses resultats. "
            f"C'est cette lecture que je veux developper en rejoignant {entreprise} "
            f"sur le poste de {poste}. MBA Manager de Business Unit (PSB Paris, "
            f"juin 2026), module controle de gestion."
        ),
        "product_marketing": (
            f"Chaque projet digital que j'ai mene — de Lisbonne a Paris — a confirme "
            f"une chose : je m'epanouis la ou marketing, produit et donnees se "
            f"croisent. Le poste de {poste} chez {entreprise} est exactement cet "
            f"environnement. MBA Manager de Business Unit (PSB Paris, juin 2026), "
            f"disponible pour {_C}."
        ),
        "digital_marketing": (
            f"Le marketing qui laisse des traces, c'est celui qui se mesure. "
            f"C'est la culture que j'ai construite chez GROW 360 (Paris) et en "
            f"projets clients depuis Lisbonne. Le poste de {poste} chez {entreprise} "
            f"est le terrain ideal pour mettre cette discipline au service de votre equipe."
        ),
        "purchasing": (
            f"Maitriser une negociation, c'est comprendre les contraintes de l'autre "
            f"partie avant de defendre les siennes. C'est l'approche que j'ai "
            f"construite en B2B (Negotiation Business School, 2025) et que je veux "
            f"transposer aux achats en rejoignant {entreprise} sur le poste de {poste}."
        ),
    }
    hook = _BEST_HOOKS.get(
        role,
        (
            f"Sur le poste de {poste} chez {entreprise}, mon objectif est clair : "
            f"etre operationnel des la premiere semaine et delivrer des resultats "
            f"mesurables. Business Developer B2B (360 KEUR/mois) et MBA Manager "
            f"de Business Unit en cours (PSB Paris, juin 2026)."
        )
    )

    bridge   = _bridge(offer, role)
    pitch    = _pitch(role)
    plan     = _thirty_day_plan(role, ctype)
    human    = _human_phrase(ctype, role)
    closing  = _closing(contrat)

    paras = ["Madame, Monsieur,", hook]
    if bridge:
        paras.append(bridge)
    paras.append(pitch)
    paras.append(plan)
    paras.append(human)
    paras.append(closing)
    paras.append(
        f"Cordialement,\n{PROFILE['name']}\n{PROFILE['phone']} | {PROFILE['email']}"
    )

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
        contact = f"{PROFILE['phone']}  |  {PROFILE['email']}  |  {PROFILE['city']}"
        self.cell(0, 4, _safe(contact), ln=1)
        self.set_fill_color(*self.GOLD)
        self.rect(0, 18, 210, 0.7, style="F")
        self.set_y(22)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 155)
        self.cell(0, 3.5, _safe(f"Lettre de motivation — {self._titre} chez {self._entreprise}"),
                  align="C")


def to_pdf(letter_text: str, offer: dict = None) -> bytes:
    """Convertit la lettre texte en PDF propre."""
    offer = offer or {}
    titre = offer.get("titre", "poste")
    entreprise = offer.get("entreprise", "entreprise")

    pdf = _LetterPdf(titre, entreprise)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_y(26)
    pdf.set_x(130)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 85)
    from datetime import date
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

    paragraphs = letter_text.split("\n\n")
    for i, para in enumerate(paragraphs):
        pdf.set_x(14)
        if i == 0:  # "Madame, Monsieur,"
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(15, 35, 85)
            pdf.cell(0, 6, _safe(para), ln=1)
            pdf.ln(2)
        elif para.startswith("Cordialement"):
            # Signature
            pdf.ln(4)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 55)
            for line in para.split("\n"):
                pdf.set_x(14)
                if line == para.split("\n")[0]:
                    pdf.set_font("Helvetica", "B", 10)
                else:
                    pdf.set_font("Helvetica", "", 9)
                pdf.cell(0, 5, _safe(line), ln=1)
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 55)
            pdf.multi_cell(182, 5.5, _safe(para))
            pdf.ln(3)

    out = pdf.output(dest="S")
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
