"""Exigences de l'offre : classement et preuve.

Classement (ce que l'offre demande) :
  MUST          obligatoire (« indispensable », « requis », « exigé »…)
  IMPORTANT     mission ou compétence clé, sans marqueur d'obligation
  NICE_TO_HAVE  un plus (« apprécié », « idéalement », « est un plus »…)
  CONTEXT       information sur le poste ou l'entreprise (télétravail, taille, salaire…) : jamais comptée comme exigence

Preuve (ce que le profil démontre), par ordre de force :
  PROUVÉ      un fait le dit : mot exact, forme proche (« prospecter » ↔ « prospection ») ou synonyme DÉCLARÉ
              (rules/skill_synonyms.yaml) — correspondance EXACT ou SYNONYME
  PLAUSIBLE   « correspondance possible » : déduction (HubSpot → CRM), famille métier, niveau de langue inférieur,
              mots en partie présents, proximité de sens (embeddings locaux en option) — correspondance SÉMANTIQUE
  NON_PROUVÉ  aucun fait ; une compétence VOISINE prouvée est seulement signalée (Salesforce demandé, HubSpot prouvé)

Une exigence PLAUSIBLE ou NON PROUVÉE n'est jamais écrite dans le CV pour gonfler un score.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..analyzer import _MUST, _NICE, _sentences
from ..claims import LANGUAGES, LEVEL_WORDS
from ..rules import RuleSet, load_rules
from ..schemas import Analysis, MasterProfile
from ..textnorm import contains_term, norm, stable_hash
from . import lexicon, semantic

CLASSES = ("MUST", "IMPORTANT", "NICE_TO_HAVE", "CONTEXT")
PROVEN, PLAUSIBLE, UNPROVEN = "PROUVÉ", "PLAUSIBLE", "NON_PROUVÉ"
STATUSES = (PROVEN, PLAUSIBLE, UNPROVEN)
LABELS = {"MUST": "Obligatoire", "IMPORTANT": "Important", "NICE_TO_HAVE": "Un plus", "CONTEXT": "Contexte",
          PROVEN: "Prouvé", PLAUSIBLE: "Correspondance possible", UNPROVEN: "Non prouvé",
          "EXACT": "Exact", "SYNONYME": "Synonyme", "SÉMANTIQUE": "Proche"}
KEYWORD_CLASS = {"REQUIRED": "MUST", "IMPORTANT": "IMPORTANT", "NICE": "NICE_TO_HAVE"}
CLASS_WEIGHT = {"MUST": 3.0, "IMPORTANT": 2.0, "NICE_TO_HAVE": 1.0, "CONTEXT": 0.0}
STATUS_VALUE = {PROVEN: 1.0, PLAUSIBLE: 0.5, UNPROVEN: 0.0}
_RANK = {PROVEN: 2, PLAUSIBLE: 1, UNPROVEN: 0}
_MATCH_RANK = {"EXACT": 3, "SYNONYME": 2, "SÉMANTIQUE": 1, "": 0}

# ── Classement ───────────────────────────────────────────────────────────────────────────────────
_CONTEXT_STRONG = re.compile(r"teletravail|\bremote\b|salaire|remuneration|\bbrut\b|package|avantages?|mutuelle|"
                             r"tickets? restaurant|\brtt\b|horaires|prise de poste|date de debut|des que possible|"
                             r"temps plein|temps partiel|jours? par semaine|poste (est )?base|base a |locaux")
_CONTEXT = re.compile(r"salaries|collaborateurs|editeur|\bentreprise\b|societe|fondee?|filiale|chiffre d'affaires|situe|"
                      r"siege|start-?up|scale-?up|leader|creee? en|depuis \d{4}|nous sommes|notre (entreprise|societe|"
                      r"groupe|equipe)|rejoindre|ambiance|\bcdi\b|\bcdd\b|contrat|\brecrute\b|\brecrutons\b")
# Verbe d'action en tête : infinitif en -er (sauf noms courants), ou verbe en -ir / -re d'une liste fermée
# (« salaire », « titre », « offre » finissent aussi en -re : une règle trop large les prendrait pour des verbes).
_NOT_VERBS = set("""premier derniere dernier entier leger cher fier hier papier metier chantier quartier dossier fichier atelier
clavier panier janvier fevrier courrier cahier calendrier particulier foyer loyer hiver super other customer manager leader
partner user power career developer offer after number better order officer""".split())
_IR_RE_VERBS = set("""suivre conduire construire produire promouvoir entreprendre prendre mettre reduire traduire ecrire decrire
lire fournir definir etablir garantir accueillir recueillir reussir saisir maintenir obtenir tenir soutenir convertir investir
batir enrichir elargir repondre vendre rendre defendre entretenir developper remplir agir choisir ouvrir couvrir offrir
servir partir sortir venir devenir intervenir parcourir recourir atteindre""".split())
_ACTION_NOUN = re.compile(r"^(?:prospection|gestion|suivi|developpement|qualification|negociation|animation|pilotage|"
                          r"organisation|participation|redaction|creation|accompagnement|conseil|vente|mise en place|"
                          r"elaboration|analyse|reporting|veille|relation|fidelisation|recrutement|sourcing)\b")


def _starts_with_action(t: str) -> bool:
    t = re.sub(r"^vous (?:allez |serez |aurez |devrez )?", "", t)
    if _ACTION_NOUN.search(t):
        return True
    first = re.match(r"[a-z]+", t)
    w = first.group(0) if first else ""
    return (len(w) > 4 and w.endswith("er") and w not in _NOT_VERBS) or w in _IR_RE_VERBS


def classify_requirement(text: str, *, section: str = "") -> str:
    """section : « profile », « mission », « company » (présentation) ou vide si inconnu."""
    t = re.sub(r"^[-•*·▪►✓✔\d.)\s]+", "", norm(text))
    if not t:
        return "CONTEXT"
    # « Maîtrise d'un CRM (HubSpot idéalement) » : le « un plus » entre parenthèses ne vise que la parenthèse.
    if _NICE.search(re.sub(r"\([^)]*\)", " ", t)):
        return "NICE_TO_HAVE"
    action = _starts_with_action(t)
    if _CONTEXT_STRONG.search(t) and not action:
        return "CONTEXT"
    if _MUST.search(t) or re.search(r"\bessentiel|imperatif|exige", t):
        return "MUST"
    if action or section in ("profile", "mission"):
        return "IMPORTANT"
    if section == "company" or _CONTEXT.search(t):
        return "CONTEXT"
    return "IMPORTANT"


# ── Preuve ───────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Proof:
    status: str = UNPROVEN
    match: str = ""                                        # EXACT | SYNONYME | SÉMANTIQUE
    via: str = ""                                          # explication lisible
    fact_ids: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)       # compétences voisines prouvées : jamais une preuve
    note: str = ""

    def better_than(self, other: "Proof") -> bool:
        return (_RANK[self.status], _MATCH_RANK[self.match]) > (_RANK[other.status], _MATCH_RANK[other.match])

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"label": LABELS[self.status]}


Evidence = list[tuple[str, str]]   # (identifiant du fait, texte normalisé du fait et de son parent)


def _implying_key(term: str, ev: str, rules: RuleSet) -> str:
    targets = rules.synonyms.equivalents(term)
    for key, implied in rules.synonyms.implies.items():
        if targets & {norm(x) for x in implied} and contains_term(ev, key):
            return key
    return ""


def _language(t: str) -> str:
    return next((w for w in LANGUAGES if contains_term(t, w)), "")


def _level(t: str) -> tuple[int, str]:
    found = [(v, w) for w, v in LEVEL_WORDS.items() if contains_term(t, w)]
    return max(found) if found else (0, "")


def _prove_language(t: str, word: str, evidence: Evidence) -> Proof:
    code = LANGUAGES[word]
    names = [w for w, c in LANGUAGES.items() if c == code]
    need, need_w = _level(t)
    hits = [(fid, ev) for fid, ev in evidence if any(contains_term(ev, n) for n in names)]
    if not hits:
        return Proof(note=f"Aucun fait ne mentionne la langue « {word} ».")
    have, have_w = max((_level(ev) for _, ev in hits), default=(0, ""))
    exact = any(contains_term(ev, word) for _, ev in hits)
    ids = [fid for fid, _ in hits][:4]
    if not need or have >= need:
        return Proof(PROVEN, "EXACT" if exact else "SYNONYME", "langue et niveau prouvés" if need else "langue prouvée", ids)
    if not have:
        return Proof(PLAUSIBLE, "SÉMANTIQUE", "langue prouvée, niveau non précisé", ids,
                     note=f"Niveau demandé : {need_w}. Préciser le niveau réel dans le profil.")
    return Proof(PLAUSIBLE, "SÉMANTIQUE", "langue prouvée, niveau inférieur", ids,
                 note=f"Niveau demandé : {need_w} ; niveau prouvé : {have_w}. Ne pas surévaluer.")


def prove(term: str, evidence: Evidence, rules: RuleSet | None = None, *, embedder: Any = None) -> Proof:
    """Preuve d'une notion (mot-clé ou courte exigence) par les faits. Déterministe sauf `embedder` (optionnel)."""
    rules = rules or load_rules()
    t, c = norm(term), lexicon.core(term)
    if not t:
        return Proof()
    lang = _language(t)
    if lang:
        return _prove_language(t, lang, evidence)
    best = Proof()
    for cand in dict.fromkeys(x for x in (t, c) if x):
        for fid, ev in evidence:
            how = rules.synonyms.supported_by(cand, ev)
            if not how:
                continue
            if how == "implique":
                key = _implying_key(cand, ev, rules)
                p = Proof(PLAUSIBLE, "SÉMANTIQUE", f"déduit de « {key} »" if key else "déduction", [fid],
                          note="Déduction (règle déclarée), pas une mention explicite : formulation prudente.")
            else:
                p = Proof(PROVEN, "EXACT" if how == "direct" else "SYNONYME",
                          "mention directe" if how == "direct" else "synonyme déclaré", [fid])
            if p.better_than(best):
                best = p
            elif p.status == best.status and p.match == best.match and fid not in best.fact_ids:
                best.fact_ids.append(fid)
    if best.status == PROVEN:
        best.fact_ids = best.fact_ids[:6]
        return best

    key = c or t
    # Famille métier : « un CRM » demandé, « HubSpot » prouvé → correspondance possible.
    fam = semantic.family_of_category(key)
    if fam and best.status == UNPROVEN:
        for fid, ev in evidence:
            found = semantic.members_in(ev, fam)
            if found:
                best = Proof(PLAUSIBLE, "SÉMANTIQUE", f"« {found[0]} » appartient à la famille {fam.label}", [fid],
                             note="Famille métier : pas une mention explicite.")
                break
    # Membre d'une famille : « Salesforce » demandé, « HubSpot » prouvé → voisin signalé, statut inchangé.
    related: list[str] = []
    for f in semantic.families_of_member(key):
        for _, ev in evidence:
            related += [m for m in semantic.members_in(ev, f, exclude=key) if m not in related]
    best.related = related[:4]

    # Formes proches (racines) : toutes les notions dans un même fait.
    words = lexicon.content_tokens(key)
    need = {lexicon.stem(w) for w in words}
    if need and best.status == UNPROVEN:
        for fid, ev in evidence:
            have = lexicon.stems(ev)
            if need <= have:
                best = (Proof(PROVEN, "EXACT", "forme proche", [fid]) if len(need) <= 2 else
                        Proof(PLAUSIBLE, "SÉMANTIQUE", "tous les mots présents, formulation différente", [fid]))
                break
    if best.status == UNPROVEN and words:
        union: set[str] = set()
        for _, ev in evidence:
            union |= lexicon.stems(ev)
        if len(words) == 1:
            w0 = lexicon.stem(words[0])
            hit = words if any(lexicon.stem_related(w0, s) or lexicon.fuzzy_equal(w0, s) for s in union) else []
        else:
            hit = [w for w in words if lexicon.stem(w) in union]
        if hit and (len(words) == 1 or (len(hit) >= 2 and len(hit) / len(words) >= 0.5)):
            miss = [w for w in words if w not in hit]
            ids = [fid for fid, ev in evidence if any(contains_term(ev, w) for w in hit)][:3]
            best = Proof(PLAUSIBLE, "SÉMANTIQUE", "mots proches : " + ", ".join(hit), ids,
                         note=("non prouvé : " + ", ".join(miss)) if miss else "forme voisine, à vérifier")
    if best.status == UNPROVEN and embedder is not None and evidence:
        try:
            score, i = embedder.best(term, [ev for _, ev in evidence])
            if score >= embedder.threshold:
                best = Proof(PLAUSIBLE, "SÉMANTIQUE", f"proximité de sens (modèle local, {score:.2f})", [evidence[i][0]],
                             related=best.related, note="Rapprochement automatique : jamais une preuve.")
        except Exception:  # noqa: BLE001 — option : n'empêche jamais l'analyse déterministe
            pass
    if best.status == UNPROVEN:
        best.note = (f"Compétence voisine prouvée : {', '.join(best.related)}. À valoriser en entretien, ne pas l'écrire "
                     f"à la place de « {term} ».") if best.related else "Aucun fait ne le prouve : à ne pas écrire."
    return best


