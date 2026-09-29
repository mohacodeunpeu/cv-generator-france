"""Test de fumée d'une installation PAI (à lancer après chaque déploiement ou mise à jour).

    PAI_URL=http://127.0.0.1:8080 PAI_API_KEY=pai_… python deploy/smoke_test.py

Vérifie : santé, en-têtes de sécurité, page de connexion, API protégée, analyse d'une offre FICTIVE,
génération asynchrone d'un pack (worker + Chromium), téléchargement du PDF par lien signé.
N'envoie rien à personne ; n'utilise qu'une offre fictive. Sortie : une ligne par contrôle, code 0 si tout passe.
"""

from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlparse

import httpx

OFFER = ("Business Developer Junior (H/F) — CDI — Paris\nEntreprise FICTIVE de test (smoke test PAI).\n\n"
         "Vos missions\n- Prospecter de nouveaux clients PME par téléphone et LinkedIn.\n- Suivre votre pipeline dans un CRM.\n\n"
         "Votre profil\n- Anglais courant.\n- Première expérience en prospection B2B.")


def main() -> int:
    base = os.environ.get("PAI_URL", "http://127.0.0.1:8080").rstrip("/")
    key = os.environ.get("PAI_API_KEY", "")
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        print(f"{'OK  ' if cond else 'ÉCHEC'} {name}{(' — ' + detail) if detail else ''}")

    with httpx.Client(base_url=base, timeout=60, follow_redirects=False) as c:
        r = c.get("/health")
        check("santé", r.status_code == 200 and r.json().get("status") == "ok", r.text[:80])
        h = r.headers
        check("en-têtes de sécurité", h.get("x-frame-options") == "DENY" and "noindex" in h.get("x-robots-tag", "")
              and "frame-ancestors 'none'" in h.get("content-security-policy", ""))
        check("interface protégée", c.get("/").status_code == 303 and c.get("/v1/profile").status_code == 401)
        check("page de connexion", c.get("/login").status_code == 200)
        if not key:
            print("(PAI_API_KEY absent : contrôles de l'API ignorés — python -m pai api-key create smoke --scopes read,analyze,generate)")
            return 0 if ok else 1
        auth = {"Authorization": f"Bearer {key}"}
        r = c.post("/v1/analyze-job", json={"offer_text": OFFER}, headers=auth)
        check("analyse d'offre", r.status_code == 200, f"secteur {r.json().get('analysis', {}).get('sector_id')}" if r.status_code == 200 else r.text[:120])
        r = c.post("/v1/generate-application-pack", json={"offer_text": OFFER}, headers=auth | {"Idempotency-Key": f"smoke-{int(time.time())}"})
        check("pack mis en file", r.status_code == 202, r.text[:120])
        if r.status_code != 202:
            return 1
        job_id, job = r.json()["job_id"], {}
        for _ in range(120):
            job = c.get(f"/v1/jobs/{job_id}", headers=auth).json()
            if job.get("status") in ("DONE", "FAILED"):
                break
            time.sleep(1)
        check("pack généré par le worker", job.get("status") == "DONE", job.get("error") or job.get("status", ""))
        if job.get("status") != "DONE":
            return 1
        result = job["result"]
        check("factualité 100 %", result["quality_scores"].get("factuality_cv") == 100 and result["quality_scores"].get("factuality_letter") == 100)
        pdf = c.get(urlparse(result["application_pack"]["cv_pdf"]).path)
        check("PDF du CV (lien signé)", pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), f"{len(pdf.content)} octets")
        print(f"Statut du pack : {result['status']} · génération {result['generation_id']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
