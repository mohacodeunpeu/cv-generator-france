# IA dans PAI : autonome d'abord, externe en option

**PAI est autonome.** Toute la chaîne (lecture de l'offre, exigences, preuves, Score PAI, CV, lettre, relecture du
PDF) fonctionne **sans aucune IA**, par des voies déterministes 100 % factuelles. Une IA **locale et gratuite**
(Ollama) améliore la rédaction ; un fournisseur **externe** (Claude, Gemini, Mistral, OpenAI…) reste une option,
jamais une dépendance.

> AUTONOME : 100 % des fonctions sans IA · OPTIONNEL EXTERNE : disponible (clé du fournisseur requise).

## 1. Choisir le fournisseur

| `AI_PROVIDER` | Effet | Coût |
|---|---|---|
| `local` (défaut) | Ollama s'il répond et a un modèle ; sinon **sans IA**, sans erreur | 0 € |
| `none` | jamais d'IA : voies déterministes uniquement | 0 € |
| `anthropic`, `gemini`, `mistral`, `openai_compatible` | fournisseur externe, avec sa clé (`AI_API_KEY`) | payant |

Variables (alias documentés ; les anciens noms `PAI_AI_PROVIDER`, `ANTHROPIC_API_KEY`, `LOCAL_MODEL`… restent lus) :
`AI_PROVIDER`, `AI_MODEL` (grand modèle), `AI_MODEL_SMALL` (petit modèle local), `AI_BASE_URL`, `AI_API_KEY`,
`AI_PROFILE` (`eco` | `balanced` | `quality`), `OLLAMA_BASE_URL`.
Priorité : **Réglages → IA** dans l'interface (clés chiffrées en base) → variables d'environnement →
`default_provider` de `config/models.yaml` (`local`) → sans IA. Le badge de l'interface affiche le mode réel :
**IA LOCALE**, **IA EXTERNE** ou **SANS IA**.

## 2. Le routeur : quelle intelligence pour quelle tâche

`config/models.yaml` (`router`) et `pai/ai/router.py`. Trois niveaux : **aucun** (voie déterministe), **petit**
modèle local, **grand** modèle local (ou le fournisseur externe s'il est actif).

- **Jamais d'IA** pour ce qui se calcule : parsing, coordonnées, dates, sections, mots-clés exacts, classement des
  exigences, preuves, **factualité**, contrôle du PDF, Score PAI. Ces tâches ne figurent même pas dans le routeur.
- Profil `balanced` (défaut) : petit modèle pour l'extraction et les réponses courtes, grand modèle pour la
  stratégie, les corrections et la lettre ; le CV reste déterministe (100 % factuel par construction).
- Profil `eco` : le moins d'appels possible (la lettre seulement). Profil `quality` : l'IA partout où elle aide,
  la factualité restant déterministe.
- Chaque réponse est mise en **cache** (empreinte fournisseur + modèle + tâche + prompt + réglages) ; le journal
  `llm_calls` note niveau, jetons, durée, `cache_hit` / `cache_miss`, `request_id` — jamais le contenu.
- Toute sortie d'IA repasse par le validateur de faits : une phrase sans preuve est retirée, jamais publiée.

## 3. Choix du modèle local : mesuré, pas supposé

`python -m pai ai setup --pull` détecte la machine (cœurs utilisables, RAM, GPU, disque — limites de conteneur
comprises), propose les modèles qui tiennent (`config/local_models.yaml`), les **mesure** sur l'auto-évaluation
(`benchmark/selfeval/cases.yaml`) et enregistre le choix. Un modèle n'est retenu que s'il :

1. ne **ment pas** : aucune exigence déclarée prouvée à tort, aucune affirmation inventée, aucune lettre qui ajoute
   un fait (porte de vérité `truthful()`) ;
2. rend du JSON valide (≥ 80 %) ;
3. est assez rapide pour son niveau (grand ≥ 3 jetons/s, petit ≥ 8 jetons/s, sur CPU).

Parmi ceux-là : la meilleure qualité, puis la vitesse.

### Mesure de référence

Machine : x86_64, 4 cœurs Xeon 2,1 GHz, 15,7 Go de RAM, **sans GPU** ; Ollama 0.34.4. Scores sur 100.

| Modèle (Q4_K_M) | Qualité | Jetons/s | Extraction | Classement | Correspondance | Factualité | Lettre | Verdict |
|---|---|---|---|---|---|---|---|---|
| **qwen3 4B instruct 2507** | **87,2** | 4,4 | 95,2 | 87,5 | 83,3 | 100 | 100 | **grand modèle retenu** |
| qwen2.5 3B | 78,2 | 5,5 | 85,7 | 50,0 | 66,7 | 100 | 100 | moins bon |
| **qwen3 1.7B** | 77,8 | **9,1** | 95,2 | 37,5 | 66,7 | 100 | 100 | **petit modèle retenu** |
| gemma3 4B | 58,8 | 4,2 | 95,2 | 62,5 | 8,3 | 100 | 100 | **écarté** : déclare prouvée une exigence non prouvée |
| gemma3 1B | 50,1 | 13,1 | 85,7 | 25,0 | 16,7 | 66,7 | 50 | **écarté** : invente « Salesforce » dans une lettre |

Embeddings (rapprochements sémantiques, jamais une preuve) : `embeddinggemma`.
Mémoire : ≈ 4 Go pour le grand modèle, ≈ 2,2 Go pour le petit.

**Pourquoi ce choix** : qwen3 4B instruct est le seul grand modèle à la fois véridique, le plus juste sur le
classement et la correspondance, et au-dessus du seuil de vitesse sur un simple CPU ; qwen3 1.7B est deux fois
plus rapide et aussi fiable sur l'extraction, ce qui suffit aux petites tâches. Les deux tournent sur le serveur
gratuit (Oracle Ampere A1, 4 cœurs / 24 Go).

### En conditions réelles : un pack complet dans Docker (3 cœurs CPU, 8 Go, sans GPU)

Mesuré avec la pile Compose (`pai_web`, `pai_worker`, `pai_db`, `pai_ollama` limité à 3 cœurs / 8 Go) :

| Réglage | Résultat |
|---|---|
| profil `balanced` (stratégie, lettre et corrections par le grand modèle) | **21 min, aucune sortie IA retenue** : stratégie hors délai (360 s), lettre coupée à 900 jetons (JSON incomplet, 3 essais) ; le pack reste correct grâce aux voies déterministes |
| profil `eco` conseillé par la mesure (lettre seule par le grand modèle), après corrections | **pack en 320 s** dont 307 s pour la lettre (851 jetons) ; lettre de l'IA retenue, factualité CV 100 %, lettre 100 %, Score PAI 85 % |

D'où trois corrections et une règle, testées (`tests/test_ai_router.py`) :

- une réponse rejetée (JSON invalide) n'est **jamais resservie par le cache** (l'essai suivant relisait la même réponse
  fausse) ; une réponse validée au 2ᵉ essai est mise en cache sous la demande d'origine ;