def proof_status_for_texts(requirement: str, texts: list[str]) -> str:
    """Raccourci (auto-évaluation) : statut d'une exigence face à une liste de faits en texte libre."""
    return prove(requirement, [(f"t{i}", norm(x)) for i, x in enumerate(texts)]).status


# ── Exigences d'une offre ───────────────────────────────────────────────────────────────────────
@dataclass
class Requirement:
    id: str
    text: str
    term: str
    kind: str                     # keyword | language | sentence | mission | degree | experience
    klass: str
    source: str = ""
    proof: Proof = field(default_factory=Proof)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["class"] = d.pop("klass")
        d["proof"] = self.proof.as_dict()
        d["class_label"] = LABELS[self.klass]
        return d


def display_term(term: str) -> str:
    t = term.strip()
    if re.fullmatch(r"[a-z0-9+#]{2,4}", t) and not t.isdigit():
        return t.upper()
    return t[:1].upper() + t[1:]


def _source(sentences: list[str], term: str) -> str:
    hits = [s for s in sentences if contains_term(norm(s), term)]
    return max(hits, key=lambda s: bool(_MUST.search(norm(s))), default="")[:200]


def extract(analysis: Analysis, offer_text: str = "") -> list[Requirement]:
    sentences = _sentences(offer_text) if offer_text else []
    out: list[Requirement] = []
    langs = {norm(x.get("name", "")): x for x in analysis.languages}
    for kw in analysis.keywords:
        lang = langs.get(norm(kw.term))
        level = str(lang.get("level", "")) if lang else ""
        term = f"{kw.term} {level}".strip() if lang and level not in ("", "UNKNOWN") else kw.term
        out.append(Requirement(f"kw.{stable_hash(norm(kw.term), 8)}", display_term(term), term, "language" if lang else "keyword",
                               KEYWORD_CLASS.get(kw.priority, "IMPORTANT"), _source(sentences, kw.term)))
    seen = {norm(r.text) for r in out}
    for section, items in (("profile", analysis.recruiter_wants.get("explicit", [])), ("mission", analysis.missions)):
        for s in items:
            if norm(s) in seen:
                continue
            seen.add(norm(s))
            out.append(Requirement(f"{section[:3]}.{stable_hash(norm(s), 8)}", s, s, "sentence" if section == "profile" else "mission",
                                   classify_requirement(s, section=section), s))
    if analysis.degree_required not in ("", "UNKNOWN"):
        src = next((s for s in sentences if DEGREE_RE.search(norm(s))), "")
        out.append(Requirement("degree", f"Diplôme : {analysis.degree_required}", analysis.degree_required, "degree",
                               "MUST" if _MUST.search(norm(src)) else "IMPORTANT", src))
    if analysis.experience_years_min:
        y = analysis.experience_years_min
        src = next((s for s in sentences if YEARS_RE.search(norm(s))), "")
        out.append(Requirement("experience", f"Expérience : {y:g} an{'s' if y > 1 else ''} minimum", str(y), "experience",
                               "NICE_TO_HAVE" if _NICE.search(norm(src)) else "MUST", src))
    return out


