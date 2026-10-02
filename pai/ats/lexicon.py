"""Lexique français léger, sans modèle : mots vides, remplissage des exigences, racinisation, similarité floue.

C'est la couche « sémantique » par défaut de PAI (aucune IA, aucun réseau). Elle rapproche des formes
(« prospecter » ↔ « prospection ») ; elle ne prouve rien à elle seule : une correspondance approximative
donne au mieux PLAUSIBLE, jamais PROUVÉ (voir requirements.prove).
"""

from __future__ import annotations

import re

from ..textnorm import norm

STOPWORDS = set("""
a au aux avec ce ces cet cette chez d dans de des du elle en et etc il ils je j l la le les leur leurs lui ma mais me
mes mon ne ni nos notre nous on ou par pas pour qu que qui sa se ses si son sur ta te tes ton tu un une vos votre vous
y afin ainsi alors aussi autre autres avoir bien car cela comme dont donc entre etre fait faire ici leur meme ni peu
plus puis quand quel quelle quelles quels sans selon sous tout toute toutes tous tres via the and of to in for with
at on by an or as is are be your our we you will this that from sont est sera seront etes sommes
avez ont chaque tous toutes afin
""".split())

# Mots qui entourent une exigence sans en être le contenu (« Maîtrise d'un CRM indispensable » → « crm »).
FILLER = set("""
utilisation utiliser utilise maitrise maitriser maitrisez connaissance connaissances connaitre connaissez experience
experiences experimente premiere premier bonne bon bonnes bons excellente excellent excellentes solide solides forte
fort capacite capacites aptitude aptitudes sens gout competence competences savoir requis requise requises exige exigee
indispensable indispensables obligatoire obligatoires souhaite souhaitee souhaitable apprecie appreciee appreciees
atout idealement minimum minimale secteur domaine domaines notions notion pratique usage outil outils logiciel logiciels
environnement environnements idealement vous etes avez disposez justifiez maitrisez parlez possedez niveau
professionnelle professionnel similaire equivalent equivalente souhaitez aimez envie serait plus un est
""".split())

# Suffixes retirés (du plus long au plus court) ; la racine garde au moins 4 lettres.
_SUFFIXES = ("issements", "issement", "ications", "ication", "atrices", "atrice", "ateurs", "ateur", "ations", "ation",
             "ements", "ement", "ments", "ment", "ances", "ance", "ences", "ence", "euses", "euse", "eurs", "eur",
             "ions", "ion", "ives", "ive", "ifs", "if", "iques", "ique", "istes", "iste", "ables", "able", "ees", "ee",
             "ers", "er", "ez", "es", "e", "s", "x")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.-]*[a-z0-9+#]|[a-z0-9]")


def stem(word: str) -> str:
    w = norm(word)
    if w.endswith("aux") and len(w) > 5:
        return w[:-3] + "al"
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(norm(text).replace("'", " "))


def content_tokens(text: str) -> list[str]:
    """Mots porteurs de sens (sans mots vides ni remplissage), dans l'ordre, sans doublon."""
    out: list[str] = []
    for t in tokens(text):
        if t in STOPWORDS or t in FILLER or (len(t) < 3 and not t.isdigit() and t not in ("ux", "ui", "rh", "bi", "pr")):
            continue
        if t not in out:
            out.append(t)
    return out


def core(text: str) -> str:
    """L'exigence sans son remplissage (« Maîtrise d'un CRM indispensable » → « crm »)."""
    return " ".join(content_tokens(text))


def stems(text: str) -> set[str]:
    return {stem(t) for t in content_tokens(text)}


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fuzzy_equal(a: str, b: str) -> bool:
    """Coquille ou variante d'orthographe : mots de 6 lettres et plus, une lettre d'écart (deux à partir de 10)."""
    if len(a) < 6 or len(b) < 6:
        return False
    return levenshtein(a, b) <= (1 if max(len(a), len(b)) < 10 else 2)


def dice(a: str, b: str) -> float:
    """Similarité de deux phrases (bigrammes de caractères, texte normalisé) : 1 = identiques."""
    x, y = norm(a), norm(b)
    ba = [x[i:i + 2] for i in range(len(x) - 1)]
    bb = [y[i:i + 2] for i in range(len(y) - 1)]
    if not ba or not bb:
        return 0.0
    counts: dict[str, int] = {}
    for g in ba:
        counts[g] = counts.get(g, 0) + 1
    inter = 0
    for g in bb:
        if counts.get(g, 0) > 0:
            counts[g] -= 1
            inter += 1
    return 2 * inter / (len(ba) + len(bb))


def stem_related(a: str, b: str) -> bool:
    """Racines voisines (l'une prolonge l'autre, 6 lettres communes au moins) : « qualifi » ↔ « qualific »."""
    short, long = sorted((a, b), key=len)
    return len(short) >= 6 and long.startswith(short)
