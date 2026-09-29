"""Garde-fou (A10) : aucune donnée personnelle ni photo ne doit entrer dans le dépôt, qui est public.

Seul `legacy/` (ancien générateur, déjà exposé dans l'historique, conservé pour le benchmark) est toléré.
Les données réelles vivent dans `data/` (ignoré par Git), dans la base du serveur ou dans la base privée de PAI Studio.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}")
ALLOWED_EMAIL = re.compile(r"@([a-z0-9-]+\.)*example\.(org|com|fr|net)$|^noreply@anthropic\.com$")  # domaines réservés (RFC 2606) et sous-domaines
PHONE = re.compile(r"(?<![\d.])(\+33 ?|0)[67]([ .]?[0-9]{2}){4}(?![\d])")
FICTIONAL_PHONE = re.compile(r"(\+33 ?|0)6([ .]?00){4}")
LINKEDIN = re.compile(r"linkedin\.com/in/[A-Za-z0-9-]+", re.I)
IMAGE = re.compile(r"\.(png|jpe?g|webp|heic|heif|gif|bmp|tiff?)$", re.I)
IMAGE_DIRS = ("docs/proofs/",)  # captures d'écran avec le profil FICTIF « Camille Test » uniquement


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("dépôt Git indisponible")
    return [f for f in out.decode("utf-8").split("\0") if f]


def test_no_personal_contact_data_outside_legacy():
    offenders = []
    for rel in tracked_files():
        if rel.startswith("legacy/") or IMAGE.search(rel) or rel.endswith((".ttf", ".otf", ".woff", ".woff2", ".pdf")):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in EMAIL.finditer(text):
            if not ALLOWED_EMAIL.search(m.group(0)):
                offenders.append(f"{rel}: e-mail")
        for m in PHONE.finditer(text):
            if not FICTIONAL_PHONE.fullmatch(m.group(0)):
                offenders.append(f"{rel}: téléphone")
        if LINKEDIN.search(text):
            offenders.append(f"{rel}: profil LinkedIn")
    assert not offenders, "Données personnelles dans le dépôt public : " + ", ".join(sorted(set(offenders)))


def test_no_photos_or_private_files_tracked():
    tracked = tracked_files()
    photos = [f for f in tracked if IMAGE.search(f) and not f.startswith(IMAGE_DIRS)]
    assert not photos, f"Images hors docs/proofs/ (photos interdites dans le dépôt) : {photos}"
    private = [f for f in tracked if f.startswith(("data/", "backups/")) or f == ".env" or f.endswith((".age", ".dump"))]
    assert not private, f"Fichiers privés suivis par Git : {private}"
