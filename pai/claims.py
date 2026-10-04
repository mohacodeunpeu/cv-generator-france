"""Validateur DÉTERMINISTE claim → evidence (règle A2, sans IA).

Chaque ligne générée porte `fact_ids`. Une ligne est acceptée seulement si :
  - ses faits existent et ont un statut autorisé (CONFIRMED, IMPORTED, INFERRED approuvé) ;
  - chaque nombre, date, nom propre, diplôme, outil, langue ou niveau cité existe dans ses faits
    (comparaison normalisée ; équivalences uniquement via rules/skill_synonyms.yaml) ;
  - aucun terme interdit (ex. MBA) n'apparaît ;
  - le niveau de responsabilité n'est pas gonflé ;
  - aucune phrase creuse « dure » n'est utilisée.
Le juge IA d'exagération (prompts/factuality_judge.md) complète ce contrôle sans le remplacer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .profile import LEVELS
from .rules import RuleSet, load_rules
from .schemas import CvDocument, Fact, LetterDocument, Line, LineVerdict, MasterProfile, ValidationReport
from .textnorm import contains_term, extract_numbers, norm

# ── Lexiques de termes « à risque » ──────────────────────────────────────────

TOOLS = [
    "hubspot", "salesforce", "pipedrive", "zoho", "sap", "oracle", "sage", "odoo", "dynamics", "microsoft dynamics",
    "sales navigator", "linkedin sales navigator", "lemlist", "kaspr", "lusha", "dropcontact", "apollo", "zapier",
    "excel", "powerpoint", "microsoft word", "power bi", "tableau software", "looker", "google analytics", "google ads", "meta ads",
    "seo", "sem", "wordpress", "shopify", "prestashop", "wix", "webflow", "figma", "photoshop", "illustrator",
    "indesign", "canva", "notion", "trello", "asana", "jira", "slack", "microsoft teams", "python", "sql", "crm", "erp", "ats",
    "google suite", "google workspace", "mailchimp", "brevo", "sendinblue", "hootsuite", "chatgpt", "welcome to the jungle",
]
DEGREES = [
    "mba", "master", "mastere", "msc", "licence", "bachelor", "bts", "doctorat", "phd", "deug",
    "bac+2", "bac+3", "bac+4", "bac+5", "bac +2", "bac +3", "bac +4", "bac +5", "diplome", "diplomee", "diplomé",
    "grande ecole", "ecole de commerce", "ingenieur", "master 1", "master 2",
]
DEGREE_ACRONYMS = ["BUT", "DUT", "M1", "M2"]  # sensibles à la casse (« but » est un mot anglais)
CERTIFICATIONS = ["toeic", "toefl", "ielts", "cambridge", "delf", "dalf", "sst", "pmp", "prince2", "scrum", "itil",
                  "certification", "certifie", "certifiee", "habilitation"]
LANGUAGES = {
    "francais": "fr", "french": "fr", "anglais": "en", "english": "en", "arabe": "ar", "arabic": "ar",
    "espagnol": "es", "spanish": "es", "chinois": "zh", "mandarin": "zh", "chinese": "zh", "allemand": "de",
    "german": "de", "italien": "it", "italian": "it", "portugais": "pt", "portuguese": "pt", "neerlandais": "nl",
    "dutch": "nl", "russe": "ru", "japonais": "ja", "turc": "tr", "hindi": "hi",
}
LEVEL_WORDS = dict(LEVELS) | {"fluent": 5, "native": 7, "bilingual": 6, "maternelle": 7, "lu, ecrit, parle": 5,
                              "courante": 5, "professionnelle": 5}

LEADERSHIP = ["dirige", "dirigee", "dirigeant", "manage", "managee", "encadre", "encadree", "encadrement",
              "supervise", "supervisee", "direction d'equipe", "chef d'equipe", "responsable d'equipe",
              "management d'equipe", "manager une equipe", "a la tete", "head of", "team lead", "led a team",
              "managed a team", "supervised"]
OWNERSHIP = ["pilote", "pilotee", "piloter", "pilotage", "gere", "geree", "gerer", "gestion", "mene", "menee", "conduit",
             "realise", "realisee", "assure", "livre", "livres", "developpe", "coordonne", "coordination", "organise",
             "negocie", "negociation", "prospecte", "prospection", "vendu", "conseille", "recrute", "recrutement",
             "cree", "produit", "production", "optimise", "suivi", "responsable", "owned", "managed", "delivered"]
CONTRIBUTION = ["participe", "participee", "participation", "contribue", "contribuee", "contribution", "assiste",
                "assistee", "aide", "soutien", "appui", "en support", "assisted", "contributed", "participated"]

# Mots capitalisés qui ne sont pas des affirmations factuelles.
STOP_CAPITALIZED = {
    "je", "j'", "nous", "vous", "votre", "vos", "madame", "monsieur", "objet", "candidature", "cordialement",
    "bonjour", "profil", "experience", "experiences", "formation", "competences", "langues", "outils", "commercial",
    "commerciale", "digital", "cv", "lettre", "poste", "le", "la", "les", "un", "une", "des", "de", "du", "en", "et",
    "a", "au", "aux", "pour", "avec", "sur", "dans", "chez", "par", "ce", "cette", "ces", "mon", "ma", "mes", "son",
    "sa", "ses", "leur", "leurs", "il", "elle", "ils", "elles", "on", "si", "mais", "ou", "donc", "or", "ni", "car",
    "the", "and", "of", "to", "in", "for", "with", "at", "my", "our", "your", "i", "janvier", "fevrier", "mars",
    "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre", "janv", "fevr",
    "avr", "juil", "sept", "oct", "nov", "dec", "present", "aujourd'hui", "actuellement", "depuis", "puis", "ainsi",
    "enfin", "aussi", "egalement", "fort", "forte", "pret", "prete", "disponible", "ravi", "ravie",
}

_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][\wÀ-ÖØ-öø-ÿ'’&+./-]*")
_SENTENCE_BREAK = re.compile(r"[.!?:;•·|—–(\"«]\s*$")


@dataclass
class Evidence:
    text: str          # texte normalisé des faits liés (+ parent, + données)
    numbers: set[str]
    facts: list[Fact]


def _flatten(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        for v in value.values():
            yield from _flatten(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _flatten(v)
    elif value is not None:
        yield str(value)


def build_evidence(profile: MasterProfile, fact_ids: list[str]) -> Evidence:
    facts: list[Fact] = []
    chunks: list[str] = []
    for fid in fact_ids:
        fact = profile.fact(fid)
        if fact is None:
            continue
        facts.append(fact)
        chunks.append(fact.text)
        chunks.extend(_flatten({k: v for k, v in fact.data.items() if k != "raw"}))
        if fact.parent:
            parent = profile.fact(fact.parent)
            if parent is not None and parent.usable:
                chunks.append(parent.text)
                chunks.extend(_flatten({k: v for k, v in parent.data.items() if k != "raw"}))
    text = norm(" \n ".join(chunks))
    numbers: set[str] = set()
    for chunk in chunks:
        numbers.update(extract_numbers(chunk))
    return Evidence(text=text, numbers=numbers, facts=facts)


_TEAM_LEAD = re.compile(r"(manag|encadr|dirig|supervis|anim|lead)\w*\s+(d'|de\s+|des\s+|l'|la\s+|une\s+|un\s+)*"
                        r"(equipe|team|collaborateurs|commerciaux|stagiaires|personnes|vendeurs|conseillers)")


def _level_of(text_norm: str) -> int:
    if any(contains_term(text_norm, w) for w in LEADERSHIP) or _TEAM_LEAD.search(text_norm):
        return 3
    if any(contains_term(text_norm, w) for w in OWNERSHIP):
        return 2
    if any(contains_term(text_norm, w) for w in CONTRIBUTION):
        return 1
    return 0


def proper_noun_candidates(text: str) -> list[str]:
    """Groupes de mots capitalisés hors début de phrase + sigles / mots à majuscule interne."""
    candidates: list[str] = []
    current: list[str] = []
    prev_end = 0
    sentence_start = True
    for m in _WORD.finditer(text):
        word = m.group(0).rstrip(".,;:'’")
        gap = text[prev_end:m.start()]
        if prev_end and _SENTENCE_BREAK.search(text[:m.start()].rstrip() + " ") and gap.strip():
            sentence_start = True
        if prev_end == 0:
            sentence_start = True
        stripped = word.strip("'’")
        is_acronym = len(stripped) >= 2 and stripped.isupper() and any(c.isalpha() for c in stripped)
        internal_cap = any(c.isupper() for c in stripped[1:]) and not stripped.isupper()
        is_cap = stripped[:1].isupper()
        keep = False
        if is_acronym or internal_cap:
            keep = True
        elif is_cap and not sentence_start:
            keep = True
        elif is_cap and current:
            keep = True
        if keep and norm(stripped) not in STOP_CAPITALIZED:
            current.append(stripped)
        else:
            if current:
                candidates.append(" ".join(current))
                current = []
        # connecteurs internes des noms propres (« Printemps Haussmann », « Agence 113 / DEFI GROUPE »)
        prev_end = m.end()
        sentence_start = bool(_SENTENCE_BREAK.search(text[:m.end()] + " "))
    if current:
        candidates.append(" ".join(current))
    return candidates


class ClaimValidator:
    def __init__(self, profile: MasterProfile, offer_text: str = "", rules: RuleSet | None = None,
                 offer_terms: list[str] | None = None):
        self.profile = profile
        self.rules = rules or load_rules()
        self.offer_norm = norm(offer_text)
        self.offer_numbers = set(extract_numbers(offer_text))
        self.offer_terms_norm = norm(" ".join(offer_terms or []))
        self.forbidden = [norm(t) for t in profile.forbidden_terms() if norm(t)]

    # -- éléments communs ----------------------------------------------------
    def _supported(self, term: str, evidence: Evidence, allow_offer: bool) -> bool:
        if self.rules.synonyms.supported_by(term, evidence.text):
            return True
        if allow_offer and (contains_term(self.offer_norm, term) or contains_term(self.offer_terms_norm, term)):
            return True
        return False

    def validate_line(self, line: Line) -> LineVerdict:
        v = LineVerdict(line_id=line.id, ok=True)
        text = line.text.strip()
        if line.kind == "structure" or not text:
            return v
        t = norm(text)

        # 1. Termes interdits (MBA…) : rejet immédiat, pénalité -20.
        for term in self.forbidden:
            if contains_term(t, term):
                v.ok, v.forbidden = False, True
                v.reasons.append(f"Terme interdit : « {term} »")

        # 2. Phrases creuses
        hard, soft = self.rules.banned_found(text)
        for phrase in hard:
            v.ok = False
            v.reasons.append(f"Phrase creuse interdite : « {phrase} »")
        v.warnings.extend(f"Phrase à éviter : « {p} »" for p in soft)

        # 3. Faits liés
        needs_facts = line.kind in ("claim", "fact")
        unknown = [fid for fid in line.fact_ids if self.profile.fact(fid) is None]
        unusable = [fid for fid in line.fact_ids if (f := self.profile.fact(fid)) is not None and not f.usable]
        if unknown:
            v.ok = False
            v.reasons.append(f"Faits inexistants : {', '.join(unknown)}")
        if unusable:
            v.ok = False
            statuses = ", ".join(f"{fid} ({self.profile.fact(fid).status})" for fid in unusable)  # type: ignore[union-attr]
            v.reasons.append(f"Faits non utilisables (statut) : {statuses}")
        usable_ids = [fid for fid in line.fact_ids if fid not in unknown and fid not in unusable]
        if needs_facts and not usable_ids:
            v.ok = False
            v.reasons.append("Aucun fait source valide pour une affirmation")
        evidence = build_evidence(self.profile, usable_ids)
        allow_offer = line.kind in ("headline", "offer_ref", "projection", "closing")

        # 4. Citation de l'offre (offer_ref)
        if line.kind == "offer_ref":
            quote = norm(line.offer_quote)
            if not quote:
                v.ok = False
                v.reasons.append("offer_ref sans citation de l'offre")
            elif quote not in self.offer_norm:
                words = [w for w in re.findall(r"[a-z0-9]+", quote) if len(w) > 2]
                hits = sum(1 for w in words if contains_term(self.offer_norm, w))
                if not words or hits / len(words) < 0.85:
                    v.ok = False
                    v.reasons.append("Citation introuvable dans l'offre")

        # 5. Nombres (dates comprises)
        for num in extract_numbers(text):
            if num in evidence.numbers:
                continue
            if allow_offer and num in self.offer_numbers:
                continue
            v.ok = False
            v.reasons.append(f"Nombre sans preuve : {num}")

        # 6. Diplômes et certifications
        for term in DEGREES + CERTIFICATIONS:
            if contains_term(t, term) and not self._supported(term, evidence, allow_offer=False):
                if term in ("certification", "certifie", "certifiee", "diplome", "diplomee", "diplomé") and allow_offer \
                        and contains_term(self.offer_norm, term):
                    continue
                v.ok = False
                v.reasons.append(f"Diplôme/certification sans preuve : « {term} »")

        for acro in DEGREE_ACRONYMS:
            if re.search(rf"(?<![A-Za-z0-9]){acro}(?![A-Za-z0-9])", text) and not self._supported(acro, evidence, allow_offer=False):
                v.ok = False
                v.reasons.append(f"Diplôme sans preuve : « {acro} »")

        # 7. Outils
        for term in TOOLS:
            if contains_term(t, term) and not self._supported(term, evidence, allow_offer=line.kind == "headline"):
                if allow_offer and line.kind != "projection" and contains_term(self.offer_norm, term):
                    continue
                v.ok = False
                v.reasons.append(f"Outil/compétence technique sans preuve : « {term} »")

        # 8. Langues et niveaux
        words = t.split(" ")
        for i, w in enumerate(words):
            lang = LANGUAGES.get(w.strip(",.;:()"))
            if not lang:
                continue
            lang_facts = [f for f in evidence.facts if f.kind in ("language", "certification")]
            if not self._supported(w.strip(",.;:()"), evidence, allow_offer=allow_offer and line.kind != "projection"):
                v.ok = False
                v.reasons.append(f"Langue sans preuve : « {w} »")
                continue
            window = " ".join(words[max(0, i - 3): i + 5])
            claimed = max((lvl for word, lvl in LEVEL_WORDS.items() if contains_term(window, word)), default=0)
            if claimed:
                fact_level = 0
                for f in lang_facts:
                    fl = norm(str(f.data.get("level", ""))) if f.kind == "language" else ""
                    fact_level = max(fact_level, LEVEL_WORDS.get(fl, 0))
                    if f.kind == "certification" and "toeic" in norm(f.text):
                        fact_level = max(fact_level, 5)
                if fact_level and claimed > fact_level:
                    v.ok, v.exaggeration = False, True
                    v.reasons.append(f"Niveau de langue gonflé : {window.strip()}")

        # 9. Noms propres / sigles
        for cand in proper_noun_candidates(text):
            if self._supported(cand, evidence, allow_offer=allow_offer):
                continue
            # un groupe de plusieurs mots est accepté si chacun de ses mots est justifié
            parts = [p for p in re.split(r"[\s/&]+", cand) if p and norm(p) not in STOP_CAPITALIZED]
            if parts and all(self._supported(p, evidence, allow_offer=allow_offer) for p in parts):
                continue
            v.ok = False
            v.reasons.append(f"Nom propre ou sigle sans preuve : « {cand} »")

        # 10. Niveau de responsabilité
        if needs_facts and evidence.facts:
            line_level = _level_of(t)
            fact_level = max((_level_of(norm(f.text)) for f in evidence.facts), default=0)
            contribution_only = fact_level == 1
            if line_level == 3 and fact_level < 3:
                v.ok, v.exaggeration = False, True
                v.reasons.append("Responsabilité gonflée (management/direction) sans fait qui le prouve")
            elif contribution_only and line_level >= 2:
                v.ok, v.exaggeration = False, True
                v.reasons.append("« Participé » ne devient pas « piloté/géré »")

        # 11. Hygiène
        if line.section == "experience" and len(text) > 130:
            v.warnings.append(f"Puce longue ({len(text)} caractères)")
        if line.kind == "headline" and extract_numbers(text):
            v.ok = False
            v.reasons.append("Chiffre dans le titre")
        return v

    # -- documents -----------------------------------------------------------
    def validate_lines(self, lines: list[Line]) -> ValidationReport:
        report = ValidationReport()
        for line in lines:
            if line.kind == "structure":
                continue
            verdict = self.validate_line(line)
            report.verdicts.append(verdict)
            report.total += 1
            if verdict.ok:
                report.traced += 1
            else:
                report.rejected_ids.append(line.id)
            if verdict.forbidden:
                report.forbidden_hits += 1
            report.warnings.extend(f"{line.id}: {w}" for w in verdict.warnings)
        report.factuality = round(100.0 * report.traced / report.total, 1) if report.total else 0.0
        return report


def validate_cv(cv: CvDocument, profile: MasterProfile, offer_text: str, offer_terms: list[str] | None = None) -> ValidationReport:
    return ClaimValidator(profile, offer_text, offer_terms=offer_terms).validate_lines(cv.lines)


def validate_letter(letter: LetterDocument, profile: MasterProfile, offer_text: str, offer_terms: list[str] | None = None) -> ValidationReport:
    return ClaimValidator(profile, offer_text, offer_terms=offer_terms).validate_lines(letter.lines)


def drop_rejected(lines: list[Line], report: ValidationReport) -> tuple[list[Line], list[dict[str, object]]]:
    """Supprime les lignes rejetées ; renvoie les lignes gardées et le journal des suppressions."""
    reasons = {v.line_id: v.reasons for v in report.verdicts if not v.ok}
    kept = [ln for ln in lines if ln.id not in reasons]
    removed: list[dict[str, object]] = [{"id": ln.id, "text": ln.text, "reasons": reasons[ln.id]} for ln in lines if ln.id in reasons]
    return kept, removed
