# Sécurité du dépôt Git — constat et procédure

## Constat (audit du 27 septembre 2026, toutes branches, tout l'historique)

Le dépôt `mohacodeunpeu/cv-generator-france` est **public** : n'importe qui peut le cloner avec tout son historique.

| Élément | Exposé ? | Où |
|---|---|---|
| Clé d'API (Anthropic, OpenAI, Google, GitHub…), clé privée, jeton | **Non** : aucune trouvée | recherche de motifs sur tout l'historique |
| Mot de passe réel | **Non** : seulement des valeurs d'exemple ou de test (`CHANGE_ME`, tests) | `.env.example`, tests |
| E-mail personnel | **Oui** | `amine_profile.py` puis `legacy/amine_profile.py`, depuis le 1er mai 2026 (12 versions) |
| Téléphone | **Oui** | mêmes fichiers ; anciennes versions de `cv_gen_france.py` |
| Profil LinkedIn | **Oui** | mêmes fichiers |
| Parcours (employeurs, dates, diplômes, chiffres) | **Oui** | mêmes fichiers ; `profiles/confirmations.yaml` (sans coordonnées) |
| Fichier compilé `__pycache__/cv_gen_france.cpython-312.pyc` | **Oui** (contient les mêmes chaînes) | un ancien commit |
| Photo, adresse postale, date de naissance | Non | — |

Depuis cette PR, aucune donnée personnelle nouvelle n'entre dans le dépôt. Le test
`tests/test_no_personal_data.py` fait échouer la CI si un e-mail, un téléphone, un profil LinkedIn,
une photo, un fichier de `data/` ou une sauvegarde est ajouté hors de `legacy/`.

## 1. Passer le dépôt en privé (2 minutes, réversible) — recommandé tout de suite

GitHub → dépôt → **Settings** → **General** → tout en bas, *Danger Zone* → **Change repository visibility**
→ **Make private** → confirmer le nom du dépôt.

Conséquences :
- le serveur PAI n'est pas concerné : il tourne à partir de sa copie locale ;
- la CI continue (GitHub Free : 2 000 minutes par mois pour les dépôts privés ; un passage prend environ 3 minutes) ;
- le lien de la PR et les liens GitHub ne sont plus visibles sans connexion.

Limite : rendre privé n'efface rien de ce qui a déjà été copié (clones, forks, archives, moteurs de recherche).

## 2. Option : purger l'historique (irréversible, à faire en connaissance de cause)

À faire **après** avoir passé le dépôt en privé, depuis un ordinateur avec Git et `git-filter-repo`
(`pip install git-filter-repo`) :

```bash
git clone --mirror https://github.com/mohacodeunpeu/cv-generator-france.git pai-purge.git
cd pai-purge.git
# 1) Retirer les fichiers qui contenaient les coordonnées (ils seront recréés sans coordonnées)
git filter-repo --invert-paths --path amine_profile.py --path __pycache__/cv_gen_france.cpython-312.pyc
# 2) Remplacer les coordonnées restantes dans tout l'historique
cat > ../remplacements.txt <<'EOF'
VOTRE_EMAIL==>contact@example.org
VOTRE_TELEPHONE_TEL_QU_ECRIT==>+33 6 00 00 00 00
VOTRE_URL_LINKEDIN==>linkedin.example/profil
EOF
git filter-repo --replace-text ../remplacements.txt
git push --force --mirror origin
```

Conséquences :
- tous les commits changent d'identifiant : la PR #2 doit être recréée à partir de la nouvelle branche ;
- toute copie locale doit être reclonée ;
- GitHub peut garder des vues en cache (anciennes PR) : demander un nettoyage au support GitHub
  (*Remove cached views*) ;
- `legacy/amine_profile.py` doit ensuite être remplacé par une version sans coordonnées (le benchmark
  « ancien vs nouveau » lit le profil réel depuis `data/`, hors Git).

## 3. Règles pour la suite

- Les données personnelles vivent uniquement dans `data/` (ignoré par Git), dans la base PostgreSQL du serveur
  (sauvegardes chiffrées avec age) ou dans la base privée de PAI Studio.
- La photo n'est jamais commitée : elle est envoyée depuis l'interface, puis stockée dans la base privée.
- Les secrets vivent dans `.env` (ignoré) ou chiffrés dans la base (clés d'API saisies dans l'écran « Fournisseur IA »).
- Captures d'écran et tests : uniquement le profil fictif « Camille Test ».