def evidence_index(profile: MasterProfile) -> Evidence:
    from ..matching import fact_evidence_index

    return [(f.id, text) for f, text in fact_evidence_index(profile)]


def _profile_degree(profile: MasterProfile) -> tuple[int, str]:
    t = norm(" ".join(f.text for f in profile.by_kind("education") if f.usable))
    for level, label, pattern in ((5, "Bac+5", r"\bmaster\b|\bmsc\b|bac\s?\+\s?5|\bm2\b|grande ecole|ingenieur"),
                                  (4, "Bac+4", r"bac\s?\+\s?4|\bm1\b|master 1"),
                                  (3, "Bac+3", r"bachelor|licence|bac\s?\+\s?3|\bbut\b"),
                                  (2, "Bac+2", r"\bbts\b|\bdut\b|bac\s?\+\s?2"), (1, "Bac", r"\bbac\b|baccalaureat")):
        if re.search(pattern, t):
            return level, label
    return 0, ""


def _prove_degree(profile: MasterProfile, required: str) -> Proof:
    need = {"Bac+5": 5, "Bac+4": 4, "Bac+3": 3, "Bac+2": 2, "Bac": 1}.get(required, 0)
    have, label = _profile_degree(profile)
    ids = [f.id for f in profile.by_kind("education") if f.usable][:3]
    if need and have >= need:
        return Proof(PROVEN, "EXACT", f"diplôme prouvé : {label}", ids)
    return Proof(note=f"Niveau demandé : {required} ; niveau prouvé : {label or 'aucun diplôme renseigné'}. "
                      "Ne jamais ajouter ni gonfler un diplôme.", fact_ids=ids)


