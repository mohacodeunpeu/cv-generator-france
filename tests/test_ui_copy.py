"""Garde-fou de rédaction : l'interface parle un français soigné (docs/DESIGN_SYSTEM.md, « Typographie »).

Pas de pluriel « ligne(s) » : l'accord se fait avec nb(n, 'ligne', 'lignes') dans web/studio/app/00_core.js.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "web" / "studio" / "app"


def test_no_parenthesised_plurals_in_ui_strings():
    bad = []
    for f in sorted(APP.glob("*.js")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("//"):
                continue
            bad += [f"{f.name}:{i}: {m.group(0)}" for m in re.finditer(r"\b[a-zà-ÿ]+\(s\)", line)]
    assert not bad, bad


def test_run_details_are_not_english_jargon():
    src = (APP / "20_pipeline.js").read_text(encoding="utf-8")
    for jargon in ("MATCH ${", "QUALITY ${", "RISK ${", "mots-clés REQUIRED"):
        assert jargon not in src, jargon
