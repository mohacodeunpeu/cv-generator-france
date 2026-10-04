"""Moteur ATS de PAI : déterministe, explicable, sans IA obligatoire.

Correspondance avec les briques attendues :
  parser                 pai/ats/parser.py          lecture d'un CV (sections, coordonnées, expériences, dates)
  job_analyzer           pai/analyzer.py            analyse d'offre déterministe (+ IA en option)
  keyword_extractor      pai/analyzer.py            mots-clés et priorités de l'offre
  synonym_matcher        pai/rules.py (Synonyms)    équivalences et implications déclarées (rules/skill_synonyms.yaml)
  semantic_matcher       pai/ats/semantic.py        taxonomie métier FR, formes proches, embeddings locaux optionnels
  requirement_classifier pai/ats/requirements.py    MUST / IMPORTANT / NICE_TO_HAVE / CONTEXT
  gap_analyzer           pai/ats/requirements.py    PROUVÉ / PLAUSIBLE / NON_PROUVÉ (+ compétences voisines)
  factuality             pai/claims.py              validateur ligne → fait (aucune invention)
  ats_validator          pai/ats/scanner.py         scanner PDF (OK / WARNING / ERROR) + relecture
  scoring                pai/ats/scoring.py         Score PAI et dimensions en pourcentages
  report                 pai/ats/report.py          rapports « CV + offre » et « CV seul »
  (+) variants, corpus, changes                     variantes de CV, corpus métier, AVANT / APRÈS / RAISON / PREUVE
"""

from .report import ENGINE_VERSION, cv_report, match_report
from .requirements import classify_requirement, proof_status_for_texts, prove

__all__ = ["ENGINE_VERSION", "classify_requirement", "cv_report", "match_report", "proof_status_for_texts", "prove"]


def studio_payload() -> dict:
    """Données du moteur ATS injectées dans PAI Studio (web/studio/ats.js) : listes de mots, motifs, taxonomie,
    pondérations, variantes. Une seule source de vérité (ce paquet) : le port JavaScript ne recopie aucune liste."""
    from ..analyzer import _MUST, _NICE
    from ..claims import LANGUAGES, LEVEL_WORDS
    from . import lexicon, scoring, semantic, variants
    from . import requirements as rq

    return {
        "lexicon": {"stopwords": sorted(lexicon.STOPWORDS), "filler": sorted(lexicon.FILLER), "suffixes": list(lexicon._SUFFIXES)},
        "classify": {"not_verbs": sorted(rq._NOT_VERBS), "ir_re_verbs": sorted(rq._IR_RE_VERBS),
                     "context_words": sorted(rq._CONTEXT_WORDS), "soft": sorted(rq.SOFT)},
        "patterns": {"must": _MUST.pattern, "nice": _NICE.pattern, "context_strong": rq._CONTEXT_STRONG.pattern,
                     "context": rq._CONTEXT.pattern, "action_noun": rq._ACTION_NOUN.pattern, "degree": rq.DEGREE_RE.pattern,
                     "years": rq.YEARS_RE.pattern, "lead_strip": rq.LEAD_STRIP.pattern},
        "taxonomy": [{"id": f.id, "label": f.label, "category": list(f.category), "members": list(f.members)}
                     for f in semantic.families()],
        "scoring": scoring.config(),
        "variants": variants.variants(),
        "labels": rq.LABELS,
        "languages": [[w, c] for w, c in LANGUAGES.items()],
        "level_words": [[w, v] for w, v in LEVEL_WORDS.items()],
    }
