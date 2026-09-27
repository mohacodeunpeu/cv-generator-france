"""Construit PAI Studio (page unique pour claude.ai) à partir des sources web/studio/ et des règles du dépôt.

Sortie : web/dist/pai_studio.html (+ pdf.worker.min.js à publier à côté).
Les règles, prompts et polices sont injectés : une seule source de vérité, le dépôt.
Le profil N'EST PAS injecté (données personnelles) : il vit dans la base privée de l'artefact.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pai import ENGINE_VERSION  # noqa: E402
from pai.rules import load_prompts, load_rules, prompts_version  # noqa: E402

STUDIO = ROOT / "web" / "studio"
DIST = ROOT / "web" / "dist"
VENDOR = ROOT / "web" / "vendor"
PDFJS_VERSION = "3.11.174"
FONTS = ["FiraSans-Regular.ttf", "FiraSans-Italic.ttf", "FiraSans-Medium.ttf", "FiraSans-SemiBold.ttf", "FiraSans-Bold.ttf"]


def example_offers() -> dict:
    """Une offre FICTIVE (SYNTHETIC) pour le bouton « Exemple » : jamais présentée comme réelle."""
    import yaml

    raw = yaml.safe_load((ROOT / "benchmark" / "offers" / "01_bd_saas_paris.yaml").read_text(encoding="utf-8"))
    return {raw["id"]: {"title": raw["title"], "company": raw["company"], "text": raw["text"], "synthetic": True}}


LIBS = {  # bibliothèque → (paquet npm, fichier dans le paquet)
    "pdfmake.min.js": ("pdfmake@0.2.20", "package/build/pdfmake.min.js"),
    "jszip.min.js": ("jszip@3.10.1", "package/dist/jszip.min.js"),
    "pdf.min.js": (f"pdfjs-dist@{PDFJS_VERSION}", "package/build/pdf.min.js"),
    "pdf.worker.min.js": (f"pdfjs-dist@{PDFJS_VERSION}", "package/build/pdf.worker.min.js"),
}


def ensure_vendor(name: str) -> Path:
    """Copie locale d'une bibliothèque (tests hors ligne, worker pdf.js publié à côté de la page)."""
    target = VENDOR / name
    if target.exists():
        return target
    VENDOR.mkdir(parents=True, exist_ok=True)
    package, member_name = LIBS[name]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["npm", "pack", package, "--silent"], cwd=tmp, check=True, capture_output=True)
        tgz = next(Path(tmp).glob("*.tgz"))
        with tarfile.open(tgz) as tar:
            with tar.extractfile(tar.getmember(member_name)) as src:  # type: ignore[union-attr]
                target.write_bytes(src.read())
    return target


def studio_data() -> dict:
    rules = load_rules()
    prompts = {name: {"version": p.version, "template": p.template} for name, p in load_prompts().items()}
    return {
        "examples": example_offers(),
        "version": {"engine": ENGINE_VERSION, "rules": rules.version, "prompts": prompts_version()},
        "sectors": rules.sectors,
        "countries": rules.countries,
        "designs": rules.designs,
        "synonyms": {"equivalents": rules.synonyms.groups, "implies": rules.synonyms.implies},
        "banned": {"hard": rules.banned_hard, "soft": rules.banned_soft},
        "scoring": rules.scoring,
        "models": {k: rules.models.get(k) for k in ("artifact_tiers", "modes", "generation")},
        "brand": rules.brand,
        "prompts": prompts,
    }


def ensure_pdf_worker() -> Path:
    return ensure_vendor("pdf.worker.min.js")


def build(output: Path | None = None) -> str:
    DIST.mkdir(parents=True, exist_ok=True)
    data = json.dumps(studio_data(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    fonts = {name: base64.b64encode((ROOT / "fonts" / name).read_bytes()).decode("ascii") for name in FONTS}
    html = (STUDIO / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*@STYLES@*/", (STUDIO / "styles.css").read_text(encoding="utf-8"))
    html = html.replace("/*@DATA@*/", f"window.PAI_DATA = {data};")
    html = html.replace("/*@FONTS@*/", "window.PAI_FONTS = " + json.dumps(fonts, separators=(",", ":")) + ";")
    html = html.replace("/*@ENGINE@*/", (STUDIO / "engine.js").read_text(encoding="utf-8"))
    html = html.replace("/*@APP@*/", (STUDIO / "app.js").read_text(encoding="utf-8"))
    out = output or DIST / "pai_studio.html"
    out.write_text(html, encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    return f"{out} ({size_kb} Ko)"


def write_data_json(path: Path) -> None:
    path.write_text(json.dumps(studio_data(), ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--data-json":
        write_data_json(Path(sys.argv[2]))
        print(sys.argv[2])
    else:
        print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