def _prove_years(profile: MasterProfile, years: float) -> Proof:
    from ..matching import _months

    months = sum(_months(e.data.get("start"), e.data.get("end")) for e in profile.experiences())
    have = months / 12
    ids = [e.id for e in profile.experiences()][:4]
    text = f"{have:.1f}".replace(".", ",") + f" an(s) d'expérience cumulée pour {years:g} demandé(s)"
    if have >= years:
        return Proof(PROVEN, "EXACT", text, ids)
    if have >= 0.6 * years:
        return Proof(PLAUSIBLE, "SÉMANTIQUE", text, ids, note="Durée un peu courte : mettre en avant l'intensité et les résultats.")
    return Proof(note=text + ".", fact_ids=ids)


DEGREE_RE = re.compile(r"bac\s?\+|\bmaster\b|\blicence\b|\bbachelor|diplom|ecole de commerce|\bbts\b|\bdut\b")
YEARS_RE = re.compile(r"\d+\s?(?:\+\s?)?(?:ans?|years?)\b")
_CONTEXT_WORDS = set("""stage stages alternance cdi cdd interim freelance contrat poste postes entreprise societe semaine
semaines mois jour jours an ans annee annees heure heures temps plein partiel nouveau nouveaux nouvelle nouvelles chaque
sont sera seront divers diverses differents differentes ensemble""".split())
SOFT = {"tenacite", "organisation", "challenge", "curiosite", "dynamisme", "rigueur", "autonomie", "adaptabilite",
        "ecoute", "polyvalence", "reactivite", "patience", "precision", "discretion", "fiabilite", "communication",
        "aisance", "relationnel", "relationnelle", "esprit", "equipe", "motivation", "motive", "motivee", "energie",
        "enthousiasme", "persuasion", "resilience", "creativite", "proactivite", "proactif", "proactive", "empathie"}


