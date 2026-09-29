# Design system PAI « Atelier »

Référence de l'interface PAI (PAI Studio sur claude.ai et serveur PAI : même code, `web/studio/`).
Source de vérité : `web/studio/styles.css` (jetons en tête de fichier). Les documents (CV, lettres) ont leurs
propres gabarits : `web/studio/designs.js` (voir « Documents » plus bas).

## Intention

PAI doit se lire comme un **atelier de candidature** (AI workspace, career intelligence), pas comme un tableau
de bord d'administration. Trois règles guident chaque écran :

1. **Un seul geste principal par écran**, au centre, très visible (Accueil : « Analyser » dans le champ ;
   Analyse : « Ouvrir dans CV Studio » ; Studio : le document lui-même).
2. **Les documents sont les héros** : un vrai A4 (rendu pdf.js du PDF final), posé sur un « bureau »
   (fond `.desk`), jamais une imitation HTML (la vue « Preuves » reste disponible pour la traçabilité).
3. **L'espace et la typographie structurent, pas les cadres** : les sections sont séparées par un filet
   (`.card` = section à filet supérieur, sans fond ni bordure) ; seules quelques surfaces portent un fond :
   le champ de commande, les cartes d'information de l'analyse, la barre d'outils du studio, la galerie de designs.

## Couleurs (jetons)

| Rôle | Sombre (défaut) | Clair | Jeton |
| --- | --- | --- | --- |
| Fond graphite profond | `#0A0C0F` | `#F4F2EC` (ivoire) | `--bg` |
| Surfaces | `#11161B` → `#1C242B` | `#FBFAF6` → `#ECE9E1` | `--raise`, `--raise-2`, `--raise-3` |
| Texte ivoire / graphite | `#EDE9DE` | `#15191D` | `--ink` (puis `--ink-2`, `--muted`, `--faint`) |
| Bleu pétrole (action) | `#1C6272` / `#2E8292` / `#79B7C3` | `#175868` / `#1C6272` | `--petrol`, `--petrol-2`, `--petrol-3` |
| Bleu profond (profondeur, aurore) | `#12264A` / `#1D3B69` | idem | `--deep`, `--deep-2` |
| Champagne (très léger) | `#D9C9A2` | `#8E7440` | `--champ` : le *I* de PAI, les surtitres, un filet actif |
| Filets | ivoire à 7 / 12 / 20 % | graphite à 8 / 13 / 22 % | `--hair`, `--hair-2`, `--hair-3` |
| États | vert, ambre, rouge doux | versions foncées | `--good`, `--warn`, `--bad` (+ `-soft`) |

Le champagne est rare (moins de 5 % de la surface) : il signale la marque et la hiérarchie, jamais une action.
Le bleu pétrole porte les actions. Thème : clair et sombre complets (`prefers-color-scheme`, et le choix
Réglages → Apparence pose `data-theme` sur la racine).

## Typographie

| Usage | Police | Taille |
| --- | --- | --- |
| Marque « PAI » | Instrument Serif | 92 → 176 px (`.wordmark`) |
| Titres de page | Instrument Serif | 34 → 52 px (`h1.title`) ; 24 → 30 px (`h2.h2`) |
| Chiffres clés | Instrument Serif | 30 → 44 px (scores, « En bref ») |
| Interface | Instrument Sans | 15 px (corps), 13–14 px (secondaire) |
| Surtitres | Instrument Sans 600, capitales, +0,16 em | 11,5 px (`.kicker`) — avec parcimonie |
| Données, versions | Geist Mono | 11–13 px |

Titres en `text-wrap: balance`, paragraphes limités à ~62 caractères. Les titres de section sont en
casse normale (`h3.h3`, 14 px, 600) : les capitales espacées sont réservées aux surtitres.

## Espace

Échelle 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 px (`--s1` … `--s9`). Espacement entre sections de page :
40 px (56 px sur l'accueil). Gouttière latérale ≥ 16 px à toutes les largeurs. Contenu limité à 1 360 px,
accueil centré sur 880 px.

## Composants

- **Rail** (`.rail`, 88 px) : monogramme PAI, 6 entrées principales (Accueil, Analyser, Studio, Packs, Lab,
  Learning), 4 secondaires plus discrètes (Bench, Profil, Versions, Réglages), avatar du profil (photo ou
  initiales, pastille verte = profil validé). Mobile (≤ 960 px) : barre d'onglets flottante + feuille « Plus ».
- **Barre du haut** : fil d'Ariane, « Données privées », badge **AI MODE** (`REMOTE` / `LOCAL` / `DEGRADED`
  + fournisseur), ligne de progression de l'analyse en haut de l'écran.
- **Champ de commande** (`.command`) : verre fumé, liseré dégradé pétrole → champagne, lien / texte / PDF
  (bouton ou glisser-déposer), profondeur (Rapide / Standard / Approfondi), bouton `.cta` à l'intérieur.
- **CTA** (`.cta`) : dégradé pétrole → bleu profond, liseré champagne, reflet au survol. Un seul par écran.
- **Pipeline** (`.pipeline`) : 9 étapes (Ingest, Understand, Company, Match, Strategy, CV, Letter, Pack, QA),
  nœud animé (halo + arc champagne) pendant l'étape, coche dessinée à la fin, durée par étape.
- **Bureau** (`.desk`) : fond à halo pétrole et trame de points, pour poser les documents.
- **Pile de documents** (`.doc-stack`) : CV devant, lettre derrière légèrement tournée.
- **Studio** (`.studio`) : 3 colonnes (stratégie · document · qualité) ; barre d'outils en verre
  (versions, design, couleurs, PDF réel / Preuves) ; galerie des **5 designs avec aperçus réels** du CV ;
  pilule « brouillon » flottante (« Enregistrer en V3 · Annuler »).
- **Scores** (`.score`) : chiffre en serif, barre fine, pourquoi, preuve dépliable.

## Mouvement

Durées 0,2 → 0,9 s, courbe `--ease-out` (cubic-bezier .16, 1, .3, 1). Uniquement `transform` et `opacity`
(performance). Entrée de page (fondu + 8 px), aurore lente derrière l'accueil (22 s), étapes du pipeline
(halo, arc, coche), documents qui « se posent », galerie qui descend, survols (documents +6 px).
`prefers-reduced-motion: reduce` coupe toutes les animations et transitions.

## Documents (CV et lettres)

`web/studio/designs.js` : 5 familles réellement différentes (mise en page, polices, palette, place de la photo),
chacune avec sa lettre assortie (même palette, mêmes polices, même en-tête) :

| Famille | Idée | Lecture ATS |
| --- | --- | --- |
| Premium Corporate | bandeau sombre plein cadre, nom en serif, filets champagne | élevée |
| Modern Commercial | barre d'accent, chiffres clés en tête, compétences en étiquettes | moyenne |
| Minimal Executive | serif, colonne de titres, beaucoup d'air | élevée |
| Digital Creative | colonne latérale sombre, photo ronde, niveaux de langue | faible |
| ATS Hybrid | une colonne, filets fins, lecture ATS maximale | élevée |

Un gabarit ne fait QUE la mise en page : le texte vient des lignes validées (claim → evidence) ; les tests
vérifient que chaque ligne est présente dans les 5 PDF, sur 1 page, avec polices embarquées et ordre de lecture
nom → expérience → formation (`tests/e2e/test_designs.py`, `tests/js/designs.test.js`).
