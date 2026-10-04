"""Lecture sûre d'une URL publique (protection SSRF) : une offre d'emploi lue à la demande de l'utilisateur.

Règles : http/https seulement, ports 80/443, aucun identifiant dans l'URL ; TOUTES les adresses résolues doivent
être publiques (boucle locale, réseaux privés, lien local dont 169.254.169.254, CGNAT, multicast, réservées… sont
refusées, y compris écrites en décimal, octal, hexadécimal ou en IPv6 « mappée ») ; redirections suivies à la main
et revalidées à chaque saut ; corps lu en flux, borné (décompression comprise) ; adresse réellement connectée
revérifiée après connexion (défense contre le DNS rebinding). Les proxys de l'environnement sont ignorés :
la connexion doit partir vers l'adresse validée. Seule exception, explicite : PAI_FETCH_PROXY (réseau d'entreprise
qui impose un proxy sortant) ; les adresses sont alors toujours validées avant chaque requête, mais l'adresse
connectée est celle du proxy (choisi par l'administrateur), donc non revérifiable.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import ssl
import time
import zlib
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .textnorm import strip_accents

USER_AGENT = "PAI/1.0 (usage personnel ; lecture d'une offre à la demande de l'utilisateur)"
USER_AGENT_HEADER = strip_accents(USER_AGENT)  # en-tête HTTP en ASCII (« à » → « a ») : httpx et certains serveurs refusent le reste
DEFAULT_PORTS = {"http": 80, "https": 443}
ALLOWED_PORTS = frozenset({80, 443})
REDIRECTS = frozenset({301, 302, 303, 307, 308})
PASTE_HINT = "collez le texte de l'offre ou importez le PDF"

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[..., Any]  # même contrat que socket.getaddrinfo(host, port, type=…)

# Réseaux jamais joignables, en plus des drapeaux du module ipaddress (Python 3.12 classe le multicast et
# fec0::/10 comme « globaux », d'où la liste explicite).
_BLOCKED = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24",
    "192.168.0.0/16", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4",
    "::/128", "::1/128", "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8"))
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NUMERIC_PART = re.compile(r"^(0x[0-9a-f]*|[0-9]+)$", re.I)
_HOST_NAME = re.compile(r"^[a-z0-9._-]+$")


class FetchError(Exception):
    """Échec de lecture. `code` stable (bad_url, blocked_address, too_large, timeout, http_error, unreadable),
    `message` affichable tel quel (français)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes

    @property
    def mime(self) -> str:
        return self.content_type.split(";", 1)[0].strip().lower()

    @property
    def charset(self) -> str | None:
        m = re.search(r"charset=[\"']?([\w.:-]+)", self.content_type, re.I)
        return m.group(1) if m else None


