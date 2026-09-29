# Audit visuel et refonte de l'interface (septembre 2026)

Méthode : la version en production et la refonte ont été ouvertes dans un vrai navigateur (Chromium, Playwright),
avec le même build et le même profil **fictif** « Camille Test », aux largeurs 375, 390, 430, 768, 1280, 1440
et 1920 px, en thème sombre et clair. L'URL publique (serveur Oracle) n'est pas joignable depuis l'environnement
de travail (proxy : 403) : l'audit porte sur le même code que celui servi par le serveur.

Captures : `docs/proofs/redesign/` (avant / après, 5 designs de CV, 5 lettres, mobile, thème clair).

## 1. Audit de la version en production (avant)

Jugée comme un utilisateur qui découvre le produit :

1. **Accueil = tableau de bord d'administration** : 4 compteurs à zéro (« 0 Application Packs », « — Factualité »,
   « 0 Retours », « 0 Votes ») qui ne disent rien à un nouvel utilisateur.
2. **Pas d'action principale visible** ; le bouton « Nouvelle candidature » s'affichait comme une **icône géante
   cassée** dans un bloc cyan (et débordait de l'écran sur mobile).
3. **Soupe de cartes** : 8 blocs encadrés identiques sur l'accueil, 11 sur le CV Studio ; aucune hiérarchie.
4. **Menu à 10 entrées + intertitres techniques** (« MESURER », « DONNÉES », « Learn from JobAgent »).
5. **Typographie sans échelle** : titres en serif système gras, capitales grises partout.
6. **CV Studio** : aperçu du CV en imitation HTML (pas le vrai PDF), 7 tuiles de scores à barres, réglages
   empilés dans un long formulaire (« ATS / Hybride / Humain »), pastilles de couleur sans rapport avec le design.
7. **Aucune identité** (logo texte, couleurs génériques), aucun mouvement, barre du haut en « console d'état ».
8. **Mobile** : barre d'onglets opaque, blocs empilés sans respiration, débordement horizontal.

## 2. Première refonte (intermédiaire) : ce qui restait « dashboard »

Rail de 10 libellés, chaque bloc encadré, CTA en bas à gauche du champ, CV Studio en 3 colonnes de cartes qui
écrasaient le document, surtitres en capitales partout, cyan trop « tech ».

## 3. Refonte « Atelier » (design system : `docs/DESIGN_SYSTEM.md`)

- **Identité** : monogramme PAI (serif, *I* champagne), palette graphite / ivoire / bleu pétrole / bleu profond /
  champagne très léger, aurore lente derrière l'accueil, trame de points sur les « bureaux ».
- **Accueil** : composition centrée (marque, « Personal Application Intelligence », promesse en serif sur 2 lignes),
  **champ « Analyser une offre » comme héros** avec le CTA à l'intérieur, lien / texte / PDF / glisser-déposer,
  « Next best action » sur une ligne, reprise des packs sous forme de couvertures de documents réelles.
- **Analyser** : espace de travail en 2 volets ; à gauche le titre du poste en grand et les 9 étapes animées ;
  à droite un bureau où apparaissent l'entreprise, la correspondance, le design choisi, puis le CV et la lettre.
- **CV Studio** : le document au centre (vrai PDF), barre d'outils en verre (versions, design, couleurs, PDF réel /
  Preuves), **galerie des 5 designs rendus réellement avec le CV de l'utilisateur**, brouillon flottant
  (« Enregistrer en V3 »), stratégie à gauche et qualité à droite en typographie (plus de cartes).
- **Letter Studio** : même atelier, galerie des 5 mises en page de la lettre, badge « Assortie au CV ».
- **Application Pack** : couverture (monogramme de l'entreprise, titre en serif, statut), documents posés sur le
  bureau, chiffres clés en grand (correspondance, mots-clés prouvés, risque, factualité).
- **Reste** (Packs, Lab, Learning, Benchmark, Profil, Versions, Réglages, Configuration) : même langage — titres
  en serif, sections à filets, listes à la place des grilles de cartes ; détails techniques repliés.
- **Mobile** : barre d'onglets flottante en verre, CTA pleine largeur, documents avant les panneaux.

## 4. Deuxième passage critique (sur captures) et corrections

| Défaut observé | Correction |
| --- | --- |
| Aperçu du CV **flou** quand une miniature du même design existait (cache commun 300 px) | cache des aperçus par largeur |
| Promesse de l'accueil coupée sur 4 lignes | largeur 30 ch → 2 lignes |
| Cartes d'information de l'analyse surchargées (texte sur 5 lignes) | contenu réduit : titre en serif, une ligne, une note |
| Durées des étapes renvoyées sur une 3ᵉ ligne ; « UNDERSTAND » collé au texte | grille nom / détail / durée, colonne de 122 px |
| Barre de progression décalée (position fixe dans un parent transformé) | élément fixe dédié, largeur animée |
| Options de design qui débordaient de la galerie | ligne dédiée pour la photo et « Pourquoi ce design ? » |
| Barre d'outils du studio sur 2 lignes | téléchargement déplacé dans l'en-tête ; une seule ligne |
| Débordement horizontal de 77 px à 768 px (halo de l'accueil) | halo découpé au niveau du contenu (`overflow-x: clip`) |
| Barre du haut coupée à 1 400 px sur écran 1920 | pleine largeur |
| Compteurs à zéro sur l'accueil d'un nouvel utilisateur | remplacés par une promesse tant qu'il n'y a pas de pack |
| Redondance dans la lettre (citations répétées dans « Pourquoi cette entreprise ») | seulement le paragraphe « entreprise » |

## 5. Vérifications automatiques

- `tests/e2e/test_studio_e2e.py` : parcours complet, galerie des 5 designs, brouillon → V2, comparaison,
  téléchargements PDF / ZIP, Training Lab (V3), conflit de profil, photo fictive + basse résolution, onboarding,
  réglages (test de connexion), et **aucun défilement horizontal de 375 à 1920 px**.
- `tests/e2e/test_designs.py` : les 5 CV et 5 lettres en PDF réels (1 page, polices embarquées, ordre ATS,
  même contenu).
- `tests/js/designs.test.js` : design automatique, fiche entreprise, photo jamais sur la lettre, 5 mises en page
  distinctes.
