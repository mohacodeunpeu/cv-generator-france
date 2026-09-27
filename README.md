# PAI — Personal Application Intelligence

PAI est un produit autonome de préparation de candidatures, pensé pour générer un CV, une lettre, une analyse d'offre et un Application Pack à partir d'un profil candidat et d'une offre réelle.

Il est conçu pour être séparé du JobAgent, sans dépendance directe à son code, ses ports, ses secrets ni sa base de données.

## Mission

- comprendre l'offre, l'entreprise, le poste et le contexte recruteur
- analyser le profil candidat et ses faits vérifiables
- positionner le candidat sur le bon angle de candidature
- produire un CV PDF, une lettre et un pack d'application
- garder un niveau de vérité strict, sans invention
- préparer le chemin vers le benchmark, les feedbacks et l'apprentissage

## Périmètre actuel (Lot A)

Le dépôt contient désormais le cœur du Lot A :

- Master profile versionné
- Analyse d'offre
- Matching / stratégie de positionnement
- Génération de CV PDF
- Génération de lettre PDF
- Pack ZIP exportable
- API versionnée de base
- Dashboard de test local
- Documentation d'architecture et de reprise

## Séparation stricte JobAgent / PAI

PAI ne doit pas dépendre du JobAgent.

Les règles de séparation sont les suivantes :

- projet Docker séparé
- réseau séparé
- ports séparés
- base PostgreSQL séparée
- volumes séparés
- secrets séparés
- logs séparés
- aucun accès en écriture au JobAgent
- aucun redémarrage ou modification de ses services

Le dépôt contient des fichiers de documentation pour préserver cette séparation :

- ARCHITECTURE.md
- DECISIONS.md
- PROGRESS.md
- RUNBOOK.md

## Stack

- Python 3.12
- FastAPI
- Pydantic / Pydantic Settings
- Jinja2
- ReportLab
- Anthropic API (optionnel selon le fournisseur actif)
- SQLite local pour le bootstrapping

## Structure du projet

```text
.
├── app.py
├── ARCHITECTURE.md
├── DECISIONS.md
├── PROGRESS.md
├── RUNBOOK.md
├── .env.example
├── .gitignore
├── requirements.txt
├── templates/
│   └── pai_dashboard.html
├── pai/
│   ├── __init__.py
│   ├── __init__.py
│   ├── analyzer.py
│   ├── config.py
│   ├── models.py
│   ├── pdf_renderer.py
│   ├── profile.py
│   └── strategy.py
├── amine_profile.py
├── cv_gen_france.py
├── cover_letter_france.py
├── modes.py
└── README.md
```

## Démarrage rapide

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2. Configurer les variables d'environnement

Copier le fichier exemple :

```bash
cp .env.example .env
```

Editer le fichier `.env` :

```env
ANTHROPIC_API_KEY=changeme
APP_NAME=PAI
ENVIRONMENT=development
DB_URL=sqlite:///./pai.db
```

### 3. Lancer le serveur

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Vérifier

```bash
curl http://localhost:8000/health
```

## Routes principales

### Health

```http
GET /health
```

### Profil

```http
GET /api/v1/profile
```

### Analyse d'offre

```http
POST /api/v1/analyze-job
```

Payload attendu :

```json
{
  "job_title": "Business Developer",
  "company": "Entreprise test",
  "offer_text": "Nous recherchons un profil commercial orienté prospection, relation client et portefeuille.",
  "offer_url": "https://example.com/job"
}
```

### Stratégie

```http
POST /api/v1/generate-strategy
```

### CV PDF

```http
POST /api/v1/generate-cv
```

### Pack ZIP

```http
POST /api/v1/generate-pack
```

### Compatibilité legacy

Le produit garde aussi les routes historiques suivantes pour sécuriser la transition :

- `POST /generate`
- `POST /cv`
- `POST /lettre`
- `POST /best`
- `POST /chat`

## Dashboard

Le dashboard local est disponible via :

```text
http://localhost:8000/
```

Il permet :

- d'analyser une offre
- de générer un pack PDF / ZIP
- de tester le cœur du moteur sans passer par un autre service

## Objectifs du Lot A

Le Lot A couvre :

- profil candidat
- compréhension de l'offre
- matching / positionnement
- génération de CV et de lettre
- export pack
- architecture documentaire claire
- préparation au benchmark et à l'apprentissage

## Points de vigilance

- la vérité des faits est prioritaire
- l'invention est interdite
- les données personnelles doivent rester hors Git et hors logs
- l'IA doit utiliser ses propres clés et son environnement
- le JobAgent reste intact et non modifié

## Prochaines étapes

### Lot B

- feedback utilisateur
- scoring
- benchmark sur offres réelles
- Blind Arena
- comparaison avec JobAgent de manière honnête

### Lot C

- interface premium et responsive
- meilleur UX pour analyse, versioning et feedback
- apprentissage par règles validées
- déploiement réel sur serveur 24/7 avec URL stable

## Contribution / reprise

Pour reprendre la session plus tard, le point de départ est :

- PROGRESS.md
- DECISIONS.md
- RUNBOOK.md

Cela permet de reprendre le projet sans perdre la progression ni refaire des étapes déjà validées.

## Sécurité

- les secrets sont dans `.env` et hors Git
- pas de mot de passe ni de token dans les logs
- les données sensibles doivent rester dans les fichiers locaux / secrets du serveur
- l'application ne doit pas exposer de données sensibles dans les URLs

## Résumé

PAI est une base autonome de préparation de candidatures, pensée pour être plus sérieux, plus traçable, plus robuste et plus séparé du JobAgent que le projet initial.

C'est une base de produit, pas une simple maquette.

---

Version du projet : 0.1.0 (Lot A)
