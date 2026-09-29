"""Commandes `python -m pai ai …` : état, détection, mesure, choix automatique et installation des modèles locaux.

  status        machine + Ollama + fournisseur actif, profil, plan du routeur, choix enregistré
  detect        ressources réelles et candidats compatibles
  bench         mesure des modèles installés (et du mode sans IA) sur les tâches PAI
  setup         detect → (pull) → bench des candidats installés qui tiennent → choix enregistré
  pull NOM      téléchargement depuis la bibliothèque Ollama (registry.ollama.ai)
  import-gguf   téléchargement d'un GGUF publié sur Docker Hub (espace ai/) puis import dans Ollama par son API
                (utile quand la bibliothèque Ollama n'est pas joignable ; empreinte sha256 vérifiée)
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings
from ..providers.ollama import OllamaProvider, normalize_base_url, probe, reset_probe_cache
from . import registry, selfeval
from .hardware import detect


def base_url(arg: str | None = None) -> str:
    s = get_settings()
    return normalize_base_url(arg or s.ollama_base_url or s.ai_base_url or s.local_base_url)


def status(url: str | None = None) -> dict[str, Any]:
    from ..providers import active_profile, active_provider_id, build_router
    from ..providers.ollama import load_selection
    from ..providers.store import read_stored_settings

    settings, stored = get_settings(), read_stored_settings()
    active = active_provider_id(settings, stored)
    router = build_router(active, settings, stored)
    reset_probe_cache()
    return {"machine": detect().as_dict(), "ollama": probe(base_url(url)), "active_provider": active,
            "mode": router.mode(), "profile": active_profile(settings, stored), "plan": router.plan(),
            "selection": load_selection()}


def pull(name: str, url: str | None = None) -> dict[str, Any]:
    r = httpx.post(f"{base_url(url)}/api/pull", json={"model": name, "stream": False}, timeout=httpx.Timeout(3600, connect=10))
    r.raise_for_status()
    reset_probe_cache()
    return r.json()


# ── Import depuis Docker Hub (artefacts OCI « ai/… ») ────────────────────────────────────────────
_ACCEPT = ", ".join(["application/vnd.oci.image.index.v1+json", "application/vnd.oci.image.manifest.v1+json",
                     "application/vnd.docker.distribution.manifest.v2+json"])


def _hub_token(c: httpx.Client, repo: str) -> str:
    return c.get(f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull").json()["token"]


def _hub_manifest(c: httpx.Client, repo: str, ref: str) -> dict[str, Any]:
    r = c.get(f"https://registry-1.docker.io/v2/{repo}/manifests/{ref}", headers={"Authorization": f"Bearer {_hub_token(c, repo)}", "Accept": _ACCEPT})
    r.raise_for_status()
    m = r.json()
    return _hub_manifest(c, repo, m["manifests"][0]["digest"]) if "manifests" in m else m


def _gguf_layer(m: dict[str, Any]) -> dict[str, Any]:
    def ok(layer: dict[str, Any]) -> bool:
        fp = (layer.get("annotations") or {}).get("org.cncf.model.filepath", "")
        return ("gguf" in layer["mediaType"] or fp.endswith(".gguf")) and "mmproj" not in fp
    layers = [layer for layer in m.get("layers", []) if ok(layer)]
    if not layers:
        raise ValueError("aucun fichier GGUF dans cet artefact")
    return max(layers, key=lambda layer: layer["size"])


def import_gguf(ref: str, name: str, url: str | None = None, workdir: str | None = None, echo=print) -> dict[str, Any]:
    """ref = « ai/qwen3:4b-instruct-2507-q4_K_M ». Télécharge (reprise), vérifie le sha256, envoie le blob à Ollama,
    crée le modèle `name`, supprime le fichier temporaire."""
    repo, tag = ref.rsplit(":", 1)
    api = base_url(url)
    with httpx.Client(timeout=httpx.Timeout(60, read=900), follow_redirects=True) as c:
        layer = _gguf_layer(_hub_manifest(c, repo, tag))
        digest, size = layer["digest"], int(layer["size"])
        tmp = Path(workdir or tempfile.gettempdir()) / f"pai-{name.replace(':', '_')}.gguf"
        for _ in range(6):
            have = tmp.stat().st_size if tmp.exists() else 0
            if have >= size:
                break
            headers = {"Authorization": f"Bearer {_hub_token(c, repo)}"} | ({"Range": f"bytes={have}-"} if have else {})
            try:
                with c.stream("GET", f"https://registry-1.docker.io/v2/{repo}/blobs/{digest}", headers=headers) as r:
                    r.raise_for_status()
                    with open(tmp, "ab" if have and r.status_code == 206 else "wb") as f:
                        for chunk in r.iter_bytes(1 << 20):
                            f.write(chunk)
            except httpx.HTTPError as exc:
                echo(f"  reprise du téléchargement ({exc.__class__.__name__})")
        sha = hashlib.sha256()
        with open(tmp, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha.update(chunk)
        if f"sha256:{sha.hexdigest()}" != digest:
            tmp.unlink(missing_ok=True)
            raise ValueError("empreinte sha256 différente : fichier rejeté")
        with open(tmp, "rb") as f:
            c.post(f"{api}/api/blobs/{digest}", content=f, timeout=httpx.Timeout(1800, connect=10)).raise_for_status()
        r = c.post(f"{api}/api/create", json={"model": name, "files": {Path(layer.get("annotations", {}).get("org.cncf.model.filepath", "model.gguf")).name: digest},
                                              "stream": False}, timeout=httpx.Timeout(1800, connect=10))
        r.raise_for_status()
        tmp.unlink(missing_ok=True)
    reset_probe_cache()
    return {"name": name, "size_gb": round(size / 1e9, 2), "digest": digest}


# ── Mesure et choix ─────────────────────────────────────────────────────────────────────────────
def bench(models: list[str] | None = None, url: str | None = None, echo=print) -> dict[str, Any]:
    api = base_url(url)
    reset_probe_cache()
    state = probe(api)
    if not state.get("reachable"):
        raise SystemExit(f"Ollama injoignable sur {api} : {state.get('error')}")
    installed = [m["name"] for m in state["models"]]
    hw = detect()
    if not models:
        models = []
        for n in installed:
            c = registry.by_installed_name(n) or registry.by_installed_name(n.removesuffix(":latest"))
            if c and "embed" not in c.tiers and registry.fits(c, hw)[0]:
                models.append(n)
    results = [selfeval.run_deterministic()]
    echo(f"sans IA : qualité {results[0]['quality']} (tâches déterministes : {', '.join(results[0]['scores'])})")
    for name in models:
        echo(f"… {name}")
        p = OllamaProvider(base_url=api, model=name, tier="large")
        r = selfeval.run_provider(p)
        r["model"] = name
        r["memory_gb"] = selfeval.loaded_memory_gb(api, name)
        echo(f"  qualité {r['quality']} · {r['tokens_per_s']} jetons/s · {r['total_s']} s · {r['memory_gb']} Go · "
             + " ".join(f"{k} {v:.0f}" for k, v in r["scores"].items()))
        results.append(r)
    mins = registry.load_registry().get("min_tokens_per_second", {"small": 8, "large": 3})
    choice = selfeval.choose([r for r in results if r["model"] != "sans IA"], mins)
    embed = next((n for n in installed if (c := registry.by_installed_name(n.removesuffix(":latest"))) and "embed" in c.tiers), "")
    if embed:
        choice["embed"] = embed.removesuffix(":latest")
    return {"machine": hw.as_dict(), "ollama_version": state.get("version"), "results": results, "choice": choice, "thresholds": mins}


def setup(url: str | None = None, do_pull: bool = False, echo=print) -> dict[str, Any]:
    hw = detect()
    echo(f"Machine : {hw.arch}, {hw.cpus:.0f} cœur(s), {hw.ram_total_gb} Go de RAM, GPU : "
         + (", ".join(f"{g['name']} {g['vram_gb']} Go" for g in hw.gpus) or "aucun") + f", disque libre {hw.disk_free_gb} Go")
    rec = registry.recommend(hw)
    if do_pull:
        for tier in ("small", "large", "embed"):
            best = next((c for c in rec[tier] if c["fits"]), None)
            if best:
                echo(f"Téléchargement {tier} : {best['ollama']}")
                pull(best["ollama"], url)
    report = bench(url=url, echo=echo)
    if not report["choice"]:
        echo("Aucun modèle assez rapide et assez bon : PAI reste en mode SANS IA (tout fonctionne, voies déterministes).")
    path = selfeval.save_selection(report["choice"], report)
    echo(f"Choix enregistré ({path}) : {json.dumps(report['choice'], ensure_ascii=False)}")
    return report


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m pai ai")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("status", "detect"):
        sub.add_parser(cmd).add_argument("--base-url")
    b = sub.add_parser("bench")
    b.add_argument("--models", default="")
    b.add_argument("--base-url")
    b.add_argument("--json", default="")
    s = sub.add_parser("setup")
    s.add_argument("--base-url")
    s.add_argument("--pull", action="store_true", help="télécharger d'abord les candidats recommandés (bibliothèque Ollama)")
    p = sub.add_parser("pull")
    p.add_argument("name")
    p.add_argument("--base-url")
    i = sub.add_parser("import-gguf")
    i.add_argument("ref", help="ex. ai/qwen3:4b-instruct-2507-q4_K_M")
    i.add_argument("--name", required=True)
    i.add_argument("--base-url")
    args = ap.parse_args(argv)
    if args.cmd == "status":
        print(json.dumps(status(args.base_url), ensure_ascii=False, indent=1))
    elif args.cmd == "detect":
        hw = detect()
        print(json.dumps({"machine": hw.as_dict(), "candidates": registry.recommend(hw)}, ensure_ascii=False, indent=1))
    elif args.cmd == "bench":
        report = bench([m for m in args.models.split(",") if m] or None, args.base_url)
        if args.json:
            Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(report["choice"], ensure_ascii=False))
    elif args.cmd == "setup":
        setup(args.base_url, args.pull)
    elif args.cmd == "pull":
        print(json.dumps(pull(args.name, args.base_url), ensure_ascii=False))
    elif args.cmd == "import-gguf":
        print(json.dumps(import_gguf(args.ref, args.name, args.base_url), ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