def sentence_words(text: str) -> list[str]:
    return [w for w in lexicon.content_tokens(text) if w not in _CONTEXT_WORDS and not re.fullmatch(r"\d+(?:[.,]\d+)?k?", w)]


def _contains_keyword(tn: str, sent_stems: set[str], r: "Requirement") -> bool:
    base = r.term.split(" ")[0] if r.kind == "language" else r.term
    kst = {lexicon.stem(w) for w in lexicon.content_tokens(base)}
    return contains_term(tn, base) or bool(kst and kst <= sent_stems)


def _prove_sentence(text: str, keyword_reqs: list["Requirement"], evidence: Evidence,
                    special: dict[str, Proof] | None = None) -> Proof:
    tn = norm(text)
    special = special or {}
    if "degree" in special and DEGREE_RE.search(tn):
        return Proof(**{**asdict(special["degree"])})
    if "experience" in special and YEARS_RE.search(tn):
        return Proof(**{**asdict(special["experience"])})
    words = sentence_words(text)
    stems_ = {lexicon.stem(w) for w in words}
    inside = [r for r in keyword_reqs if _contains_keyword(tn, stems_, r)]
    union: set[str] = set()
    for _, ev in evidence:
        union |= lexicon.stems(ev)
    covered = [w for w in words if lexicon.stem(w) in union or any(lexicon.stem_related(lexicon.stem(w), s) for s in union)]
    share = len(covered) / len(words) if words else 0.0
    first_ok = bool(words) and words[0] in covered
    ids: list[str] = []
    for r in inside:
        ids += [i for i in r.proof.fact_ids if i not in ids]
    missing = [w for w in words if w not in covered]
    note = ("non prouvé : " + ", ".join(missing[:6])) if missing else ""
    if words and all(w in SOFT for w in words):
        return Proof(note="Qualités personnelles : aucune preuve écrite possible, à illustrer en entretien par un exemple réel.")
    if words and first_ok and share >= 0.5 and all(r.proof.status == PROVEN for r in inside) and (inside or share >= 0.75):
        worst = min((r.proof.match for r in inside), key=lambda m: _MATCH_RANK[m]) if inside else "EXACT"
        via = ("mots-clés prouvés : " + ", ".join(r.term for r in inside)) if inside else "mots présents dans les faits"
        if not ids:
            ids = [fid for fid, ev in evidence if any(contains_term(ev, w) for w in covered)][:3]
        return Proof(PROVEN, worst, via, ids[:6], note=note)
    if any(r.proof.status != UNPROVEN for r in inside) or share >= 0.34 or first_ok:
        via = ("mots-clés : " + ", ".join(f"{r.term} ({LABELS[r.proof.status].lower()})" for r in inside)) if inside else \
              "mots proches : " + ", ".join(covered[:6])
        if not ids:
            ids = [fid for fid, ev in evidence if any(contains_term(ev, w) for w in covered)][:3]
        return Proof(PLAUSIBLE, "SÉMANTIQUE", via, ids[:6], note=note)
    return Proof(note="Aucun fait ne le prouve : à préparer pour l'entretien, à ne pas écrire.")


