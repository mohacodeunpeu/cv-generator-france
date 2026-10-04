# Moteur ATS de PAI

Déterministe, explicable, sans IA obligatoire. Code : `pai/ats/` (Python) et `web/studio/engine.js` (même logique,
côté navigateur, parité vérifiée par `tests/golden/ats_parity.json`).

> Le **Score PAI** est un indicateur interne. Ce n'est **ni le score d'un ATS réel** (Workday, Taleo…) **ni une
> probabilité d'embauche**. Chaque pourcentage est calculé par des règles lisibles, affichées dans « Voir les détails ».

## 1. Ce que voit l'utilisateur

```
SCORE PAI  86 %
Format & parsing 94 %  ·  Structure 91 %  ·  Matching offre 82 %  ·  Mots-clés 86 %  ·  Expérience 88 %  ·  Factualité 100 %
(Formation, Langues, Conditions : dans les détails)                                                        Voir les détails →
```

L'écran principal ne montre que des **pourcentages**. Les critères (une vingtaine) sont le moteur interne ; ils
apparaissent seulement dans le détail de chaque dimension.

| Dimension | Poids (mode B) | Calcul |
|---|---|---|
| Matching offre | 28 % | exigences couvertes : obligatoires ×3, importantes ×2, « un plus » ×1 ; prouvé = 1, correspondance possible = 0,5 |
| Mots-clés | 14 % | mots-clés de l'offre présents dans le CV (avant CV : prouvés par le profil) |
| Expérience | 14 % | 40 % intitulés proches, 35 % durée, 25 % séniorité |
| Format & parsing | 12 % | scanner PDF : 100 − 25 par ERREUR − 8 par AVERTISSEMENT |
| Factualité | 10 % | lignes du CV prouvées par un fait (validateur `pai/claims.py`) |
| Structure | 7 % | sections, expériences datées, puces utiles, coordonnées |
| Formation | 5 % | niveau demandé vs niveau prouvé |
| Langues | 5 % | langues et niveaux, pondérés par classe d'exigence |
| Conditions | 5 % | 50 % lieu (mobilité déclarée), 30 % contrat, 20 % disponibilité |

Pondérations : `rules/ats_scoring.yaml` (modifiable sans code). Une dimension non mesurable (pas encore de PDF) est
exclue ; les poids restants sont renormalisés et le score est marqué **provisoire** (la formule l'indique).

## 2. Deux modes d'analyse

**Mode A — CV seul** (`cv_report`, `POST /api/cv/analyze` sans offre) : Format & parsing (30 %), Structure (25 %),
Contenu (20 %), Lisibilité (15 %), Factualité = cohérence interne (10 % : dates possibles, pas de superlatifs
invérifiables). Points forts, problèmes, recommandations. **Aucune liste de mots-clés inventée** : un TOP n'apparaît
que si le corpus métier contient assez d'offres de la famille détectée (voir §6), avec son volume.

**Mode B — CV + offre** (`match_report`, `POST /api/cv/analyze` avec offre, pipeline complet) : les huit dimensions
ci-dessus, les exigences classées et prouvées, les mots-clés expliqués, la variante de CV retenue.

## 3. Exigences : classement et preuve

Classement (`classify_requirement`) :

| Classe | Libellé | Repères |
|---|---|---|
| MUST | Obligatoire | indispensable, requis, exigé, impératif, maîtrise… |
| IMPORTANT | Important | mission (verbe d'action en tête) ou compétence sans marqueur |
| NICE_TO_HAVE | Un plus | apprécié, idéalement, est un plus, atout… (hors parenthèse : « CRM (HubSpot idéalement) » reste obligatoire) |
| CONTEXT | Contexte | télétravail, salaire, taille de l'entreprise… — jamais compté comme exigence |

Preuve (`prove`) — du plus fort au plus faible :

| Statut | Libellé | Quand | Type |
|---|---|---|---|
| PROUVÉ | Prouvé | un fait le dit : mot exact, forme proche (« prospecter » ↔ « prospection »), synonyme déclaré | EXACT / SYNONYME |
| PLAUSIBLE | Correspondance possible | déduction déclarée (HubSpot → CRM), famille métier, niveau de langue inférieur, mots en partie présents, proximité de sens (embeddings locaux, option) | SÉMANTIQUE |
| NON_PROUVÉ | Non prouvé | aucun fait ; une compétence voisine prouvée est seulement signalée | — |

Exemples (profil fictif) : HubSpot → PROUVÉ · prospection → PROUVÉ · Salesforce → NON PROUVÉ (voisin prouvé :
HubSpot, à valoriser en entretien, jamais à écrire) · immobilier → NON PROUVÉ · « un CRM » → PLAUSIBLE.

**Sémantique ≠ preuve.** La taxonomie (`rules/taxonomy_fr.yaml`), les racines (`pai/ats/lexicon.py`), la
similarité floue et les embeddings locaux (`PAI_SEMANTIC_EMBEDDINGS=1`, modèle EmbeddingGemma via Ollama) ne
produisent jamais mieux que PLAUSIBLE.

Chaque mot-clé porte son **pourquoi** : « Présent : prouvé par exp.alpha.t3 », « Pas ajouté : aucun fait ne le
prouve. L'écrire gonflerait le score au prix de la vérité. », etc. PAI n'ajoute jamais un terme pour monter un score.

## 4. Scanner PDF et relecture

`pai/ats/scanner.py` : texte extractible, encodage (`(cid:)`, `�`), caractères à risque (pictogrammes de police,
ligatures, emoji), pagination, débordement, colonnes, tableaux, images, texte pivoté, polices (Type3, taille),
en-tête et pied de page (coordonnées placées seulement dans ces bandes : certains ATS les ignorent), densité
(mots par page), coordonnées, sections reconnues, expériences datées, formation → **OK / WARNING / ERROR** avec
explication.

Deux lectures du PDF, comme deux familles d'ATS : dans l'ordre du flux du fichier (PDFBox/Tika, pdf.js) et ligne à
ligne par position (pdftotext -layout). Les sections sont jugées sur la meilleure des deux ; l'écart (colonnes mêlées
par une lecture ligne à ligne, flux désordonné) est expliqué dans le contrôle « Colonnes ».

Relecture (`roundtrip`) : CV → PDF → texte extrait → comparaison avec les lignes du CV source :
**rien de perdu** (chaque ligne retrouvée) et **rien d'ajouté** (aucun reste de gabarit : `undefined`, `null`,
`{{…}}`). Dans le pipeline, une ERREUR déclenche une passe de correction bornée (modèle ATS une colonne), puis une
nouvelle relecture.

