"""Sauvegarde vérifiée : deploy/backup.sh → modification → deploy/restore.sh → comparaison, sur un vrai PostgreSQL.

Les vrais scripts, en mode local, avec le vrai chiffrement age : la base (schéma Alembic, profil, utilisateur, jobs)
et le dossier de données doivent revenir EXACTEMENT à l'état sauvegardé (empreinte de chaque table, de chaque fichier),
et une sauvegarde ne contient aucune donnée lisible en clair. Base dédiée, créée puis supprimée par le test.
Nécessite PAI_TEST_PG_URL (rôle autorisé à créer une base), age, age-keygen, pg_dump et pg_restore ; sinon ignoré.
Profil fictif « Camille Test » uniquement.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("PAI_TEST_PG_URL", "")
TOOLS = ("age", "age-keygen", "pg_dump", "pg_restore", "bash")
MISSING = [t for t in TOOLS if not shutil.which(t)] + ([] if PG_URL else ["PAI_TEST_PG_URL"])
if MISSING and os.environ.get("PAI_REQUIRE_BACKUP_TEST") == "1":     # CI : jamais ignoré en silence
    raise RuntimeError(f"Test de restauration impossible, manque : {', '.join(MISSING)}")
pytestmark = pytest.mark.skipif(bool(MISSING), reason=f"manque : {', '.join(MISSING)}")


def _table_prints(url: str) -> dict[str, str]:
    """Empreinte de chaque table : nombre de lignes + hachage du contenu (indépendant de l'ordre physique)."""
    engine = create_engine(url)
    try:
        out = {}
        with engine.connect() as c:
            for table in sorted(inspect(engine).get_table_names()):
                rows = c.execute(text(f'SELECT * FROM "{table}"')).fetchall()
                digest = hashlib.sha256("\n".join(sorted(repr(tuple(r)) for r in rows)).encode()).hexdigest()
                out[table] = f"{len(rows)}:{digest[:16]}"
        return out
    finally:
        engine.dispose()


def _file_prints(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture()
def backup_db(monkeypatch):
    """Base PostgreSQL dédiée au test, au schéma des migrations Alembic, remplie par l'application elle-même."""
    admin_url = make_url(PG_URL)
    url = admin_url.set(database="pai_backup_check").render_as_string(hide_password=False)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS pai_backup_check WITH (FORCE)"))
        c.execute(text("CREATE DATABASE pai_backup_check"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True, capture_output=True,
                   env=os.environ | {"DB_URL": url})
    from pai.api import auth
    from pai.config import reset_settings_cache
    from pai.db.repo import save_profile_doc, snapshot_profile
    from pai.db.session import reset_engines, session_scope
    from pai.profile import load_profile

    monkeypatch.setenv("DB_URL", url)
    monkeypatch.setenv("SECRET_KEY", "b" * 48)
    reset_settings_cache()
    reset_engines()
    profile = load_profile(ROOT / "tests" / "fixtures" / "profile_test.json")
    with session_scope() as s:
        save_profile_doc(s, profile)
        snapshot_profile(s, profile)                       # profil versionné : candidat, version, faits
    auth.create_user("camille", "mot-de-passe-de-test-sauvegarde")
    reset_engines()
    yield url
    reset_engines()
    reset_settings_cache()
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS pai_backup_check WITH (FORCE)"))
    admin.dispose()


def test_backup_modify_restore_compare(backup_db, tmp_path):
    from pai.api import auth
    from pai.db.session import reset_engines

    data = tmp_path / "data"
    (data / "cache" / "results").mkdir(parents=True)
    (data / "master_profile.json").write_text((ROOT / "tests" / "fixtures" / "profile_test.json").read_text(encoding="utf-8"),
                                              encoding="utf-8")
    (data / "cache" / "results" / "r1.json").write_text('{"score": 84}', encoding="utf-8")
    key = tmp_path / "cle.txt"
    subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    recipient = next(ln.split(": ", 1)[1] for ln in key.read_text().splitlines() if ln.startswith("# public key: "))
    env = os.environ | {"PAI_ENV_FILE": str(tmp_path / "absent.env"), "PAI_BACKUP_MODE": "local", "DB_URL": backup_db,
                        "PAI_DATA_DIR": str(data), "PAI_BACKUP_DIR": str(tmp_path / "backups"),
                        "PAI_BACKUP_AGE_RECIPIENT": recipient, "PAI_BACKUP_AGE_IDENTITY": str(key)}

    before_db, before_files = _table_prints(backup_db), _file_prints(data)
    assert before_db["users"].startswith("1:") and before_db["store_documents"].startswith("1:"), before_db
    assert int(before_db["facts"].split(":")[0]) > 10, before_db
    out = subprocess.run(["bash", "deploy/backup.sh"], cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    assert "sauvegarde OK" in out.stdout, out.stderr
    db_file = next((tmp_path / "backups").glob("pai_db_*.dump.age"))
    data_file = next((tmp_path / "backups").glob("pai_data_*.tar.age"))
    for f in (db_file, data_file):                       # chiffré : ni le nom du profil ni le JSON en clair
        raw = f.read_bytes()
        assert raw.startswith(b"age-encryption.org/v1") and b"Camille" not in raw and b"score" not in raw

    # Modification après la sauvegarde : un utilisateur de plus, un profil modifié, des fichiers changés.
    auth.create_user("intrus", "un-autre-mot-de-passe")
    reset_engines()
    engine = create_engine(backup_db)
    with engine.begin() as c:
        c.execute(text("UPDATE store_documents SET version = version + 1"))
        c.execute(text("DELETE FROM facts WHERE id IN (SELECT id FROM facts ORDER BY id LIMIT 3)"))
    engine.dispose()
    (data / "cache" / "results" / "r1.json").write_text('{"score": 12}', encoding="utf-8")
    (data / "master_profile.json").unlink()
    (data / "nouveau.json").write_text("{}", encoding="utf-8")
    assert _table_prints(backup_db) != before_db and _file_prints(data) != before_files

    out = subprocess.run(["bash", "deploy/restore.sh", str(db_file), str(data_file), "--yes"], cwd=ROOT, env=env,
                         check=True, capture_output=True, text=True)
    assert "Restauration terminée" in out.stdout, out.stderr
    assert _table_prints(backup_db) == before_db          # base : exactement l'état sauvegardé
    assert _file_prints(data) == before_files             # fichiers : idem (le fichier ajouté a disparu)
