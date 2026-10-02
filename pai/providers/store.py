"""Réglages IA enregistrés côté serveur (table `app_settings`, clé « ai »), clés d'API chiffrées au repos.

Chiffrement : Fernet (AES-128-CBC + HMAC-SHA256), clé dérivée de SECRET_KEY par HKDF-SHA256 (libellé fixe).
Une clé n'est jamais journalisée ni renvoyée : l'API n'expose qu'un indice (••••a1b2).
Changer SECRET_KEY rend les clés enregistrées illisibles : elles sont ignorées (à ressaisir), sans erreur.

Valeur JSON stockée : {"active": "gemini", "providers": {"gemini": {"key": "<jeton Fernet>", "model": "…"},
"openai": {"model": "…", "base_url": "https://…/v1"}}}.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("pai.providers")
AI_SETTINGS_KEY = "ai"
HKDF_INFO = b"pai/app_settings/api-keys/fernet/v1"


def _fernet() -> Any:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    from ..api.security import secret_key

    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_INFO).derive(secret_key().encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Lève cryptography.fernet.InvalidToken si le jeton vient d'une autre SECRET_KEY ou a été altéré."""
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


def key_hint(raw: str) -> str:
    """Indice affichable : 4 derniers caractères seulement, et rien pour une clé courte."""
    if not raw:
        return ""
    return f"••••{raw[-4:]}" if len(raw) >= 12 else "••••"


@dataclass
class StoredProvider:
    api_key: str = field(default="", repr=False)   # déchiffrée, en mémoire seulement
    model: str = ""
    base_url: str = ""
    model_small: str = ""                           # local : petit modèle


@dataclass
class StoredAiSettings:
    active: str = ""
    providers: dict[str, StoredProvider] = field(default_factory=dict)
    profile: str = ""                               # eco | balanced | quality

    def get(self, pid: str) -> StoredProvider:
        return self.providers.get(pid) or StoredProvider()


def decode_settings(value: Any) -> StoredAiSettings:
    """Valeur JSON de la base → réglages en mémoire (clés déchiffrées ; clé illisible = ignorée)."""
    from cryptography.fernet import InvalidToken

    value = value if isinstance(value, dict) else {}
    out = StoredAiSettings(active=str(value.get("active") or ""), profile=str(value.get("profile") or ""))
    entries = value.get("providers") if isinstance(value.get("providers"), dict) else {}
    for pid, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        key = ""
        if entry.get("key"):
            try:
                key = decrypt_secret(str(entry["key"]))
            except (InvalidToken, ValueError, TypeError):
                log.warning("Clé d'API enregistrée pour « %s » illisible (SECRET_KEY changée ?) : ignorée, à ressaisir.", pid)
        out.providers[str(pid)] = StoredProvider(api_key=key, model=str(entry.get("model") or ""),
                                                 base_url=str(entry.get("base_url") or ""),
                                                 model_small=str(entry.get("model_small") or ""))
    return out


def load_settings_value(session: Any, lock: bool = False) -> dict[str, Any]:
    """Copie profonde de la valeur enregistrée (modifiable sans toucher à l'objet suivi par la session).
    `lock` : verrou de ligne (PostgreSQL) pour une lecture-modification-écriture."""
    from ..db.models import AppSetting

    row = session.get(AppSetting, AI_SETTINGS_KEY, with_for_update=True if lock else None)
    return json.loads(json.dumps(row.value)) if row is not None and isinstance(row.value, dict) else {}


def save_settings_value(session: Any, value: dict[str, Any]) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    from ..db.models import AppSetting, utcnow

    row = session.get(AppSetting, AI_SETTINGS_KEY)
    if row is None:
        session.add(AppSetting(key=AI_SETTINGS_KEY, value=value))
        return
    row.value, row.updated_at = value, utcnow()
    flag_modified(row, "value")


def _sqlite_file_missing(db_url: str) -> bool:
    """Fichier SQLite absent : rien à lire, et une simple lecture ne doit pas créer de base vide."""
    from sqlalchemy.engine import make_url

    url = make_url(db_url)
    return url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:") and not Path(url.database).exists()


def read_stored_settings() -> StoredAiSettings:
    """Réglages enregistrés ; base indisponible ou table absente → réglages vides (repli silencieux sur l'environnement)."""
    try:
        from ..config import get_settings
        from ..db.session import session_scope

        if _sqlite_file_missing(get_settings().db_url):
            return StoredAiSettings()
        with session_scope() as s:
            return decode_settings(load_settings_value(s))
    except Exception as exc:  # noqa: BLE001 — la génération ne doit jamais dépendre de cette lecture
        log.debug("Réglages IA en base indisponibles (%s) : environnement seul.", exc.__class__.__name__)
        return StoredAiSettings()
