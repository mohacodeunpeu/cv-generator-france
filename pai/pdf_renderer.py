from __future__ import annotations

from pai.models import Strategy


def build_strategy(profile: dict, analysis) -> Strategy:
    sector = analysis.sector
    if sector == "marketing":
        positioning = "Positionnement marketing-performance / acquisition & activation, en mettant en avant la conversion, le contenu et les résultats mesurés."
        ats_mode = "HYBRID"
        hook = "Je transforme le trafic et les opportunités en résultats mesurables pour la croissance."
        primary = ["Community Management", "Marketing digital", "Vente premium", "Relation client"]
        secondary = ["Wix", "Canva", "CRM"]
        key_skills = ["Prospection", "Marketing digital", "Relation client", "Performance"]
    elif sector == "recrutement":
        positioning = "Positionnement recrutement & business development, orienté sourcing, relation, et conversion de candidats vers recrutement."
        ats_mode = "ATS_FIRST"
        hook = "Je gère le cycle de recrutement et la prospection comme un pipeline commercial avec des résultats clairs."
        primary = ["Recrutement", "Prospection B2B", "Négociation", "KPI"]
        secondary = ["HubSpot", "Sales Navigator", "Relation client"]
        key_skills = ["Sourcing", "Négociation", "Pipeline", "Relation"]
    elif sector == "international":
        positioning = "Positionnement international / VIE / account management avec angle commercial, relation et adaptabilité multilingue."
        ats_mode = "HYBRID"
        hook = "Je crée de la confiance internationale, j'ouvre des opportunités et je transforme la relation client en croissance."
        primary = ["Vente premium", "Relation client", "Multilinguisme", "Proximité client"]
        secondary = ["International", "CRM", "Présentation"]
        key_skills = ["Gestion de portefeuille", "Négociation", "Communication", "Adaptabilité"]
    else:
        positioning = "Positionnement commercial / business development orienté résultats, proximité client, gestion de portefeuille et conversion."
        ats_mode = "ATS_FIRST"
        hook = "Je crée de la valeur directement sur le terrain : relation, pipeline, conversion, résultats."
        primary = ["Prospection B2B", "Business Development", "Relation client", "Vente"]
        secondary = ["CRM", "KPI", "Négociation"]
        key_skills = ["Prospection", "Vente", "Relation client", "KPI"]

    return Strategy(
        positioning=positioning,
        ats_mode=ats_mode,
        retention_hook=hook,
        primary_experiences=primary,
        secondary_experiences=secondary,
        key_skills=key_skills,
        risks=["Le rôle peut demander une spécialisation secteur plus poussée.", "Le niveau de seniorité doit être confirmé par le recruteur."],
        next_action="Valider le profil, préparer la mise en avant des résultats commerciaux, puis générer le CV et la lettre adaptatifs."
    )
