"""Construction du Master Profile v1 (étape P0.5).

Sources, par priorité de vérité :
  1. profiles/confirmations.yaml — déclarations CONFIRMÉES par l'utilisateur ;
  2. legacy/amine_profile.py     — ancien profil du dépôt, importé avec provenance (IMPORTED) ;
  3. JobAgent                    — PROFILE_IMPORT_REQUIRED tant qu'aucun export n'est fourni.

Règles : une donnée legacy en conflit avec une confirmation n'est jamais importée
telle quelle (file REVIEW ou FORBIDDEN) ; les chiffres importés restent « à confirmer ».
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from . import paths
from .profile import add_review
from .schemas import Fact, MasterProfile, ProfileEvent, ReviewItem
from .textnorm import extract_numbers, norm, stable_hash

# Orthographe : le fichier legacy est écrit sans accents. Correction purement typographique,
# la version brute reste dans `data.raw` pour la traçabilité.
_ACCENTS = {
    r"\bqualifies\b": "qualifiés", r"\blivres\b": "livrés", r"\bNegociation\b": "Négociation",
    r"\bnegociation\b": "négociation", r"\bdecideurs\b": "décideurs", r"\boperationnel\b": "opérationnel",
    r"\bStrategie\b": "Stratégie", r"\beditorial\b": "éditorial", r"\bdepassement\b": "dépassement",
    r"\bFidelisation\b": "Fidélisation", r"\bclientele\b": "clientèle", r"\bClientele\b": "Clientèle",
    r"\bde A a Z\b": "de A à Z", r"posts/semaine 0 retard": "posts/semaine, 0 retard",
    r"\bprojet digitaux\b": "projets digitaux", r"\bDeveloppement\b": "Développement",
    r"\bFrancais\b": "Français", r"\bIntermediaire\b": "Intermédiaire", r"\bavance\b": "avancé",
    r"\bFrancaise\b": "française", r"\bCertifie\b": "Certifié", r"\bPresent\b": "présent",
    r"\bSecouriste Travail\b": "Secouriste du Travail", r"\(prospection -> closing\)": "(de la prospection au closing)",
    r"->": "à", r"\bKEUR\b": "K€",
    r"/session recrutement": " par session de recrutement", r"\ba l'aise\b": "à l'aise",
    r"\bA l'aise\b": "À l'aise", r"\borientee\b": "orientée", r"\bcree\b": "crée",
}

_MONTHS = {"janv": "01", "jan": "01", "fev": "02", "feb": "02", "mars": "03", "mar": "03", "avr": "04", "apr": "04",
           "mai": "05", "may": "05", "juin": "06", "jun": "06", "juil": "07", "jul": "07", "aout": "08", "aug": "08",
           "sept": "09", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
_MONTH_LABEL = {"01": "Janv.", "02": "Févr.", "03": "Mars", "04": "Avr.", "05": "Mai", "06": "Juin", "07": "Juil.",
                "08": "Août", "09": "Sept.", "10": "Oct.", "11": "Nov.", "12": "Déc."}

# Compétences extraites mot pour mot des responsabilités importées (aucune déduction).
_SKILL_PHRASES = [
    "Prospection B2B", "Négociation", "Relation client", "Recrutement", "Gestion de projets digitaux",
    "Community management", "Vente conseil", "Fidélisation", "Reporting", "Suivi KPIs", "UX",
    "Stratégie de contenu", "Planning éditorial", "Production de contenu", "Analyse de performance",
    "Optimisation conversion", "Coordination POEI", "Cycle commercial complet",
]


def fr_text(text: str) -> str:
    out = text
    for pattern, repl in _ACCENTS.items():
        out = re.sub(pattern, repl, out)
    out = re.sub(r"\+(\d+)%", r"+\1 %", out)
    return out.strip()


def parse_period(raw: str) -> dict[str, Any]:
    """'Sept. 2025 - Present' → start 2025-09, en cours ; '2023 - 2024' → 2023 à 2024."""
    txt = norm(raw)
    parts = [p.strip() for p in re.split(r"\s-\s|\s–\s|\sa\s", txt)]

    def one(part: str) -> str | None:
        m = re.search(r"(19|20)\d{2}", part)
        if not m:
            return None
        year = m.group(0)
        for key, month in _MONTHS.items():
            if re.search(rf"\b{key}", part):
                return f"{year}-{month}"
        return year

    start = one(parts[0]) if parts else None
    end: str | None
    current = False
    if len(parts) > 1:
        if any(w in parts[1] for w in ("present", "aujourd", "en cours", "actuel", "now")):
            end, current = None, True
        else:
            end = one(parts[1])
    else:
        end = start

    def label(value: str | None) -> str:
        if not value:
            return ""
        if len(value) == 7:
            return f"{_MONTH_LABEL[value[5:]]} {value[:4]}"
        return value

    period_label = label(start) if end == start else f"{label(start)} – {'présent' if current else label(end)}"
    return {"start": start, "end": end, "current": current, "period_label": period_label}


def _load_legacy_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("pai_legacy_profile", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fact(fid: str, kind: str, text: str, status: str, source: str, provenance: str, **extra: Any) -> Fact:
    return Fact(id=fid, kind=kind, text=text, status=status, source=source, provenance=provenance, **extra)


def build_master_profile(
    legacy_path: Path | None = None,
    confirmations_path: Path | None = None,
    candidate_id: str = "amine",
) -> MasterProfile:
    legacy_path = legacy_path or paths.LEGACY_DIR / "amine_profile.py"
    confirmations_path = confirmations_path or paths.PROFILES_DIR / "confirmations.yaml"
    conf = yaml.safe_load(confirmations_path.read_text(encoding="utf-8"))
    conf_src = conf.get("source", "user")
    conf_prov = f"{confirmations_path.relative_to(paths.ROOT).as_posix()} ({conf.get('confirmed_at', '')})"

    facts: list[Fact] = []
    profile = MasterProfile(candidate_id=candidate_id, version=1)

    # 1. Confirmations utilisateur
    for item in conf.get("facts", []):
        facts.append(_fact(item["id"], item["kind"], item["text"], "CONFIRMED", conf_src, conf_prov,
                           data=item.get("data") or {}, note=item.get("note", "")))
    forbidden_terms: list[str] = []
    for item in conf.get("forbidden", []):
        facts.append(_fact(item["id"], item.get("kind", "other"), item["text"], "FORBIDDEN", conf_src, conf_prov,
                           terms=item.get("terms", []), note=item.get("reason", "")))
        forbidden_terms.extend(norm(t) for t in item.get("terms", []))

    def is_forbidden(text: str) -> bool:
        t = norm(text)
        return any(term and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", t) for term in forbidden_terms)

    # 2. Import legacy (avec provenance)
    legacy_prov = f"legacy/amine_profile.py@sha256:{stable_hash(legacy_path.read_bytes(), 10)}"
    src = "legacy:amine_profile.py"
    legacy = _load_legacy_module(legacy_path)

    facts += [
        _fact("contact.email", "contact", legacy.EMAIL, "IMPORTED", src, legacy_prov),
        _fact("contact.phone", "contact", legacy.PHONE, "IMPORTED", src, legacy_prov),
        _fact("contact.city", "contact", legacy.CITY, "IMPORTED", src, legacy_prov, data={"city": legacy.CITY.split(",")[0]}),
    ]
    if getattr(legacy, "LINKEDIN_URL", ""):
        facts.append(_fact("contact.linkedin", "contact", legacy.LINKEDIN_URL, "IMPORTED", src, legacy_prov))
    if norm(legacy.DISPLAY_NAME) != norm(next((f.text for f in facts if f.id == "id.name"), "")):
        add_review(profile, "id.name", f"Nom legacy différent : « {legacy.DISPLAY_NAME} »", "conflict")

    # Expériences
    for key, exp in legacy.EXPERIENCES.items():
        exp_id = f"exp.{key}"
        period = parse_period(exp["periode"])
        title, company = fr_text(exp["titre"]), fr_text(exp["entreprise"])
        city = fr_text(exp.get("ville", ""))
        facts.append(_fact(exp_id, "experience", f"{title} — {company} ({period['period_label']})", "IMPORTED", src, legacy_prov,
                           data={"title": title, "company": company, "city": city, "type": exp.get("type", ""),
                                 **period, "raw": exp["periode"]}))
        if period["current"]:
            add_review(profile, exp_id,
                       "Poste noté « en cours » dans le profil legacy alors que la disponibilité immédiate est confirmée : "
                       "date de fin à confirmer.", "warning")
        for i, item in enumerate(exp.get("competences", []), 1):
            facts.append(_fact(f"{exp_id}.t{i}", "responsibility", fr_text(item), "IMPORTED", src, legacy_prov,
                               parent=exp_id, data={"raw": item}))
        results = [r.strip() for r in exp.get("impact_cle", "").split(",") if r.strip()]
        numbers_seen: set[str] = set()
        n = 0
        for raw in results:
            n += 1
            nums = extract_numbers(raw)
            numbers_seen.update(nums)
            text = fr_text(raw[0].upper() + raw[1:])
            facts.append(_fact(f"{exp_id}.r{n}", "result", text, "IMPORTED", src, legacy_prov, parent=exp_id,
                               needs_confirmation=bool(nums), confidence=0.7 if nums else 0.85, data={"raw": raw}))
        for raw in (exp.get("chiffres") or {}).values():
            figures = set(extract_numbers(raw))
            if figures and figures <= numbers_seen:
                continue
            n += 1
            numbers_seen.update(figures)
            facts.append(_fact(f"{exp_id}.r{n}", "result", fr_text(raw[0].upper() + raw[1:]).replace(" / ", " par "),
                               "IMPORTED", src, legacy_prov, parent=exp_id, needs_confirmation=True, confidence=0.7,
                               data={"raw": raw}))

    # Formation (conflits → REVIEW ou FORBIDDEN, jamais importés en silence)
    confirmed_titles = [norm(f.text) for f in facts if f.kind == "education" and f.status == "CONFIRMED"]
    for key, edu in legacy.FORMATION.items():
        title, school = fr_text(edu["titre"]), fr_text(edu["ecole"])
        text = f"{title} — {school} ({edu['annee']})" + (f", {fr_text(edu['statut'])}" if edu.get("statut") else "")
        if is_forbidden(text):
            add_review(profile, "edu.mba",
                       f"Le profil legacy mentionne « {edu['titre']} » : rejeté (interdit par l'utilisateur).", "info")
            continue
        kind = "certification" if key in ("negociation", "sst") else "education"
        fid = f"{'cert' if kind == 'certification' else 'edu'}.legacy_{key}"
        status = "IMPORTED"
        if kind == "education" and any(t.split(" ")[0] in norm(title) for t in confirmed_titles):
            status = "UNVERIFIED"
            add_review(profile, fid,
                       f"Deux intitulés proches : « {title} — {school} » (legacy) et le diplôme confirmé "
                       f"« {', '.join(f.text for f in facts if f.kind == 'education' and f.status == 'CONFIRMED')} ». "
                       "Même diplôme ? À confirmer avant usage.", "conflict")
        facts.append(_fact(fid, kind, text, status, src, legacy_prov,
                           data={"title": title, "school": school, "year": edu["annee"], "raw": edu["titre"]}))

    # Langues
    for name, level in legacy.LANGUES:
        lang_fr = fr_text(name)
        slug = {"francais": "fr", "arabe": "ar", "anglais": "en", "espagnol": "es", "chinois": "zh"}.get(norm(name), norm(name)[:2])
        facts.append(_fact(f"lang.{slug}", "language", f"{lang_fr} — {fr_text(level).lower()}", "IMPORTED", src, legacy_prov,
                           data={"language": lang_fr, "level": fr_text(level).lower()}))

    # Outils
    for group in legacy.OUTILS_BASE.split("|"):
        if ":" not in group:
            continue
        category, tools = group.split(":", 1)
        for tool in [t.strip() for t in tools.split(",") if t.strip()]:
            label = fr_text(tool)
            if norm(label) == "sales navigator":
                label = "LinkedIn Sales Navigator"
            facts.append(_fact(f"tool.{re.sub(r'[^a-z0-9]+', '_', norm(label)).strip('_')}", "tool", label, "IMPORTED", src,
                               legacy_prov, data={"category": fr_text(category.strip())}))

    # Forces (auto-évaluations) : utilisables, confiance réduite
    for i, force in enumerate(legacy.FORCES, 1):
        if norm(force).startswith("multilinguisme"):
            continue  # doublon des langues
        facts.append(_fact(f"soft.{i}", "soft_skill", fr_text(force), "IMPORTED", src, legacy_prov, confidence=0.6))

    # Objectifs → préférences (jamais écrits comme faits dans un document)
    for horizon, text in getattr(legacy, "OBJECTIF", {}).items():
        facts.append(_fact(f"pref.{horizon}", "preference", fr_text(text), "IMPORTED", src, legacy_prov))

    # Compétences extraites mot pour mot des responsabilités
    seen_skills: set[str] = set()
    for f in list(facts):
        if f.kind != "responsibility":
            continue
        for phrase in _SKILL_PHRASES:
            if norm(phrase) in norm(f.text) and norm(phrase) not in seen_skills:
                seen_skills.add(norm(phrase))
                facts.append(_fact(f"skill.{re.sub(r'[^a-z0-9]+', '_', norm(phrase)).strip('_')}", "skill", phrase,
                                   "IMPORTED", "derived:verbatim", f"extrait de {f.id}", parent=f.id))

    profile.facts = facts
    profile.unknowns = [
        "Photo professionnelle (non fournie) — mode photo OFF.",
        "Bachelor REM : intitulé complet, école, dates.",
        "BTS NTC : école, dates.",
        "TOEIC 915/990 : date de passage.",
        "Dates au mois près pour Wix (2025), Printemps Haussmann (2024), GROW 360 (2023 – 2024).",
        "Statut exact de la mission Wix (freelance, salarié, stage).",
        "Âge et nationalité : utiles seulement pour l'éligibilité VIE, jamais écrits sans confirmation.",
        "Prétentions salariales.",
        "Export JobAgent (historique des candidatures, CV et lettres envoyés, réponses) : PROFILE_IMPORT_REQUIRED.",
    ]
    profile.history.append(ProfileEvent(action="bootstrap", detail=f"confirmations + {legacy_prov}"))
    ids = [f.id for f in profile.facts]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"Identifiants en double : {sorted(dup)}")
    return profile


def jobagent_status() -> ReviewItem:
    return ReviewItem(
        fact_id="jobagent",
        reason="PROFILE_IMPORT_REQUIRED : le lien /profil JobAgent (trycloudflare, temporaire) est inaccessible "
               "depuis l'environnement de build. Fournir un export JSON produit par JobAgent ou une nouvelle URL.",
        severity="info",
    )
