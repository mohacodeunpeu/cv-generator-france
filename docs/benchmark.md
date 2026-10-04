# Benchmarks de PAI

Trois instruments, trois questions. Aucun ne mesure une chance d'embauche : ils mesurent la qualité du système
(vérité, lisibilité, pertinence, constance). Le Score PAI n'est ni le score d'un ATS réel ni une probabilité
d'embauche.

| Instrument | Question | Données | Commande |
|---|---|---|---|
| **Régression** | PAI fait-il mieux que l'ancien générateur, et ne recule-t-il jamais ? | 13 offres **fictives** (`benchmark/offers/`, versionnées) | `python -m pai benchmark` |
| **Offres réelles** | Que vaut PAI sur de vraies annonces, comparé au CV que vous enverriez sans lui ? | vos offres réelles, **hors Git** (`data/benchmark_real/`) | `python -m pai benchmark-real` |
| **Auto-évaluation IA** | Quel modèle local est fiable et assez rapide sur cette machine ? | ≈ 40 cas synthétiques (`benchmark/selfeval/cases.yaml`) | `python -m pai ai setup` |

## 1. Régression : 13 offres fictives, ancien générateur contre PAI

Même instrument pour les deux, appliqué au **texte extrait du PDF** (ce que lit un ATS) : factualité en texte libre
(un terme interdit met le document à 0), couverture des mots-clés obligatoires et importants (brute, et « honnête » :
seulement ceux que le profil prouve), lisibilité, pagination, qualité du PDF, factualité de la lettre.

Dernière exécution (moteur 1.0.0, 4 octobre 2026, PAI sans IA : c'est son plancher) :

| Mesure | PAI | Ancien générateur |
|---|---|---|
| Score global (pondéré, `rules/scoring.yaml`) | **92,9** | 54,6 |
| Factualité du CV | **100** (13/13) | 0 (terme interdit dans les 13) |
| Lignes non prouvées par CV | **0** | 9 |
| Factualité de la lettre | **100** | 13,6 |
| Couverture honnête des mots-clés (prouvés) | **97,4** | 91,0 |
| Couverture brute des mots-clés | 71,7 | 76,4 |
| Lisibilité ATS / pagination | 100 / 100 | 100 / 100 |
| Qualité du PDF | **100** | 70 |
| Titre aligné sur l'offre | **100 %** | 7,7 % |
| Secteur reconnu | 100 % | — |

Lecture honnête : l'ancien générateur couvre plus de mots-clés **bruts** parce qu'il en ajoute que le profil ne
prouve pas (0,6 par CV en moyenne) ; PAI refuse de le faire. Écarts de moins de 3 points : équivalents.

## 2. Offres réelles (hors Git)

Préparer le dossier `data/benchmark_real/` (jamais versionné : `data/` est dans `.gitignore`) :

```
data/benchmark_real/
├── liens.txt              une URL d'offre par ligne (lue par le serveur PAI lui-même)
├── offre_xyz.pdf          ou .txt, .md, .html, .docx : une offre par fichier
└── cv_original.pdf        facultatif : le CV tel qu'il partirait sans PAI (comparaison)
```

```bash
python -m pai benchmark-real                       # sans IA (voies déterministes)
python -m pai benchmark-real --ai configured       # avec l'IA configurée (locale par défaut)
docker compose exec pai_web python -m pai benchmark-real --dir /app/data/benchmark_real
```

Chaque offre est générée deux fois (constance). Rapport : `data/benchmark_real/results/<date>/report.md`
(+ `rows.json`, `summary.json`) — des nombres seulement, aucun contenu du CV.

| Mesure | Définition |
|---|---|
| Factualité CV / lettre | part des lignes publiées qui citent un fait du profil (validateur de faits) |
| Affirmations non prouvées publiées | lignes publiées sans preuve (doit rester 0) ; lignes retirées faute de preuve comptées à part |
| Couverture des mots-clés : brute | mots-clés de l'offre présents dans le CV ciblé |
| … prouvée | présents **et** prouvés par le profil |
| … sémantique | « correspondance possible » : affichée à part, jamais comptée comme preuve |
| Exigences obligatoires prouvées | part des exigences obligatoires de l'offre prouvées par le profil |
| Format & parsing | scanner du PDF réel (deux lectures d'ATS : flux du fichier, ligne à ligne) |
| Qualité du PDF | pages, débordements, polices (contrôle du PDF) |
| Constance | deux générations de la même offre → même CV et même lettre (empreintes) |
| Temps, appels IA, cache | durée moyenne d'un pack, appels réels, réponses servies par le cache |
| Score PAI original → ciblé | même grille appliquée au CV original et au CV ciblé, sur la même offre |

**État au 4 octobre 2026** : l'outil est en place et testé (`tests/test_realbench.py`, offres fictives, liens
refusés, CV original). **Aucun résultat sur offres réelles n'est publié ici** : l'environnement de développement
n'a pas accès aux sites d'emploi (sa politique réseau refuse hellowork.com et welcometothejungle.com) et aucune
offre réelle n'y est stockée. Sur le serveur PAI (accès Internet direct), la commande ci-dessus produit le rapport.

## 3. Auto-évaluation des modèles locaux

Sept tâches : extraction, classement des exigences, correspondance, reformulation, factualité, lettre, JSON
structuré ; plus la vitesse (jetons/s) et la mémoire. Un modèle qui invente ou déclare prouvée une exigence non
prouvée est écarté quel que soit son score. Résultats, choix et mesures en conditions réelles :
`docs/ai-providers.md`.
