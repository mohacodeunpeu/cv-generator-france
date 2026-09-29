# Décisions (choix · alternative écartée · raison)

## 2026-09-27 — Session V Ultime

1. **Réparer le commit « PAI Lot A foundation » plutôt que le compléter.**
   Les fichiers y étaient décalés d'un cran (le code de l'app dans `pai/__init__.py`, du Python dans
   `ARCHITECTURE.md`, le `.env` dans `templates/pai_dashboard.html`…) et `import pai` échouait (import circulaire).
   Écarté : corriger fichier par fichier. Raison : le contenu décalé était un squelette ; le moteur a été reconstruit.

2. **Deux surfaces : PAI Studio (claude.ai) + serveur PAI auto-hébergeable.**
   Écarté : attendre un serveur 24/7 pour livrer une URL. Raison : aucun accès SSH, aucune clé API, aucun domaine
   dans l'environnement de build ; la plateforme claude.ai permet une page privée qui appelle Claude
   (capacité `sample`), stocke des données (`db`) et offre des téléchargements (`downloads`).
   L'URL est stable, en HTTPS, derrière la connexion claude.ai, et privée par défaut.

3. **Pas de Next.js en V1 pour l'interface.** Écarté : Next.js/TypeScript/shadcn (stack imposée).
   Raison : blocage réel — la seule URL publiable ici est une page unique servie par claude.ai ; un serveur
   Next.js ne peut pas y tourner. PAI Studio est une page HTML/JS autonome ; le serveur Python sert sa propre
   interface. À reconsidérer au Lot C si le serveur 24/7 est disponible.

4. **Pas de `temperature` avec Claude Opus 5.5 et Sonnet 5.** Écarté : température basse (directive C).
   Raison : ces modèles renvoient une erreur 400 si `temperature` est fourni et la réflexion ne se désactive pas
   sur Opus 5.5. Stabilité obtenue par `output_config.effort` (medium/high), sorties JSON validées (Pydantic),
   2 nouvelles tentatives, cache par hash et validateur déterministe. Haiku 4.5 garde `temperature=0.2`.

5. **Sorties JSON par consigne + validation, pas de schéma strict côté API.** Écarté : `output_config.format`
   json_schema. Raison : le même mécanisme doit marcher pour Claude, OpenAI, Ollama et PAI Studio ; les sorties
   sont de toute façon revalidées par le validateur claim → evidence.

6. **Faits typés plutôt que tables par type.** Écarté : tables `experience`, `skill`, `education`… séparées.
   Raison : un seul mécanisme de preuve (`fact_ids`) et de statut ; le type est un champ (`kind`).