def prove_all(requirements: list[Requirement], profile: MasterProfile, analysis: Analysis,
              rules: RuleSet | None = None, *, embedder: Any = None) -> list[Requirement]:
    rules = rules or load_rules()
    evidence = evidence_index(profile)
    keywords = [r for r in requirements if r.kind in ("keyword", "language")]
    for r in keywords:
        r.proof = prove(r.term, evidence, rules, embedder=embedder)
    special: dict[str, Proof] = {}
    for r in requirements:
        if r.kind == "degree":
            r.proof = special["degree"] = _prove_degree(profile, analysis.degree_required)
        elif r.kind == "experience":
            r.proof = special["experience"] = _prove_years(profile, float(r.term))
    for r in requirements:
        if r.klass == "CONTEXT":
            r.proof = Proof(note="Information sur le poste : aucune preuve attendue.")
        elif r.kind in ("sentence", "mission"):
            r.proof = _prove_sentence(r.text, keywords, evidence, special)
    return requirements


def coverage(requirements: list[Requirement]) -> float:
    """Part pondérée des exigences couvertes (MUST ×3, IMPORTANT ×2, un plus ×1 ; prouvé 1, possible 0,5)."""
    total = sum(CLASS_WEIGHT[r.klass] for r in requirements)
    got = sum(CLASS_WEIGHT[r.klass] * STATUS_VALUE[r.proof.status] for r in requirements)
    return round(100 * got / total, 1) if total else 0.0
