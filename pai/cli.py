"""Ligne de commande : `python -m pai <commande>`."""

from __future__ import annotations

import argparse
import getpass
import json
import secrets
import sys
from pathlib import Path

from . import paths


def cmd_bootstrap_profile(args: argparse.Namespace) -> int:
    from .bootstrap import build_master_profile
    from .profile import save_profile

    profile = build_master_profile()
    target = save_profile(profile)
    print(f"Master Profile v{profile.version} : {len(profile.facts)} faits → {target}")
    for item in profile.review_queue:
        print(f"  REVIEW [{item.severity}] {item.fact_id} — {item.reason}")
    return 0


def cmd_validate_profile(args: argparse.Namespace) -> int:
    from .profile import load_profile, save_profile, validate_profile

    profile = validate_profile(load_profile())
    save_profile(profile)
    print(f"Profil v{profile.version} validé le {profile.validated_at}")
    return 0


def cmd_export_profile(args: argparse.Namespace) -> int:
    from .profile import export_csv, export_json, export_markdown, load_profile

    profile = load_profile()
    out = {"json": export_json, "csv": export_csv, "md": export_markdown}[args.format](profile)
    Path(args.output).write_text(out, encoding="utf-8") if args.output else sys.stdout.write(out)
    return 0


def cmd_import_profile(args: argparse.Namespace) -> int:
    from .profile import import_json, save_profile

    profile = import_json(Path(args.file).read_text(encoding="utf-8"))
    print(f"Profil importé ({len(profile.facts)} faits) → {save_profile(profile)}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    from .ingest import load_fixture, offer_from_pdf, offer_from_text, offer_from_url
    from .pack import export_zip
    from .pipeline import Pipeline
    from .profile import load_profile
    from .providers import get_provider
    from .render import PdfRenderer

    src = args.offer
    if src.startswith("http"):
        offer = offer_from_url(src)
    elif src.endswith((".yaml", ".yml")):
        offer = load_fixture(Path(src))[0]
    elif src.endswith(".pdf"):
        offer = offer_from_pdf(Path(src).read_bytes(), src)
    else:
        offer = offer_from_text(Path(src).read_text(encoding="utf-8"), title=args.title or "", company=args.company or "")
    provider = get_provider(args.provider, budget_eur=args.budget)
    pipe = Pipeline(load_profile(), provider, mode=args.mode, progress=lambda s, d: print(f"  · {s} — {d}"))
    pack = pipe.run(offer, questions=Path(args.questions).read_text(encoding="utf-8") if args.questions else "")
    out = Path(args.output or paths.ensure_data_dirs() / "packs" / f"{pack.id}.zip")
    out.write_bytes(export_zip(pack, pipe.files))
    PdfRenderer.shutdown()
    print(json.dumps({"pack": str(out), "status": pack.status, "provider": pack.provider, "scores": {
        k: v for k, v in pack.scores.items() if k != "points"}, "points": pack.scores.get("points", {}).get("total"),
        "cost_eur": pack.cost_eur}, ensure_ascii=False, indent=2))
    return 0


def cmd_secret(args: argparse.Namespace) -> int:
    print(secrets.token_urlsafe(48))
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    from .api.auth import create_user

    password = args.password or (getpass.getpass("Mot de passe (vide = généré) : ") if sys.stdin.isatty() else "")
    generated = not password
    password = password or secrets.token_urlsafe(18)
    create_user(args.username, password, must_change=generated)
    if generated and args.stdout:
        # Usage Docker (`docker compose run --rm pai_web python -m pai create-user … --stdout`) : affiché une seule fois
        # dans CE terminal, jamais écrit dans un journal ni un fichier ; changement imposé au premier login.
        print(f"Utilisateur « {args.username} » créé. Mot de passe provisoire (à changer au premier login) : {password}")
    elif generated:
        env = Path(args.env_file)
        lines = [ln for ln in env.read_text(encoding="utf-8").splitlines() if not ln.startswith("PAI_INITIAL_PASSWORD=")] if env.exists() else []
        lines.append(f"PAI_INITIAL_PASSWORD={password}")
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        env.chmod(0o600)
        print(f"Utilisateur « {args.username} » créé. Mot de passe généré : voir {env} (PAI_INITIAL_PASSWORD), à changer au premier login.")
    else:
        print(f"Utilisateur « {args.username} » créé.")
    return 0


def cmd_api_key(args: argparse.Namespace) -> int:
    """Clés d'API (JobAgent, scripts) : affichées UNE seule fois à la création, stockées hachées (SHA-256)."""
    from sqlalchemy import select

    from .api.auth import SCOPES, create_api_key
    from .db.models import ApiKey, AuditLog, utcnow
    from .db.session import init_db, session_scope

    init_db()
    if args.action == "create":
        scopes = [x.strip() for x in (args.scopes or "read").split(",") if x.strip()]
        raw = create_api_key(args.name, scopes)
        print(f"Clé « {args.name} » ({', '.join(sorted(scopes))}) — copiez-la maintenant, elle ne sera plus affichée :\n{raw}")
        return 0
    with session_scope() as s:
        keys = s.scalars(select(ApiKey).order_by(ApiKey.created_at)).all()
        if args.action == "list":
            for k in keys:
                state = "révoquée" if k.revoked_at else "active"
                print(f"{k.id:>4}  {k.name:<24} {k.prefix}…  {','.join(k.scopes):<40} {state}")
            if not keys:
                print(f"Aucune clé. Droits possibles : {', '.join(sorted(SCOPES))}")
            return 0
        target = next((k for k in keys if k.name == args.name and k.revoked_at is None), None)
        if target is None:
            print(f"Aucune clé active nommée « {args.name} ».")
            return 1
        target.revoked_at = utcnow()
        s.add(AuditLog(actor="cli", action="revoke_api_key", target=args.name))
        print(f"Clé « {args.name} » révoquée.")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import run_benchmark

    result = run_benchmark(include_legacy=not args.no_legacy, output_dir=Path(args.output) if args.output else None,
                           persist=args.persist)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


def cmd_build_studio(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(paths.WEB_DIR))
    from build_studio import build  # type: ignore[import-not-found]

    print(build(Path(args.output) if args.output else None, server=args.server))
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from .api.jobs import run_worker

    run_worker(once=args.once)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pai", description="PAI — Personal Application Intelligence")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap-profile", help="Construire le Master Profile v1 (confirmations + legacy)").set_defaults(fn=cmd_bootstrap_profile)
    sub.add_parser("validate-profile", help="Valider la version courante du profil").set_defaults(fn=cmd_validate_profile)
    p = sub.add_parser("export-profile", help="Exporter le profil")
    p.add_argument("--format", choices=["json", "csv", "md"], default="json")
    p.add_argument("--output")
    p.set_defaults(fn=cmd_export_profile)
    p = sub.add_parser("import-profile", help="Importer un profil JSON (export PAI Studio ou JobAgent converti)")
    p.add_argument("file")
    p.set_defaults(fn=cmd_import_profile)
    p = sub.add_parser("generate", help="Générer un Application Pack")
    p.add_argument("offer", help="fichier texte, .pdf, .yaml (fixture) ou URL publique")
    p.add_argument("--title")
    p.add_argument("--company")
    p.add_argument("--questions", help="fichier texte : une question par ligne")
    p.add_argument("--mode", choices=["QUICK", "STANDARD", "DEEP"], default="STANDARD")
    p.add_argument("--provider", choices=["claude", "openai", "local", "null"])
    p.add_argument("--budget", type=float, default=None, help="plafond en euros pour ce pack")
    p.add_argument("--output")
    p.set_defaults(fn=cmd_generate)
    p = sub.add_parser("create-user", help="Créer l'utilisateur unique de l'interface serveur")
    p.add_argument("username")
    p.add_argument("--password")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--stdout", action="store_true", help="afficher le mot de passe généré une seule fois (Docker)")
    p.set_defaults(fn=cmd_create_user)
    p = sub.add_parser("api-key", help="Clés d'API : create NOM --scopes read,generate | list | revoke NOM")
    p.add_argument("action", choices=["create", "list", "revoke"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--scopes", help="read, analyze, generate, feedback, outcomes, benchmark, admin (séparés par des virgules)")
    p.set_defaults(fn=cmd_api_key)
    sub.add_parser("secret", help="Générer une SECRET_KEY").set_defaults(fn=cmd_secret)
    p = sub.add_parser("benchmark", help="Benchmark déterministe (offres du dossier benchmark/)")
    p.add_argument("--no-legacy", action="store_true")
    p.add_argument("--output")
    p.add_argument("--persist", action="store_true", help="enregistrer en base (historique + page Benchmark de l'interface serveur)")
    p.set_defaults(fn=cmd_benchmark)
    p = sub.add_parser("build-studio", help="Construire la page PAI Studio (web/)")
    p.add_argument("--output")
    p.add_argument("--server", action="store_true", help="variante servie par le serveur PAI (API /v1 au lieu de claude.ai)")
    p.set_defaults(fn=cmd_build_studio)
    p = sub.add_parser("worker", help="Worker de jobs (file PostgreSQL)")
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_worker)
    args = parser.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
