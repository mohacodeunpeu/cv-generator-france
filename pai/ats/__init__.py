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
from .requirements import classify_requirement, prove, proof_status_for_texts

__all__ = ["ENGINE_VERSION", "classify_requirement", "cv_report", "match_report", "proof_status_for_texts", "prove"]
