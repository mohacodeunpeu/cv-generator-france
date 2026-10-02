"""Score PAI : des dimensions en pourcentages, chacune calculée par des critères lisibles.

Interface = pourcentages (Score PAI, puis Format & parsing, Structure, Matching offre, Mots-clés, Expérience,
Factualité, Formation, Langues) ; critères = moteur interne, visibles seulement dans « Voir les détails ».
Pondérations : rules/ats_scoring.yaml. Jamais présenté comme le score d'un ATS réel.
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Any

import yaml

from .. import paths
from ..rules import RuleSet, load_rules
from ..schemas import Analysis, CvDocument, Match, ValidationReport
from ..textnorm import contains_term, extract_numbers, norm
from .lexicon import stem
from .parser import LABELS as SECTION_LABELS
from .parser import ParsedCv
from .requirements import CLASS_WEIGHT, LABELS, PLAUSIBLE, PROVEN, UNPROVEN, Requirement

OK, WARNING, ERROR = "OK", "WARNING", "ERROR"


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    return yaml.safe_load((paths.RULES_DIR / "ats_scoring.yaml").read_text(encoding="utf-8")) or {}


def crit(label: str, status: str, detail: str = "", value: float | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"label": label, "status": status, "detail": detail}
    if value is not None:
        d["value"] = round(value)
    return d


def dimension(mode: str, did: str, value: float | None, details: list[dict[str, Any]], summary: str = "",
              measured: bool = True) -> dict[str, Any]:
    c = config()[mode][did]
    return {"id": did, "label": c["label"], "help": c["help"], "weight": c["weight"],
            "value": None if value is None else max(0, min(100, round(value))), "available": value is not None,
            "measured": measured, "summary": summary, "details": details}


def global_score(dims: list[dict[str, Any]]) -> dict[str, Any]:
    avail = [d for d in dims if d["available"]]
    total = sum(d["weight"] for d in avail)
    value = round(sum(d["value"] * d["weight"] for d in avail) / total) if total else None
    missing = [d["label"] for d in dims if not d["available"]]
    return {"value": value, "complete": not missing, "missing": missing, "disclaimer": config()["disclaimer"],
            "formula": " + ".join(f"{d['label']} × {d['weight']} %" for d in avail) + (
                f" (renormalisé : {', '.join(missing)} non mesuré)" if missing else "")}


# ── Structure ────────────────────────────────────────────────────────────────────────────────────
def structure_from_doc(cv: CvDocument) -> tuple[float, list[dict[str, Any]]]:
    secs = {ln.section for ln in cv.lines}
    details = []
    pts, total = 0.0, 0.0
    for sid, label, w in (("headline", "Titre du CV", 10), ("summary", "Profil", 10), ("experience", "Expérience", 25),
                          ("education", "Formation", 15), ("skills", "Compétences", 15), ("languages", "Langues", 5)):
        ok = sid in secs or (sid == "languages" and "certifications" in secs)
        total += w
        pts += w if ok else 0
        details.append(crit(label, OK if ok else WARNING if sid in ("summary", "languages") else ERROR,
                            "présente" if ok else "absente"))
    blocks = [b for b in cv.experiences if b.bullet_ids]
    dated = [b for b in blocks if b.period]
    total += 10
    pts += 10 * (len(dated) / len(blocks)) if blocks else 0
    details.append(crit("Expériences datées", OK if blocks and len(dated) == len(blocks) else WARNING,
                        f"{len(dated)}/{len(blocks)}"))
    good = [b for b in blocks if 1 <= len(b.bullet_ids) <= 6]
    total += 10
    pts += 10 * (len(good) / len(blocks)) if blocks else 0
    details.append(crit("Puces par expérience (1 à 6)", OK if blocks and len(good) == len(blocks) else WARNING,
                        f"{len(good)}/{len(blocks)} expériences"))
    contact = " ".join(cv.contact)
    has_mail, has_phone = "@" in contact, bool(re.search(r"\d{2}[\s.]?\d{2}[\s.]?\d{2}", contact))
    total += 10
    pts += 5 * has_mail + 5 * has_phone
    details.append(crit("Coordonnées (e-mail, téléphone)", OK if has_mail and has_phone else ERROR if not has_mail else WARNING,
                        ", ".join(x for x, ok in (("e-mail", has_mail), ("téléphone", has_phone)) if ok) or "absentes"))
    return 100 * pts / total, details


def structure_from_parsed(p: ParsedCv) -> tuple[float, list[dict[str, Any]]]:
    details, pts, total = [], 0.0, 0.0
    for sid, w in (("summary", 10), ("experience", 30), ("education", 20), ("skills", 20), ("languages", 5)):
        ok = sid in p.order
        total += w
        pts += w if ok else 0
        details.append(crit(SECTION_LABELS[sid], OK if ok else WARNING if sid in ("summary", "languages") else ERROR,
                            "section reconnue" if ok else "section introuvable (intitulé non standard ?)"))
    dated = [e for e in p.experiences if e.start]
    total += 10
    pts += 10 * (len(dated) / len(p.experiences)) if p.experiences else 0
    details.append(crit("Expériences datées", OK if p.experiences and len(dated) == len(p.experiences) else WARNING,
                        f"{len(dated)}/{len(p.experiences)}"))
    total += 5
    pts += 2.5 * bool(p.email) + 2.5 * bool(p.phone)
    details.append(crit("Coordonnées (e-mail, téléphone)", OK if p.email and p.phone else ERROR if not p.email else WARNING,
                        ", ".join(x for x, ok in (("e-mail", p.email), ("téléphone", p.phone)) if ok) or "absentes"))
    return 100 * pts / total, details


# ── Mots-clés ────────────────────────────────────────────────────────────────────────────────────
KW_WEIGHT = {"REQUIRED": 3.0, "IMPORTANT": 2.0, "NICE": 1.0}


def keyword_entries(analysis: Analysis, requirements: list[Requirement], cv_text: str | None,
                    rules: RuleSet | None = None) -> list[dict[str, Any]]:
    """Chaque mot-clé de l'offre : statut de preuve, présence dans le CV, et POURQUOI (présent / pas ajouté)."""
    rules = rules or load_rules()
    by_term = {norm(r.term.split(" ")[0] if r.kind == "language" else r.term): r for r in requirements
               if r.kind in ("keyword", "language")}
    text_n = norm(cv_text or "")
    out = []
    for kw in analysis.keywords:
        r = by_term.get(norm(kw.term))
        status = r.proof.status if r else UNPROVEN
        forms = rules.synonyms.equivalents(kw.term)
        present = bool(cv_text) and any(contains_term(text_n, f) for f in forms)
        if present and status == PROVEN:
            why = "Présent : prouvé par " + ", ".join(r.proof.fact_ids[:3]) + "."
        elif present and status == PLAUSIBLE:
            why = f"Présent sous une forme prudente : {r.proof.via}."
        elif present:
            why = "Présent dans le CV source, mais aucun fait du profil ne le prouve : à vérifier."
        elif status == PROVEN:
            why = "Prouvé mais pas encore dans le CV : à placer (place limitée ou priorité faible)." if cv_text else "Prouvé par le profil."
        elif status == PLAUSIBLE:
            why = f"Pas ajouté tel quel : {r.proof.via}. À formuler prudemment ou à préparer pour l'entretien."
        else:
            why = "Pas ajouté : aucun fait ne le prouve. L'écrire gonflerait le score au prix de la vérité."
            if r and r.proof.related:
                why += f" Compétence voisine prouvée : {', '.join(r.proof.related)}."
        out.append({"term": kw.term, "priority": kw.priority, "class": {"REQUIRED": "MUST", "NICE": "NICE_TO_HAVE"}.get(kw.priority, "IMPORTANT"),
                    "status": status, "status_label": LABELS[status], "in_cv": present,
                    "match": r.proof.match if r else "", "fact_ids": r.proof.fact_ids[:4] if r else [], "why": why})
    return out