# ── Adresses ────────────────────────────────────────────────────────────────
def _unwrap(ip: IPAddress) -> IPAddress:
    """IPv6 qui transporte une IPv4 (::ffff:a.b.c.d, NAT64 64:ff9b::/96) → l'IPv4 réellement visée."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip in _NAT64:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def is_public_ip(value: IPAddress | str) -> bool:
    """Vrai seulement pour une adresse unicast routable sur Internet."""
    try:
        ip = _unwrap(ipaddress.ip_address(value) if isinstance(value, str) else value)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = [v4 for v4 in (ip.sixtofour, *(ip.teredo or ())) if v4 is not None]
        if int(ip) >> 32 == 0:  # IPv4 « compatible » ::a.b.c.d (obsolète)
            embedded.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if any(not is_public_ip(v4) for v4 in embedded):
            return False
    flags = (ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified,
             getattr(ip, "is_site_local", False))
    return ip.is_global and not any(flags) and not any(ip in net for net in _BLOCKED if net.version == ip.version)


def parse_ip_literal(host: str) -> IPAddress | None:
    """Hôte écrit comme une adresse IP, y compris les formes acceptées par inet_aton (2130706433, 0x7f.1,
    017700000001, 127.1…). None pour un nom de domaine ; ValueError pour une forme numérique invalide."""
    host = host.strip("[]").rstrip(".")
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    parts = host.split(".")
    if not host or not all(_NUMERIC_PART.match(p) for p in parts):
        return None
    if len(parts) > 4:
        raise ValueError(host)
    values = [int(p[2:] or "0", 16) if p[:2].lower() == "0x" else int(p, 8) if len(p) > 1 and p[0] == "0" else int(p)
              for p in parts]
    *head, last = values
    if any(v > 255 for v in head) or last >= 256 ** (5 - len(parts)):
        raise ValueError(host)
    number = 0
    for v in head:
        number = number * 256 + v
    return ipaddress.IPv4Address((number << 8 * (5 - len(parts))) | last)


def _refuse(host: str) -> FetchError:
    return FetchError("blocked_address", f"Adresse refusée : « {host} » ne mène pas à un site public d'Internet "
                                         "(réseau privé, local ou réservé).")


def _parse(url: str | httpx.URL) -> httpx.URL:
    try:
        return url if isinstance(url, httpx.URL) else httpx.URL(url.strip())
    except (httpx.InvalidURL, TypeError, ValueError, AttributeError) as exc:
        raise FetchError("bad_url", "Adresse invalide : vérifiez l'URL de l'offre.") from exc


def check_url(url: str | httpx.URL, resolver: Resolver = socket.getaddrinfo) -> httpx.URL:
    """Valide schéma, port, identifiants et hôte, puis TOUTES les adresses résolues. Renvoie l'URL analysée par httpx
    (celle qui sera réellement demandée : aucun écart entre l'analyse de contrôle et celle de la requête)."""
    parsed = _parse(url)
    if parsed.scheme not in DEFAULT_PORTS:
        raise FetchError("bad_url", "Seules les adresses http:// et https:// sont acceptées.")
    if parsed.userinfo:
        raise FetchError("bad_url", "Adresse refusée : l'URL contient des identifiants (utilisateur:mot de passe@).")
    port = parsed.port or DEFAULT_PORTS[parsed.scheme]
    if port not in ALLOWED_PORTS:
        raise FetchError("bad_url", f"Port {port} refusé : seuls les ports 80 et 443 sont autorisés.")
    host = parsed.raw_host.decode("ascii", "replace")  # nom encodé IDNA : c'est lui qui est résolu puis connecté
    if not host:
        raise FetchError("bad_url", "Adresse invalide : nom de domaine manquant.")
    try:
        literal = parse_ip_literal(host)
    except ValueError as exc:
        raise FetchError("bad_url", "Adresse IP invalide.") from exc
    if literal is not None:
        if not is_public_ip(literal):
            raise _refuse(host)
        return parsed
    name = host.rstrip(".")
    if name == "localhost" or name.endswith(".localhost"):
        raise _refuse(name)
    if not _HOST_NAME.match(name):
        raise FetchError("bad_url", "Adresse invalide : nom de domaine incorrect.")
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:  # socket.gaierror inclus
        raise FetchError("bad_url", f"Nom de domaine introuvable ({name}) : vérifiez l'URL.") from exc
    addresses: list[IPAddress] = []
    for info in infos or []:
        try:
            addresses.append(ipaddress.ip_address(str(info[4][0])))
        except (ValueError, IndexError, TypeError) as exc:  # réponse de résolution inattendue : refus
            raise _refuse(name) from exc
    if not addresses:
        raise FetchError("bad_url", f"Nom de domaine introuvable ({name}) : vérifiez l'URL.")
    if not all(is_public_ip(ip) for ip in addresses):
        raise _refuse(name)
    return parsed


def _peer_address(response: httpx.Response) -> str | None:
    """Adresse réellement connectée (transport httpx standard) ; None si le transport ne l'expose pas."""
    get = getattr(response.extensions.get("network_stream"), "get_extra_info", None)
    if get is None:
        return None
    try:
        addr = get("server_addr")
    except Exception:  # noqa: BLE001 — information facultative
        return None
    return str(addr[0]) if isinstance(addr, (tuple, list)) and addr else None


# ── Corps borné ─────────────────────────────────────────────────────────────
class _Inflater:
    """Décompression bornée (gzip, deflate) : jamais plus de `room` octets produits par appel (bombes)."""

    def __init__(self, encoding: str) -> None:
        codings = [c for c in (x.strip().lower() for x in encoding.split(",")) if c and c != "identity"]
        if len(codings) > 1 or (codings and codings[0] not in ("gzip", "x-gzip", "deflate")):
            raise FetchError("unreadable", f"Encodage de la page non pris en charge : {PASTE_HINT}.")
        self.coding = codings[0] if codings else ""
        wbits = 16 + zlib.MAX_WBITS if self.coding in ("gzip", "x-gzip") else zlib.MAX_WBITS
        self._z = zlib.decompressobj(wbits) if self.coding else None
        self._started = self._raw = False

    def feed(self, data: bytes, room: int) -> bytes:
        """`room` = octets encore admis ; renvoie au plus room + 1 octets (au-delà : l'appelant refuse)."""
        if self._z is None:
            return data
        try:
            out = self._z.decompress(data, room + 1)
        except zlib.error:
            if self.coding == "deflate" and not self._started and not self._raw:
                self._z, self._raw = zlib.decompressobj(-zlib.MAX_WBITS), True  # deflate « brut », sans en-tête zlib
                return self.feed(data, room)
            raise FetchError("unreadable", f"Page compressée illisible : {PASTE_HINT}.") from None
        self._started = True
        return out

    def flush(self, room: int) -> bytes:
        return self._z.flush(room + 1) if self._z is not None else b""


def _size(n: int) -> str:
    return f"{n / 1_000_000:g} Mo" if n >= 1_000_000 else f"{max(n // 1000, 1)} ko"


def _too_slow() -> FetchError:
    return FetchError("timeout", f"Le site met trop de temps à répondre : {PASTE_HINT}.")


def _read_body(response: httpx.Response, max_bytes: int, deadline: float) -> bytes:
    too_large = FetchError("too_large", f"Page trop volumineuse (plus de {_size(max_bytes)}) : {PASTE_HINT}.")
    length = response.headers.get("content-length", "")
    if length.isdigit() and int(length) > max_bytes:
        raise too_large
    if response.is_stream_consumed:  # corps déjà en mémoire (transport simulé) : même plafond
        if len(response.content) > max_bytes:
            raise too_large
        return response.content
    inflater = _Inflater(response.headers.get("content-encoding", ""))
    chunks: list[bytes] = []
    size = 0
    for raw in response.iter_raw():
        data = inflater.feed(raw, max_bytes - size)
        size += len(data)
        if size > max_bytes:
            raise too_large
        chunks.append(data)
        if time.monotonic() > deadline:
            raise _too_slow()
    tail = inflater.flush(max_bytes - size)
    if size + len(tail) > max_bytes:
        raise too_large
    return b"".join(chunks) + tail


_ANTI_BOT_HEADERS = ("cf-mitigated", "x-datadome", "x-dd-b", "x-px-block", "x-amzn-waf-action", "x-sucuri-block",
                     "x-distil-cs", "x-iinfo")


def is_anti_bot(status: int, headers: httpx.Headers | dict[str, str]) -> bool:
    """Protection anti-robot reconnue à ses en-têtes (Cloudflare, DataDome, PerimeterX, AWS WAF, Sucuri, Imperva)."""
    h = {k.lower(): str(v).lower() for k, v in dict(headers).items()}
    if any(k in h for k in _ANTI_BOT_HEADERS):
        return True
    return status in (403, 503) and (h.get("server", "") in ("cloudflare", "akamaighost", "ddos-guard") or "cf-ray" in h)


def _status_error(status: int, headers: httpx.Headers | dict[str, str] | None = None) -> FetchError:
    """Cause précise, affichable : le serveur PAI dit pourquoi IL n'a pas pu lire la page (jamais « Claude »)."""
    headers = headers or {}
    if is_anti_bot(status, headers):
        code, why = "anti_bot", "le site bloque les lectures automatiques (protection anti-robot)"
    elif status in (401, 407):
        code, why = "auth_required", "le site exige une connexion"
    elif status == 403:
        code, why = "forbidden", "le site refuse l'accès à cette page"
    elif status in (404, 410):
        code, why = "not_found", "page introuvable (offre retirée ?)"
    elif status == 429:
        code, why = "rate_limited", "le site limite les accès, réessayez plus tard"
    elif status >= 500:
        code, why = "unavailable", "le site est indisponible, réessayez plus tard"
    else:
        code, why = "http_error", "réponse inattendue du site"
    return FetchError(code, f"Le serveur PAI n'a pas pu récupérer cette URL (HTTP {status}) : {why}. Sinon, {PASTE_HINT}.")


# ── Lecture ─────────────────────────────────────────────────────────────────
def outbound_options() -> dict[str, Any]:
    """Proxy sortant EXPLICITE (PAI_FETCH_PROXY) et, s'il ré-chiffre le TLS, son autorité de certification
    (PAI_FETCH_CA_BUNDLE). Jamais déduit de HTTP(S)_PROXY : un proxy hérité par erreur n'est pas suivi."""
    proxy = os.environ.get("PAI_FETCH_PROXY", "").strip()
    if not proxy:
        return {}
    ca = os.environ.get("PAI_FETCH_CA_BUNDLE", "").strip()
    return {"proxy": proxy, **({"verify": ssl.create_default_context(cafile=ca)} if ca else {})}


def safe_get(url: str, *, max_bytes: int = 3_000_000, timeout: float = 15.0, max_redirects: int = 5,
             resolver: Resolver = socket.getaddrinfo, transport: httpx.BaseTransport | None = None,
             guard: Callable[[httpx.URL], None] | None = None) -> FetchResult:
    """GET sûr d'une URL publique. Chaque saut de redirection est revalidé ; lève FetchError(code, message).
    `guard(url)` : contrôle supplémentaire appelé avant toute résolution ou requête (URL initiale et chaque
    redirection) ; il lève pour refuser (ex. site fermé)."""
    guard = guard or (lambda _url: None)
    parsed = _parse(url)
    guard(parsed)
    current = check_url(parsed, resolver)
    deadline = time.monotonic() + timeout
    headers = {"User-Agent": USER_AGENT_HEADER, "Accept-Encoding": "gzip, deflate",
               "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
               "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7"}
    outbound = outbound_options() if transport is None else {}
    with httpx.Client(transport=transport, headers=headers, timeout=httpx.Timeout(timeout), follow_redirects=False,
                      trust_env=False, **outbound) as client:
        for hop in range(max_redirects + 1):
            remaining = deadline - time.monotonic()  # un seul délai pour tout le parcours, redirections comprises
            if remaining <= 0:
                raise _too_slow()
            try:
                response = client.send(client.build_request("GET", current, timeout=httpx.Timeout(remaining)), stream=True)
            except httpx.TimeoutException as exc:
                raise _too_slow() from exc
            except httpx.HTTPError as exc:
                raise FetchError("http_error", f"Site injoignable ({exc.__class__.__name__}) : {PASTE_HINT}.") from exc
            try:
                peer = None if outbound else _peer_address(response)   # via un proxy, l'adresse connectée est la sienne
                if peer is not None and not is_public_ip(peer):
                    raise _refuse(current.host)  # la résolution a changé entre le contrôle et la connexion
                if response.status_code in REDIRECTS and response.headers.get("location"):
                    if hop == max_redirects:
                        raise FetchError("http_error", f"Trop de redirections (plus de {max_redirects}) : {PASTE_HINT}.")
                    try:
                        target = current.join(response.headers["location"])
                    except (httpx.InvalidURL, ValueError) as exc:
                        raise FetchError("bad_url", "Redirection vers une adresse invalide.") from exc
                    guard(target)
                    current = check_url(target, resolver)
                    continue
                if not 200 <= response.status_code < 300:
                    raise _status_error(response.status_code, response.headers)
                try:
                    body = _read_body(response, max_bytes, deadline)
                except httpx.TimeoutException as exc:
                    raise _too_slow() from exc
                except httpx.HTTPError as exc:
                    raise FetchError("http_error", f"Lecture interrompue ({exc.__class__.__name__}) : {PASTE_HINT}.") from exc
                return FetchResult(url=str(url), final_url=str(current), status=response.status_code,
                                   content_type=response.headers.get("content-type", ""), body=body)
            finally:
                response.close()
    raise FetchError("http_error", f"Trop de redirections : {PASTE_HINT}.")  # inatteignable (boucle bornée)
