# Décisions de conception

## 2026-09-27
- Choix de base: FastAPI + Pydantic + reportlab
- Raison: plus simple que le projet initial, compatible avec le prompt V Ultime, facile à déployer et à faire évoluer.
- Le dépôt a été conservé séparé du JobAgent; aucune écriture dans son environnement n'a été faite.
- On a conservé la base de profil existante (amine_profile.py) comme source historique, en l'exploitant côté PAI sans la détruire.
- Les premières routes exposent un cœur de produit autonome, même si le benchmark et les validations fortes arrivent ensuite.