def keywords_dim(entries: list[dict[str, Any]], has_cv: bool) -> tuple[float | None, list[dict[str, Any]], str]:
    if not entries:
        return None, [], "Aucun mot-clé extrait de l'offre."
    total = sum(KW_WEIGHT[e["priority"]] for e in entries)
    if has_cv:
        got = sum(KW_WEIGHT[e["priority"]] for e in entries if e["in_cv"])
        summary = f"{sum(e['in_cv'] for e in entries)}/{len(entries)} mots-clés présents dans le CV"
    else:
        got = sum(KW_WEIGHT[e["priority"]] * (1.0 if e["status"] == PROVEN else 0.5 if e["status"] == PLAUSIBLE else 0)
                  for e in entries)
        summary = f"{sum(e['status'] == PROVEN for e in entries)}/{len(entries)} mots-clés prouvés par le profil (avant CV)"
    details = [crit(e["term"], OK if (e["in_cv"] if has_cv else e["status"] == PROVEN) else
                    WARNING if e["status"] != UNPROVEN else ERROR, e["why"]) for e in entries]
    return 100 * got / total, details, summary


# ── Matching, expérience, formation, langues ─────────────────────────────────────────────────────
def matching_dim(reqs: list[Requirement]) -> tuple[float | None, list[dict[str, Any]], str]:
    scored = [r for r in reqs if r.klass != "CONTEXT"]
    if not scored:
        return None, [], "Aucune exigence exploitable."
    from .requirements import coverage

    details = []
    for klass in ("MUST", "IMPORTANT", "NICE_TO_HAVE"):
        rs = [r for r in scored if r.klass == klass]
        if rs:
            p = sum(r.proof.status == PROVEN for r in rs)
            q = sum(r.proof.status == PLAUSIBLE for r in rs)
            details.append(crit(LABELS[klass], OK if p == len(rs) else WARNING if p + q == len(rs) else ERROR,
                                f"{p} prouvée(s), {q} possible(s), {len(rs) - p - q} non prouvée(s) sur {len(rs)}",
                                100 * (p + 0.5 * q) / len(rs)))
    must = [r for r in scored if r.klass == "MUST"]
    must_ok = sum(r.proof.status == PROVEN for r in must)
    summary = f"{must_ok}/{len(must)} exigences obligatoires prouvées" if must else \
        f"{sum(r.proof.status == PROVEN for r in scored)}/{len(scored)} exigences prouvées"
    return coverage(scored), details, summary