- une réponse **coupée** par la limite de jetons (`done_reason = length`) est un échec immédiat (pas de nouvel essai
  inutile) ; la lettre dispose de 1 600 jetons, la stratégie et les corrections de 1 200 ;
- le délai d'un appel tient compte de la **vitesse mesurée** du modèle (lecture du prompt + génération complète,
  marge 30 %, plafond 15 min) ;
- **profil conseillé** : `eco` quand le grand modèle génère moins de 8 jetons/s sur la machine (cas d'un CPU sans
  GPU), `balanced` sinon. Enregistré par `python -m pai ai setup`, appliqué à l'IA locale seulement, et toujours
  remplacé par un choix explicite (Réglages → IA ou `AI_PROFILE`).

**Ce que ces chiffres ne disent pas** : l'auto-évaluation compte une quarantaine de cas synthétiques ; c'est un
filtre de sécurité et un comparatif, pas une mesure de la qualité d'un CV réel. Sur la même grille, la voie
**sans IA** obtient 81 en extraction et 100 en classement et en correspondance — mais ses règles ont été écrites
avec ces cas : ce 100 est optimiste. Le classement réel se mesure sur le benchmark d'offres réelles
(`docs/benchmark.md`). Un modèle local de 4 milliards de paramètres rédige moins bien qu'un grand modèle externe :
PAI ne prétend pas le contraire ; il garantit seulement que ce qui est écrit est vrai.

## 4. Fournisseur externe (optionnel)

Réglages → IA dans l'interface (clé chiffrée en base, jamais réaffichée), ou `AI_PROVIDER` + `AI_API_KEY`.
Plafonds : `COST_CAP_EUR_PER_PACK`, `COST_CAP_EUR_PER_DAY` ; au-delà, chaque étape repasse en voie déterministe.
Avec `local_first: true`, les petites tâches restent sur le modèle local s'il existe (moins de coût, aucune donnée
envoyée pour elles). Les sorties externes passent par le même validateur de faits que les sorties locales.