7. **Profil : confirmations utilisateur > legacy > JobAgent.** Le MBA présent dans `legacy/amine_profile.py`
   est FORBIDDEN (l'utilisateur a confirmé « PAS DE MBA ») ; le « Bachelor Bac+3 Développement Commercial — PSB »
   legacy est UNVERIFIED en file REVIEW (conflit possible avec « Bachelor REM » confirmé) ; les chiffres importés
   sont IMPORTED mais « à confirmer ». Écarté : importer le legacy tel quel.

8. **Données personnelles hors Git.** Le Master Profile vit dans `data/` (ignoré) et dans la base privée de
   PAI Studio ; `profiles/confirmations.yaml` ne contient aucune coordonnée. Risque signalé : le dépôt est
   public et `legacy/amine_profile.py` (historique Git) contient déjà e-mail et téléphone.

9. **Offres du benchmark SYNTHETIC.** Écarté : copier des annonces réelles depuis des extraits de recherche.
   Raison : la politique réseau bloque les sites d'emploi (Business France, Greenhouse, Jobibou) ; la règle A8
   interdit de présenter du synthétique comme réel. 13 offres fictives, marquées SYNTHETIC, dont 3 pièges.

10. **Rendu PDF serveur : HTML/CSS → Chromium (Playwright), polices Fira Sans (OFL) embarquées en data URI.**
    PAI Studio : pdfmake (texte vectoriel extractible) car l'impression navigateur est bloquée dans le cadre
    claude.ai. Écarté : html2canvas (PDF image, illisible par les ATS).

11. **Mise en page une colonne par défaut (`hybrid_modern`).** Écarté : deux colonnes. Raison : l'extraction
    ATS (pdfplumber) lit par lignes et entrelace les colonnes ; le deux colonnes est réservé au mode HUMAN_FIRST.

12. **Push uniquement sur la branche de travail `claude/elegant-dirac-vhi4np` + PR brouillon.**
    La directive dit « aucun push sans demande explicite » ; l'environnement cloud est éphémère et impose de
    pousser la branche pour ne rien perdre. Rien n'est poussé sur `master` : la fusion reste ta décision.

## 2026-09-27 — Serveur, benchmark, déploiement

13. **Le serveur sert la même interface PAI Studio, branchée sur son API.** Écarté : une seconde interface
    (Jinja ou Next.js). Raison : une seule interface à maintenir et à tester ; `server_shim.js` implémente
    `window.claude.use()` sur `/v1/store` et `/v1/ai/complete`. Le test e2e « serveur » le prouve dans Chromium,
    sous CSP stricte.

14. **Sessions signées + révocation serveur, sans table de sessions.** Écarté : sessions en base ou JWT.
    Raison : un seul utilisateur ; `users.sessions_valid_after` suffit à révoquer toutes les sessions à la
    déconnexion et au changement de mot de passe (testé : un ancien cookie rejoué reçoit 401).

15. **File de jobs dans PostgreSQL (`SELECT … FOR UPDATE SKIP LOCKED`).** Écarté : Redis + Celery/RQ.
    Raison : un service de moins sur un petit serveur ; idempotence (`Idempotency-Key` unique), reprise des jobs
    interrompus, 3 workers en parallèle testés sans double traitement. SQLite : un seul worker (documenté).

16. **Plafond de coût journalier calculé depuis le journal des appels IA en base.** Écarté : compteur en mémoire.
    Raison : un compteur en mémoire se remet à zéro à chaque requête ou redémarrage ; ici, plafond atteint →
    voies déterministes, jamais d'erreur bloquante.

17. **Benchmark : un seul instrument pour l'ancien et le nouveau, appliqué au texte extrait du PDF.**
    Écarté : comparer le score interne de PAI (qui connaît ses propres liens aux faits). Raison : équité ; la mise
    en page (dates, formule d'appel, bloc destinataire, citations de l'offre, notations « KEUR », « LT », codes de
    langue) est neutralisée des deux côtés. Chaque ligne rejetée a été relue : les 5 faux positifs trouvés côté
    ancien générateur ont été corrigés avant de publier les chiffres.

18. **Sélection gloutonne des faits dans le CV.** Écarté : tri par score de couverture isolé. Raison : deux puces
    prouvant le même mot-clé gaspillaient la place ; choisir d'abord le fait qui prouve un mot-clé encore absent
    fait passer la couverture honnête de 95,3 % à 97,4 % sans rien inventer. Même algorithme en Python et JS,
    parité vérifiée sur 13 offres (`tests/golden/cv_parity.json`).

19. **Image Docker = image officielle Playwright Python.** Écarté : `python:slim` + installation de Chromium.
    Raison : Chromium et ses dépendances système garantis, versions alignées sur `playwright==1.56.0`, image
    multi-architecture (Oracle Ampere A1 = arm64). Coût : ~3,6 Go de disque, acceptable sur le Free Tier.

20. **Sauvegardes chiffrées avec age, clé privée hors du serveur.** Écarté : GPG symétrique (phrase secrète sur
    le serveur). Raison : un serveur compromis ne peut pas relire ses propres sauvegardes. Cycle sauvegarde →
    modification → restauration vérifié sur la pile Docker réelle.

21. **Routes historiques (`/cv`, `/lettre`, `/generate`, `/best`) conservées mais authentifiées et produites par
    le nouveau pipeline.** Écarté : les supprimer. Raison : compatibilité des anciens appels, sans jamais
    réintroduire le MBA ni une ligne non prouvée.

22. **Intégration continue GitHub Actions.** Tests Python (SQLite + PostgreSQL 16), migrations, parité JS,
    e2e navigateur, `pip-audit`, `docker compose config`, uniquement avec des données fictives.