def experience_dim(match: Match, reqs: list[Requirement]) -> tuple[float, list[dict[str, Any]], str]:
    s = match.scores
    value = 0.4 * s.get("role", 50) + 0.35 * s.get("experience", 50) + 0.25 * s.get("seniority", 50)
    years = next((r for r in reqs if r.kind == "experience"), None)
    details = [crit("Intitulés proches du poste", OK if s.get("role", 0) >= 75 else WARNING, "", s.get("role")),
               crit("Durée d'expérience", OK if s.get("experience", 0) >= 80 else WARNING,
                    years.proof.via or years.proof.note if years else "aucune durée exigée", s.get("experience")),
               crit("Séniorité", OK if s.get("seniority", 0) >= 70 else WARNING, "", s.get("seniority"))]
    return value, details, "rôle, durée et niveau comparés à l'offre"


def education_dim(match: Match, reqs: list[Requirement], analysis: Analysis) -> tuple[float, list[dict[str, Any]], str]:
    r = next((x for x in reqs if x.kind == "degree"), None)
    if not r:
        return match.scores.get("degree", 70), [crit("Diplôme", OK, "aucun niveau exigé par l'offre")], "aucun niveau exigé"
    return (match.scores.get("degree", 70), [crit(f"Diplôme demandé : {analysis.degree_required}",
                                                  OK if r.proof.status == PROVEN else ERROR, r.proof.via or r.proof.note)],
            LABELS[r.proof.status])


