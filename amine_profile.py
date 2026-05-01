"""
Profil central d'Amine Ben Mansour.
Source de verite unique pour tous les generateurs.
Ne jamais inventer de fausses experiences — reformuler intelligemment.
"""

# ─── Identite ─────────────────────────────────────────────────────────────────

FULL_NAME    = "AMINE BEN MANSOUR"
DISPLAY_NAME = "Amine Ben Mansour"
PHONE        = "+33 6 60 64 57 83"
EMAIL        = "mohamedbenpro47@gmail.com"
CITY         = "Paris, France"
LINKEDIN_URL = "https://www.linkedin.com/in/amine-ben-mansour-b50a06246/"
VIDEO_CV_URL = ""   # a remplir quand disponible

# ─── Objectifs ────────────────────────────────────────────────────────────────

OBJECTIF = {
    "court_terme":  "Poste operationnel avec impact direct — commercial, marketing, business",
    "moyen_terme":  "Developper expertise et revenus rapidement, prendre des responsabilites",
    "long_terme":   "Independance — entreprendre ou devenir expert reconnu dans son domaine",
}

# ─── Forces reelles ───────────────────────────────────────────────────────────

FORCES = [
    "A l'aise en situation terrain et face au client — naturellement a l'aise dans le contact",
    "Mentalite orientee resultats : objectifs, chiffres, impact concret",
    "Adaptable rapidement a de nouveaux environnements et contextes",
    "Multilinguisme : FR/AR natifs, EN courant, ES intermediaire, Chinois notions",
    "Autonomie complete — capable de livrer sans encadrement constant",
    "Relation humaine authentique — cree rapidement la confiance",
]

# ─── Experiences reelles (ne pas inventer) ────────────────────────────────────

EXPERIENCES = {
    "defi": {
        "titre":       "Business Developer & Recruitment Officer",
        "entreprise":  "Agence 113 / DEFI GROUPE",
        "ville":       "Paris",
        "periode":     "Sept. 2025 - Present",
        "type":        "emploi",
        "impact_cle":  "Portefeuille B2B 360 KEUR/mois, 30+ leads qualifies/mois, 300+ candidats/session recrutement",
        "competences": [
            "Prospection B2B et cycle commercial complet (prospection -> closing)",
            "Negociation directe avec decideurs",
            "CRM HubSpot, LinkedIn Sales Navigator",
            "Recrutement operationnel et coordination POEI",
            "Suivi KPIs et reporting direction",
        ],
        "chiffres": {
            "ca_mensuel":     "360 KEUR/mois",
            "leads_par_mois": "30+",
            "candidats":      "300+ par session",
            "partenariats":   "3 partenariats long terme conclus / trimestre",
        },
    },
    "wix": {
        "titre":       "Project Manager / Website Builder",
        "entreprise":  "Wix — International",
        "ville":       "Lisbonne, Portugal",
        "periode":     "2025",
        "type":        "freelance/projet",
        "impact_cle":  "5+ sites clients livres en autonomie, +20% taux de clic moyen sur landing pages",
        "competences": [
            "Gestion de projet digitaux de A a Z",
            "Relation client et brief",
            "UX et optimisation conversion",
            "Livraison autonome en environnement international",
        ],
    },
    "printemps": {
        "titre":       "Sales Advisor — Premium Retail",
        "entreprise":  "Printemps Haussmann",
        "ville":       "Paris",
        "periode":     "2024",
        "type":        "emploi",
        "impact_cle":  "+10% vs objectif mensuel, clientele internationale premium",
        "competences": [
            "Vente conseil en environnement premium",
            "Relation client internationale et haut de gamme",
            "Atteinte et depassement d'objectifs de vente",
            "Fidelisation clientele et suivi portefeuille",
        ],
        "chiffres": {
            "perf_vente": "+10% vs cible mensuelle",
        },
    },
    "grow": {
        "titre":       "Community Manager",
        "entreprise":  "GROW 360",
        "ville":       "Paris",
        "periode":     "2023 - 2024",
        "type":        "emploi",
        "impact_cle":  "+35% engagement Instagram/LinkedIn en 6 mois, 10+ posts/semaine 0 retard",
        "competences": [
            "Strategie de contenu et planning editorial",
            "Community management multi-plateformes",
            "Analyse de performance et KPIs engagement",
            "Production de contenu (3 formats)",
        ],
        "chiffres": {
            "engagement": "+35% en 6 mois",
            "cadence":    "10+ posts/semaine, 0 retard",
        },
    },
}

# ─── Formation ────────────────────────────────────────────────────────────────

FORMATION = {
    "mba": {
        "titre":  "MBA Manager de Business Unit",
        "ecole":  "PSB Paris School of Business",
        "annee":  "2025-2026",
        "statut": "Soutenance juin 2026",
    },
    "bachelor": {
        "titre":  "Bachelor Bac+3 — Developpement Commercial",
        "ecole":  "PSB Paris School of Business",
        "annee":  "2022-2025",
        "statut": "Obtenu",
    },
    "negociation": {
        "titre":  "Certification Negociation Commerciale",
        "ecole":  "Negotiation Business School (en ligne)",
        "annee":  "2025",
        "statut": "Certifie",
    },
    "sst": {
        "titre":  "Habilitation SST — Sauveteur Secouriste Travail",
        "ecole":  "Croix-Rouge Francaise",
        "annee":  "2024",
        "statut": "",
    },
}

# ─── Langues ──────────────────────────────────────────────────────────────────

LANGUES = [
    ("Francais",  "Natif"),
    ("Arabe",     "Natif"),
    ("Anglais",   "Courant"),
    ("Espagnol",  "Intermediaire"),
    ("Chinois",   "Notions"),
]

# ─── Outils ───────────────────────────────────────────────────────────────────

OUTILS_BASE = "CRM : HubSpot, Sales Navigator  |  Marketing : Canva, Notion, Wix  |  Bureautique : Excel avance, Google Suite"

# ─── Detection jobs simples (mode urgence) ────────────────────────────────────

SIMPLE_JOB_KEYWORDS = [
    "serveur", "serveuse", "vendeur", "vendeuse", "caissier", "caissiere",
    "livreur", "livreuse", "agent", "animateur", "hotesse", "standardiste",
    "receptionniste", "barman", "bartender", "equipier", "plongeur",
    "magasinier", "preparateur", "conducteur", "chauffeur", "operateur",
    "agent de securite", "vigile", "gardien", "aide", "assistant polyvalent",
    "employe polyvalent", "manutentionnaire",
]

COMMERCIAL_KEYWORDS = [
    "commercial", "vendeur terrain", "technico-commercial", "vente directe",
    "chasseur", "business", "prospecteur",
]

LUXE_KEYWORDS = [
    "luxe", "premium", "haute couture", "joaillerie", "horlogerie",
    "maison", "brand ambassador", "conseiller de vente luxe",
]

RECRUTEMENT_KEYWORDS = [
    "recruteur", "chargé de recrutement", "talent", "rh", "chasseur de tete",
    "sourcer", "talent acquisition",
]
