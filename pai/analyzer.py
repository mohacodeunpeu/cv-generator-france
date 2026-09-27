from __future__ import annotations

import amine_profile as legacy_profile


def get_master_profile() -> dict:
    experiences = [
        {
            "title": "Business Developer & Recruitment Officer",
            "company": "Agence 113 / DEFI GROUPE",
            "period": "Sept. 2025 - Present",
            "summary": "Prospection B2B, recrutement, suivi de portefeuille et développement commercial.",
            "results": ["Portefeuille B2B 360 KEUR/mois", "30+ leads qualifiés/mois", "300+ candidats par session"]
        },
        {
            "title": "Project Manager / Website Builder",
            "company": "Wix — International",
            "period": "2025",
            "summary": "Livraison de sites clients et optimisation de landing pages.",
            "results": ["5+ sites clients livrés", "+20% taux de clic moyen"]
        },
        {
            "title": "Sales Advisor — Premium Retail",
            "company": "Printemps Haussmann",
            "period": "2024",
            "summary": "Vente conseil en environnement premium et relation client internationale.",
            "results": ["+10% vs objectif mensuel"]
        },
        {
            "title": "Community Manager",
            "company": "GROW 360",
            "period": "2023 - 2024",
            "summary": "Community management, création de contenu et analyse d'engagement.",
            "results": ["+35% engagement Instagram/LinkedIn en 6 mois"]
        },
    ]

    return {
        "candidate_name": legacy_profile.DISPLAY_NAME,
        "email": legacy_profile.EMAIL,
        "phone": legacy_profile.PHONE,
        "city": legacy_profile.CITY,
        "status": "BROUILLON — PROFIL NON VALIDÉ",
        "profile_version": "v1",
        "target_roles": ["Business Developer", "Key Account Manager", "Account Manager", "Commercial", "VIE / International"],
        "experiences": experiences,
        "skills": [
            "Prospection B2B",
            "CRM",
            "HubSpot",
            "Sales Navigator",
            "Négociation",
            "Relation client",
            "Marketing digital",
            "Community management",
            "Vente premium",
            "Recrutement",
            "Excel avancé",
            "Canva",
            "Notion",
            "Wix",
        ],
        "languages": ["Français natif", "Arabe natif", "Anglais courant", "Espagnol intermédiaire", "Chinois notions"],
        "education": [
            "MBA Manager de Business Unit — PSB Paris School of Business (2025-2026)",
            "Bachelor Bac+3 Développement Commercial — PSB Paris School of Business (2022-2025)",
            "Certification Négociation Commerciale — Negotiation Business School (2025)"
        ],
        "facts": [
            {"fact_id": "f1", "label": "Nom", "value": legacy_profile.DISPLAY_NAME, "status": "CONFIRMED"},
            {"fact_id": "f2", "label": "Ville", "value": legacy_profile.CITY, "status": "CONFIRMED"},
            {"fact_id": "f3", "label": "Email", "value": legacy_profile.EMAIL, "status": "CONFIRMED"},
            {"fact_id": "f4", "label": "Téléphone", "value": legacy_profile.PHONE, "status": "CONFIRMED"},
        ],
    }