def languages_dim(match: Match, reqs: list[Requirement]) -> tuple[float, list[dict[str, Any]], str]:
    langs = [r for r in reqs if r.kind == "language"]
    if not langs:
        return match.scores.get("language", 80), [crit("Langues", OK, "aucune langue exigée par l'offre")], "aucune langue exigée"
    details = [crit(r.text, OK if r.proof.status == PROVEN else WARNING if r.proof.status == PLAUSIBLE else ERROR,
                    r.proof.note or r.proof.via) for r in langs]
    w = {r.id: CLASS_WEIGHT[r.klass] or 1.0 for r in langs}
    value = 100 * sum(w[r.id] * (1.0 if r.proof.status == PROVEN else 0.5 if r.proof.status == PLAUSIBLE else 0)
                      for r in langs) / sum(w.values())
    return value, details, f"{sum(r.proof.status == PROVEN for r in langs)}/{len(langs)} langue(s) prouvée(s)"


def conditions_dim(match: Match, analysis: Analysis) -> tuple[float, list[dict[str, Any]], str]:
    s = match.scores
    loc, con, av = s.get("location", 60), s.get("contract", 70), s.get("availability", 60)
    details = [crit(f"Lieu : {analysis.location if analysis.location != 'UNKNOWN' else 'non précisé'}",
                    OK if loc >= 80 else WARNING if loc >= 50 else ERROR,
                    "dans la mobilité déclarée" if loc >= 80 else "mobilité à confirmer" if loc >= 50 else "hors mobilité déclarée", loc),
               crit(f"Contrat : {analysis.contract if analysis.contract != 'UNKNOWN' else 'non précisé'}",
                    OK if con >= 75 else WARNING, "", con),
               crit("Disponibilité", OK if av >= 80 else WARNING, "déclarée dans le profil" if av >= 80 else "non renseignée", av)]
    return 0.5 * loc + 0.3 * con + 0.2 * av, details, "lieu, contrat, disponibilité"


def factuality_dim(report: ValidationReport | None) -> tuple[float | None, list[dict[str, Any]], str]:
    if report is None or not report.total:
        return None, [], "mesurée sur le CV généré"
    rejected = [v for v in report.verdicts if not v.ok]
    details = [crit("Lignes prouvées", OK if report.traced == report.total else ERROR, f"{report.traced}/{report.total}"),
               crit("Termes interdits", OK if not report.forbidden_hits else ERROR, str(report.forbidden_hits))]
    details += [crit(f"Ligne retirée ({v.line_id})", ERROR, "; ".join(v.reasons)) for v in rejected[:6]]
    return report.factuality, details, f"{report.traced}/{report.total} lignes prouvées"


# ── Mode A : CV seul ─────────────────────────────────────────────────────────────────────────────
ACTION_WORDS = set("""
developpe gere pilote negocie prospecte conseille vendu cree lance organise anime suivi recrute forme encadre optimise
augmente reduit atteint depasse concu redige analyse coordonne accompagne fidelise qualifie realise mis mene conduit
assure livre produit genere signe converti structure implemente deploye ameliore obtenu remporte ouvert construit
supervise pilote planifie redige presente participe contribue developpement gestion prospection negociation suivi
conseil vente creation organisation animation pilotage recrutement accompagnement fidelisation qualification analyse
coordination redaction mise elaboration lancement optimisation developed managed led negotiated sold created launched
organized built delivered increased reduced achieved exceeded designed coordinated
""".split())
_ACTION_STEMS = {stem(w) for w in ACTION_WORDS}
SUPERLATIVES = re.compile(r"\b(expert|expertise reconnue|meilleur|meilleure|n°\s?1|numero 1|exceptionnel|exceptionnelle|"
                          r"parfait|parfaite|parfaitement|incontournable|hors pair|world[- ]class|100 ?% (?:de )?reussite)\b")


def _bullets(p: ParsedCv) -> list[str]:
    bs = [b for e in p.experiences for b in e.bullets]
    return bs or [ln for ln in p.sections.get("experience", []) if len(ln.split()) >= 4]


