"""Normalisation de texte partagée par l'analyse, le matching et le validateur.

Tout ce qui compare du texte passe par `norm()` : minuscules, sans accents,
apostrophes et tirets unifiés, espaces compactés.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Iterable

_APOS = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", "‛": "'"})
_DASH = str.maketrans({"–": "-", "—": "-", "‑": "-", "−": "-", "‐": "-"})
_SPACES = re.compile(r"[\s   ]+")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def norm(text: str | None) -> str:
    if not text:
        return ""
    text = strip_accents(str(text)).lower().translate(_APOS).translate(_DASH)
    text = text.replace("œ", "oe").replace("æ", "ae")
    return _SPACES.sub(" ", text).strip()


def _boundary_pattern(term_norm: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(term_norm) + r"(?![a-z0-9])")


_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def plural_variants(term_norm: str) -> list[str]:
    """Variantes singulier/pluriel simples (dernier mot)."""
    variants = {term_norm}
    if not term_norm:
        return []
    last = term_norm.split(" ")[-1]
    head = term_norm[: len(term_norm) - len(last)]
    if len(last) > 3:
        if last.endswith("s") or last.endswith("x"):
            variants.add(head + last[:-1])
        else:
            variants.add(head + last + "s")
    return sorted(variants)


def contains_term(haystack_norm: str, term: str) -> bool:
    """Le terme (déjà normalisé ou non) apparaît-il comme mot entier dans le texte normalisé ?"""
    term_n = norm(term)
    if not term_n:
        return False
    for variant in plural_variants(term_n):
        pattern = _PATTERN_CACHE.get(variant)
        if pattern is None:
            pattern = _boundary_pattern(variant)
            _PATTERN_CACHE[variant] = pattern
        if pattern.search(haystack_norm):
            return True
    return False


# ── Nombres ──────────────────────────────────────────────────────────────────

_NUM_WORDS = {
    "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7", "huit": "8",
    "neuf": "9", "dix": "10", "onze": "11", "douze": "12", "quinze": "15", "vingt": "20",
    "trente": "30", "quarante": "40", "cinquante": "50", "cent": "100", "mille": "1000",
    "two": "2", "three": "3", "four": "4", "five": "5", "ten": "10", "twenty": "20", "hundred": "100",
    "double": "2", "doubler": "2", "triple": "3", "tripler": "3",
}
# Mots qui ressemblent à des nombres mais n'en sont pas dans ce contexte.
_NUM_WORD_EXCEPTIONS = {"sept"}  # « sept. » = septembre ; traité à part

_NUMBER = re.compile(r"(?<![a-z0-9])(\d{1,3}(?:[ .  ]\d{3})+|\d+(?:[.,]\d+)?)(?![0-9])")


def extract_numbers(text: str) -> list[str]:
    """Nombres « noyaux » : '+35 %' → '35', '360 K€' → '360', '1 200' → '1200', '915/990' → '915','990'."""
    t = norm(text)
    found: list[str] = []
    for m in _NUMBER.finditer(t):
        raw = m.group(1)
        compact = re.sub(r"[ .  ]", "", raw) if re.fullmatch(r"\d{1,3}(?:[ .  ]\d{3})+", raw) else raw
        compact = compact.replace(",", ".")
        if "." in compact:
            compact = compact.rstrip("0").rstrip(".") or "0"
        found.append(compact)
    for word, value in _NUM_WORDS.items():
        if word in _NUM_WORD_EXCEPTIONS:
            continue
        if contains_term(t, word):
            found.append(value)
    return found


_YEAR = re.compile(r"(?<![0-9])(19[5-9]\d|20[0-4]\d)(?![0-9])")


def extract_years(text: str) -> list[str]:
    return _YEAR.findall(norm(text))


# ── Hachage stable ───────────────────────────────────────────────────────────

def stable_hash(obj: object, length: int = 12) -> str:
    if isinstance(obj, (bytes, bytearray)):
        payload = bytes(obj)
    elif isinstance(obj, str):
        payload = obj.encode("utf-8")
    else:
        payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = norm(item)
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def word_count(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text or ""))
