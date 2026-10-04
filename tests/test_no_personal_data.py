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


# ── Secrets et adresses de serveur (jamais dans un dépôt public) ────────────────────────────────────
SECRETS = {
    "clé privée": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "clé Anthropic": re.compile(r"sk-ant-(?!test-)[A-Za-z0-9_-]{20,}"),
    "clé OpenAI": re.compile(r"\bsk-(?:proj-)?(?!test)[A-Za-z0-9]{32,}"),
    "jeton GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}|\bgithub_pat_[A-Za-z0-9_]{40,}"),
    "jeton Slack": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "clé Google": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "clé AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "webhook Discord": re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]{20,}"),
    "jeton Cloudflare Tunnel": re.compile(r"\beyJhIjoi[A-Za-z0-9+/=_-]{60,}"),
    "clé d'API PAI": re.compile(r"\bpai_(?=[\w-]*\d)(?=[\w-]*[A-Z])[\w-]{32,}"),
    "adresse de serveur (sslip.io / nip.io)": re.compile(r"\b\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3}\.(?:sslip|nip)\.io\b"),
}
IPV4 = re.compile(r"(?<![\w.%])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.])")
# Adresses sans danger : boucle locale, réseaux privés, lien local, plages de documentation (RFC 5737), et les adresses
# publiques bien connues des tests anti-SSRF (résolveurs publics, ancienne adresse d'example.com).
SAFE_IP_TESTS = {"8.8.8.8", "1.1.1.1", "93.184.216.34"}


def _ip_is_safe(parts: tuple[str, ...], rel: str) -> bool:
    import ipaddress

    try:
        ip = ipaddress.ip_address(".".join(parts))
    except ValueError:
        return True                                    # pas une adresse (numéro de version, etc.)
    doc = any(ip in ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))
    return not ip.is_global or ip.is_multicast or doc or (rel.startswith("tests/") and str(ip) in SAFE_IP_TESTS)


def test_no_secrets_or_server_addresses_tracked():
    """Clés, jetons, webhooks, jeton de tunnel, clé d'API PAI, adresse publique du serveur : rien de tout cela dans Git.
    Les vraies valeurs vivent dans .env (ignoré), en base (chiffrées) ou dans les secrets du serveur."""
    offenders = []
    for rel in tracked_files():
        if IMAGE.search(rel) or rel.endswith((".ttf", ".otf", ".woff", ".woff2", ".pdf")):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        offenders += [f"{rel}: {label}" for label, pattern in SECRETS.items() if pattern.search(text)]
        offenders += [f"{rel}: adresse IP publique" for m in IPV4.finditer(text) if not _ip_is_safe(m.groups(), rel)]
    assert not offenders, "Secret ou adresse de serveur dans le dépôt public : " + ", ".join(sorted(set(offenders)))
