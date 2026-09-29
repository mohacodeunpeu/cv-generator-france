"""Détection des ressources réelles de la machine (aucune supposition) pour choisir un modèle local réaliste.

Lit : architecture, cœurs utilisables (affinité + quota cgroup), modèle de processeur, mémoire totale et disponible
(avec la limite cgroup d'un conteneur), GPU NVIDIA et VRAM (nvidia-smi si présent), espace disque du dossier des
modèles. Aucune dépendance : /proc, /sys, os, shutil. Sur macOS / Windows, repli sur ce que la bibliothèque standard
sait lire (les champs inconnus restent à 0 et le choix du modèle devient prudent).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}


@dataclass
class Hardware:
    arch: str = ""
    cpu_model: str = ""
    cpus: float = 0.0              # cœurs réellement utilisables (quota cgroup compris)
    ram_total_gb: float = 0.0      # limite du conteneur si elle est plus basse que la machine
    ram_available_gb: float = 0.0
    gpus: list[dict] = field(default_factory=list)   # [{"name": …, "vram_gb": …}]
    disk_free_gb: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def vram_gb(self) -> float:
        return max((g.get("vram_gb", 0.0) for g in self.gpus), default=0.0)

    def as_dict(self) -> dict:
        return asdict(self) | {"vram_gb": self.vram_gb}


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _meminfo_gb(key: str) -> float:
    for line in _read("/proc/meminfo").splitlines():
        if line.startswith(key + ":"):
            try:
                return int(line.split()[1]) / 1024 / 1024
            except (IndexError, ValueError):
                return 0.0
    return 0.0


def _cgroup_memory_limit_gb() -> float:
    """Limite mémoire du conteneur (cgroup v2 puis v1) ; 0 si aucune."""
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        raw = _read(path).strip()
        if raw and raw != "max":
            try:
                value = int(raw)
            except ValueError:
                continue
            if 0 < value < 1 << 60:        # v1 renvoie un très grand nombre quand il n'y a pas de limite
                return value / 1024 ** 3
    return 0.0


def _cgroup_cpus() -> float:
    raw = _read("/sys/fs/cgroup/cpu.max").split()
    if len(raw) == 2 and raw[0] != "max":
        try:
            return int(raw[0]) / int(raw[1])
        except (ValueError, ZeroDivisionError):
            return 0.0
    quota, period = _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").strip(), _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us").strip()
    try:
        if int(quota) > 0:
            return int(quota) / int(period)
    except ValueError:
        pass
    return 0.0


def _cpu_model() -> str:
    for line in _read("/proc/cpuinfo").splitlines():
        low = line.lower()
        if low.startswith(("model name", "hardware", "cpu model")):
            return line.split(":", 1)[-1].strip()
    if platform.machine().lower() in ("aarch64", "arm64"):
        part = next((ln.split(":", 1)[-1].strip() for ln in _read("/proc/cpuinfo").splitlines() if ln.lower().startswith("cpu part")), "")
        return {"0xd0c": "ARM Neoverse-N1 (Ampere Altra)", "0xd40": "ARM Neoverse-V1", "0xd4f": "ARM Neoverse-V2"}.get(part, "ARM64")
    return platform.processor() or ""


def _gpus() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        name, _, mem = line.rpartition(",")
        try:
            gpus.append({"name": name.strip(), "vram_gb": round(int(mem.strip()) / 1024, 1)})
        except ValueError:
            continue
    return gpus


def detect(models_dir: str | Path | None = None) -> Hardware:
    hw = Hardware(arch=_ARCH.get(platform.machine().lower(), platform.machine().lower()), cpu_model=_cpu_model())
    try:
        cpus = float(len(os.sched_getaffinity(0)))
    except AttributeError:
        cpus = float(os.cpu_count() or 0)
    quota = _cgroup_cpus()
    if quota and quota < cpus:
        hw.notes.append(f"quota CPU du conteneur : {quota:.1f} cœur(s)")
        cpus = quota
    hw.cpus = round(cpus, 1)
    total, available = _meminfo_gb("MemTotal"), _meminfo_gb("MemAvailable")
    limit = _cgroup_memory_limit_gb()
    if limit and (not total or limit < total):
        hw.notes.append(f"limite mémoire du conteneur : {limit:.1f} Go")
        total, available = limit, min(available or limit, limit)
    hw.ram_total_gb, hw.ram_available_gb = round(total, 1), round(available, 1)
    hw.gpus = _gpus()
    target = Path(models_dir) if models_dir else Path.cwd()
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        hw.disk_free_gb = round(shutil.disk_usage(target).free / 1024 ** 3, 1)
    except OSError:
        hw.disk_free_gb = 0.0
    return hw