def readability_dim(p: ParsedCv, pages: int | None) -> tuple[float, list[dict[str, Any]], str]:
    bs = _bullets(p)
    avg = sum(len(b.split()) for b in bs) / len(bs) if bs else 0
    long = [b for b in bs if len(b.split()) > 30]
    details, score = [], 100.0
    ok_avg = 6 <= avg <= 24
    details.append(crit("Longueur des puces", OK if ok_avg else WARNING, f"{avg:.0f} mots en moyenne (idéal : 8 à 22)".replace(".", ",")))
    score -= 0 if ok_avg else 15
    details.append(crit("Puces trop longues (> 30 mots)", OK if not long else WARNING, str(len(long))))
    score -= min(20, 5 * len(long))
    ok_len = 180 <= p.words <= 900
    details.append(crit("Longueur du document", OK if ok_len else WARNING, f"{p.words} mots (idéal : 250 à 700)"))
    score -= 0 if ok_len else 15
    formats = {("mois" if re.search(r"[a-z]", d) else "num") for d in p.dates if re.search(r"(19|20)\d{2}", d)}
    details.append(crit("Dates homogènes", OK if len(formats) <= 1 else WARNING,
                        "un seul format" if len(formats) <= 1 else "formats mélangés (mois en lettres et en chiffres)"))
    score -= 0 if len(formats) <= 1 else 10
    if pages is not None:
        details.append(crit("Pagination", OK if pages <= 2 else WARNING, f"{pages} page(s)"))
        score -= 0 if pages <= 2 else 15
    return score, details, f"{avg:.0f} mots par puce, {p.words} mots au total".replace(".", ",")


def content_dim(p: ParsedCv, rules: RuleSet | None = None) -> tuple[float, list[dict[str, Any]], str]:
    rules = rules or load_rules()
    bs = _bullets(p)
    first = [norm(b).split(" ")[0] if b.strip() else "" for b in bs]
    action = sum(1 for w in first if w in ACTION_WORDS or stem(w) in _ACTION_STEMS)
    quant = sum(1 for b in bs if extract_numbers(b))
    hard, soft = rules.banned_found("\n".join(p.lines))
    details = [crit("Puces qui commencent par une action", OK if bs and action / len(bs) >= 0.6 else WARNING,
                    f"{action}/{len(bs)}"),
               crit("Résultats chiffrés", OK if bs and quant / len(bs) >= 0.3 else WARNING, f"{quant}/{len(bs)} puces"),
               crit("Compétences précises", OK if len(p.skills) >= 5 else WARNING, f"{len(p.skills)} élément(s)"),
               crit("Profil / résumé", OK if "summary" in p.order else WARNING, "présent" if "summary" in p.order else "absent"),
               crit("Phrases creuses", OK if not (hard or soft) else WARNING if not hard else ERROR,
                    ", ".join((hard + soft)[:5]) or "aucune")]
    score = (35 * (action / len(bs) if bs else 0) + 30 * min(1.0, (quant / len(bs)) / 0.3 if bs else 0)
             + 15 * min(1.0, len(p.skills) / 5) + 10 * ("summary" in p.order) + 10) - 10 * len(hard) - 3 * len(soft)
    return score, details, f"{quant} résultat(s) chiffré(s), {action} puce(s) d'action"


def coherence_dim(p: ParsedCv, today: date | None = None) -> tuple[float, list[dict[str, Any]], str]:
    today = today or date.today()
    now = f"{today.year}-{today.month:02d}"
    bad = []
    for e in p.experiences:
        start, end = e.start, (now if e.end in ("present", "") else e.end)
        if start and start[:7] > now:
            bad.append(f"{e.title or e.dates} : début dans le futur")
        elif start and end and start[:4] > end[:4]:
            bad.append(f"{e.title or e.dates} : fin avant le début")
    sup = sorted({m.group(0) for m in SUPERLATIVES.finditer(norm("\n".join(p.lines)))})
    details = [crit("Dates possibles", OK if not bad else ERROR, "; ".join(bad) or "aucune incohérence"),
               crit("Affirmations invérifiables", OK if not sup else WARNING, ", ".join(sup) or "aucune")]
    return 100 - 20 * len(bad) - 6 * len(sup), details, "cohérence interne (sans profil de référence)"