## 5. CV maître, variantes, changements expliqués

Le **CV maître** (Master Profile) est la seule source de vérité. Les variantes (`rules/cv_variants.yaml`) :
MASTER, COMMERCIAL, BUSINESS_DEVELOPER, RECRUTEMENT, DIGITAL, CHARGE_AFFAIRES — choisies automatiquement (intitulé,
puis secteur) ; une variante choisit un angle, jamais un fait.

`pai/ats/changes.py` : pour chaque ligne du CV ciblé, **AVANT / APRÈS / RAISON / PREUVE** ; les lignes non reprises
sont listées avec leur raison (elles restent dans le CV maître).

## 6. Corpus métier

`pai/ats/corpus.py` agrège les offres analysées (table `analyses` + packs du Studio), par famille : intitulés,
compétences, outils, missions, qualités, fréquences (synonymes regroupés). **TOP 20** publié à partir de 10 offres,
**TOP 40** à partir de 25 (`rules/ats_scoring.yaml`). Le volume est toujours affiché ; les offres SYNTHETIC sont
exclues. API : `GET /api/corpus`.

## 7. Correspondance avec les briques attendues

| Brique | Fichier |
|---|---|
| parser | `pai/ats/parser.py` |
| job_analyzer, keyword_extractor | `pai/analyzer.py` |
| synonym_matcher | `pai/rules.py` (`Synonyms`) + `rules/skill_synonyms.yaml` |
| semantic_matcher | `pai/ats/semantic.py` + `rules/taxonomy_fr.yaml` |
| requirement_classifier, gap_analyzer | `pai/ats/requirements.py` |
| factuality | `pai/claims.py` |
| ats_validator | `pai/ats/scanner.py` |
| scoring | `pai/ats/scoring.py` + `rules/ats_scoring.yaml` |
| report | `pai/ats/report.py` |

## 8. Tests

`tests/test_ats.py` (classement, preuve, sémantique jamais preuve, rapports A et B, mot-clé non prouvé jamais ajouté,
lecture de CV, scanner et relecture sur un vrai PDF, variantes, corpus, changements) ; parité JS :
`tests/js/engine.test.js` sur `tests/golden/ats_parity.json`.
