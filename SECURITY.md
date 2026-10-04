# Sécurité de PAI

Ce dépôt est public. Ce document dit ce qui protège les données et les secrets, et comment c'est vérifié.

## Secrets et données personnelles

- Secrets uniquement dans `.env` (ignoré par Git et par l'image Docker) ou en base, **chiffrés** (clés d'API saisies
  dans l'interface : Fernet dérivé de `SECRET_KEY`, jamais réaffichées). Jamais dans le code, les journaux, les URL.
- Profil, CV, lettres, packs, sauvegardes : `data/` et `backups/` (ignorés par Git) ou la base PostgreSQL du serveur.
- Garde-fous exécutés à chaque CI (`tests/test_no_personal_data.py`, sur les fichiers suivis) :
  e-mails et téléphones réels, profils LinkedIn, photos, fichiers privés (`.env`, sauvegardes), **clés et jetons**
  (Anthropic, OpenAI, GitHub, Slack, Google, AWS, webhooks Discord, jeton de tunnel Cloudflare, clés d'API PAI,
  clés privées), **adresses de serveur** (IPv4 publiques, noms `sslip.io` / `nip.io` contenant une IP).
- Exception connue : `legacy/` (ancien générateur) et l'historique Git contiennent des coordonnées personnelles
  anciennes. Recommandation : passer le dépôt en privé ; une purge d'historique (`git filter-repo`) réécrit
  l'historique et n'est jamais faite sans décision explicite.

## Application

- Un utilisateur, mot de passe argon2 (12 caractères minimum), changement imposé au premier login ; changer de
  mot de passe ou se déconnecter **révoque toutes les sessions**.
- Sessions signées (cookie HttpOnly, Secure, SameSite=strict), durée limitée ; CSRF sur toute écriture ;
  limitation des tentatives de connexion par IP et identifiant (derrière Cloudflare Tunnel : IP lue dans
  `CF-Connecting-IP`, posé par Cloudflare, jamais dans `X-Forwarded-For`).
- Clés d'API hachées, à droits limités (`read`, `analyze`, `generate`, `outcomes`…), affichées une seule fois.
- En-têtes : CSP à nonce, `frame-ancestors 'none'`, `nosniff`, `no-referrer`, `noindex`, HSTS en production.
- Fichiers : liens signés de courte durée, sans donnée personnelle dans l'URL ; jetons masqués dans les journaux.
- Journaux structurés : `request_id`, route, statut, durée, étape, fournisseur, modèle, cache — **jamais** le
  contenu d'un CV, d'une lettre, d'une offre, ni un secret.

## Lecture d'URL (anti-SSRF)

`pai/netfetch.py` : http/https et ports 80/443 seulement, aucune adresse privée ou réservée (y compris écrite en
décimal, octal, hexadécimal ou IPv6 mappée), redirections revalidées à chaque saut, corps borné (décompression
comprise), adresse connectée revérifiée. Proxys d'environnement ignorés ; proxy sortant seulement sur demande
explicite (`PAI_FETCH_PROXY`). Échecs nommés précisément (anti-bot, connexion requise, page en JavaScript…).

## IA

Par défaut, aucune donnée ne quitte le serveur : IA locale (Ollama) ou aucune IA. Un fournisseur externe est
optionnel et se configure explicitement. Toute sortie d'IA repasse par le validateur de faits déterministe.

## Infrastructure

- Docker : base sur un réseau interne sans Internet, interface liée à `127.0.0.1`, conteneurs sans privilèges
  (`cap_drop: ALL`, `no-new-privileges`), limites CPU/mémoire, images épinglées.
- Accès public par Cloudflare Tunnel nommé : aucun port entrant ouvert, adresse IP du serveur non exposée.
- Sauvegardes chiffrées avec `age` (clé privée hors du serveur), restauration vérifiée en CI.
- CI : `pip-audit` (dépendances), lint, typage, garde-fous ci-dessus, tests sur PostgreSQL, image Docker testée.

## Signaler un problème

Ouvrir une issue **sans** joindre de donnée personnelle ni de secret, ou contacter le propriétaire du dépôt.
