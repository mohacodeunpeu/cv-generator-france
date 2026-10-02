"""Lecture sûre d'une URL (SSRF) et offre depuis une URL : adresses, schémas, ports, redirections, taille, délai,
DNS rebinding, JSON-LD JobPosting, PDF, sites fermés, route /v1/ingest/url.

Aucun accès Internet : résolveur injecté + httpx.MockTransport (et un serveur local pour le rebinding réel).
Offres fictives uniquement.
"""

from __future__ import annotations

import functools
import gzip
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from pai import ingest
from pai.ingest import IngestError, UrlIngestError, html_to_text, is_login_walled, offer_from_url
from pai.netfetch import USER_AGENT, FetchError, check_url, is_public_ip, parse_ip_literal, safe_get
from tests.test_api import api_key, client, login, session_csrf  # noqa: F401 — fixture partagée (SQLite + PostgreSQL)

PUBLIC_IP = "93.184.216.34"


def resolver(mapping: dict[str, list[str]] | None = None, default: str | None = PUBLIC_IP):
    """Résolveur factice (contrat de socket.getaddrinfo) ; enregistre les noms demandés."""
    seen: list[tuple[str, int]] = []

    def resolve(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002, ARG001
        seen.append((host, port))
        ips = (mapping or {}).get(host) or ([default] if default else [])
        if not ips:
            raise socket.gaierror(socket.EAI_NONAME, "inconnu")
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    resolve.seen = seen  # type: ignore[attr-defined]
    return resolve


def no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"aucun appel réseau attendu : {request.url}")


def fetch_code(url: str, handler=no_network, **kwargs) -> str:
    with pytest.raises(FetchError) as info:
        safe_get(url, resolver=kwargs.pop("resolve", resolver()), transport=httpx.MockTransport(handler), **kwargs)
    return info.value.code


# ── Adresses ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("address", [
    "127.0.0.1", "127.8.9.10", "10.1.2.3", "172.16.0.1", "172.31.255.254", "192.168.1.1", "169.254.169.254", "100.64.0.1",
    "0.0.0.0", "0.1.2.3", "224.0.0.1", "239.255.255.250", "240.0.0.1", "255.255.255.255", "192.0.2.10", "198.18.0.1",
    "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "fec0::1", "ff02::1", "2001:db8::1",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "::127.0.0.1", "64:ff9b::7f00:1", "2002:7f00:1::1"])
def test_non_global_addresses_are_blocked(address):
    assert not is_public_ip(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8", "64:ff9b::808:808"])
def test_global_addresses_are_allowed(address):
    assert is_public_ip(address)


@pytest.mark.parametrize("host, expected", [
    ("2130706433", "127.0.0.1"), ("0x7f.1", "127.0.0.1"), ("0x7f000001", "127.0.0.1"), ("017700000001", "127.0.0.1"),
    ("127.1", "127.0.0.1"), ("0", "0.0.0.0"), ("10.1", "10.0.0.1"), ("0xa9.0xfe.0xa9.0xfe", "169.254.169.254"),
    ("8.8.8.8", "8.8.8.8"), ("::1", "::1"), ("example.com", None), ("offre-2130706433.example.fr", None)])
def test_ip_literal_forms_are_normalised(host, expected):
    parsed = parse_ip_literal(host)
    assert (str(parsed) if parsed is not None else None) == expected


@pytest.mark.parametrize("url", ["http://2130706433/", "http://0x7f.1/", "http://017700000001/offre", "http://127.1/",
                                 "http://0/", "https://0xa9.0xfe.0xa9.0xfe/latest/meta-data/", "http://[::1]/",
                                 "http://[::ffff:127.0.0.1]/", "http://[fe80::1%25eth0]/", "http://localhost/",
                                 "http://LOCALHOST./", "http://intranet.localhost/"])
def test_literal_and_local_hosts_blocked_without_resolution(url):
    resolve = resolver()
    with pytest.raises(FetchError) as info:
        check_url(url, resolve)
    assert info.value.code == "blocked_address" and resolve.seen == []


@pytest.mark.parametrize("url", ["ftp://jobs.example.fr/offre", "file:///etc/passwd", "gopher://jobs.example.fr/", "javascript:alert(1)",
                                 "//jobs.example.fr/offre", "http:///offre", "http://jobs.example.fr:8080/offre",
                                 "https://jobs.example.fr:22/", "http://user:secret@jobs.example.fr/", "http://user@jobs.example.fr/",
                                 "http://127.0.0.1\\@jobs.example.fr/", "http://0177.0.0.1/", "http://1.2.3.4.5/",
                                 "http://%31%32%37.0.0.1/", "http://exa mple.fr/"])
def test_bad_urls_rejected(url):
    with pytest.raises(FetchError) as info:
        check_url(url, resolver())
    assert info.value.code == "bad_url"


def test_ports_80_and_443_only_explicit_or_default():
    for url in ("http://jobs.example.fr/", "http://jobs.example.fr:80/", "https://jobs.example.fr:443/", "https://jobs.example.fr:80/"):
        assert check_url(url, resolver()).host == "jobs.example.fr"


def test_every_resolved_address_must_be_public():
    mixed = resolver({"mix.example.fr": [PUBLIC_IP, "10.0.0.7"], "meta.example.fr": ["169.254.169.254"],
                      "v6.example.fr": ["2606:4700:4700::1111", "fd00::5"]})
    for host in ("mix.example.fr", "meta.example.fr", "v6.example.fr"):
        with pytest.raises(FetchError) as info:
            check_url(f"https://{host}/offre", mixed)
        assert info.value.code == "blocked_address"
    with pytest.raises(FetchError) as info:
        check_url("https://inconnu.example.fr/", resolver(default=None))
    assert info.value.code == "bad_url"
    resolve = resolver()
    check_url("https://Jobs.Example.FR/offre", resolve)
    assert resolve.seen == [("jobs.example.fr", 443)]


# ── Lecture ─────────────────────────────────────────────────────────────────
def test_safe_get_sends_clear_user_agent_and_ignores_env_proxies(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, html="<p>ok</p>")

    page = safe_get("https://jobs.example.fr/offre", resolver=resolver(), transport=httpx.MockTransport(handler))
    assert page.status == 200 and page.body == b"<p>ok</p>" and page.mime == "text/html" and page.charset == "utf-8"
    assert seen["user-agent"] == "PAI/1.0 (usage personnel ; lecture d'une offre a la demande de l'utilisateur)"
    assert USER_AGENT.replace("à", "a") == seen["user-agent"] and seen["accept-encoding"] == "gzip, deflate"


def test_redirects_are_followed_manually_and_revalidated():
    def handler(request):
        return {"/a": httpx.Response(302, headers={"Location": "/b"}),
                "/b": httpx.Response(301, headers={"Location": "https://autre.example.fr/c"}),
                }.get(request.url.path, httpx.Response(200, text="fin"))

    resolve = resolver()
    page = safe_get("http://jobs.example.fr/a", resolver=resolve, transport=httpx.MockTransport(handler))
    assert page.final_url == "https://autre.example.fr/c" and page.url == "http://jobs.example.fr/a" and page.body == b"fin"
    assert resolve.seen == [("jobs.example.fr", 80), ("jobs.example.fr", 80), ("autre.example.fr", 443)]


@pytest.mark.parametrize("location, code", [("http://127.0.0.1/admin", "blocked_address"), ("http://169.254.169.254/latest/", "blocked_address"),
                                            ("http://2130706433/", "blocked_address"), ("https://interne.example.fr/", "blocked_address"),
                                            ("ftp://jobs.example.fr/x", "bad_url"), ("http://jobs.example.fr:8080/x", "bad_url"),
                                            ("http://user:pw@jobs.example.fr/", "bad_url")])
def test_redirect_to_forbidden_target_is_refused_before_request(location, code):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": location})

    resolve = resolver({"interne.example.fr": ["192.168.0.10"]})
    assert fetch_code("https://jobs.example.fr/offre", handler, resolve=resolve) == code
    assert calls == ["https://jobs.example.fr/offre"]  # la cible interdite n'est jamais demandée


def test_too_many_redirects():
    def loop(request):
        return httpx.Response(302, headers={"Location": f"/r{int(request.url.path[2:] or 0) + 1}"})

    assert fetch_code("https://jobs.example.fr/r0", loop) == "http_error"
    assert fetch_code("https://jobs.example.fr/r0", loop, max_redirects=0) == "http_error"


def test_body_size_is_capped_streaming_declared_and_compressed():
    class Exploding(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("le corps ne doit pas être lu")

    def handler(request):
        if request.url.path == "/declared":
            return httpx.Response(200, headers={"Content-Length": "5000000"}, stream=Exploding())
        if request.url.path == "/chunked":
            return httpx.Response(200, content=iter([b"x" * 10_000] * 40))
        if request.url.path == "/bomb":  # 10 Mo de zéros, ~10 ko compressés : décompression bornée
            return httpx.Response(200, content=iter([gzip.compress(b"\0" * 10_000_000)]), headers={"Content-Encoding": "gzip"})
        return httpx.Response(200, content=iter([gzip.compress("<p>Offre compressée</p>".encode())]),
                              headers={"Content-Encoding": "gzip", "Content-Type": "text/html; charset=utf-8"})

    for path in ("/declared", "/chunked", "/bomb"):
        assert fetch_code(f"https://jobs.example.fr{path}", handler, max_bytes=100_000) == "too_large", path
    page = safe_get("https://jobs.example.fr/ok", resolver=resolver(), transport=httpx.MockTransport(handler))
    assert page.body.decode("utf-8") == "<p>Offre compressée</p>"


def test_timeouts_and_http_errors():
    def handler(request):
        path = request.url.path
        if path == "/lent":
            raise httpx.ReadTimeout("lent", request=request)
        if path == "/injoignable":
            raise httpx.ConnectError("refus", request=request)
        return httpx.Response(int(path[1:]))

    assert fetch_code("https://jobs.example.fr/lent", handler) == "timeout"
    assert fetch_code("https://jobs.example.fr/injoignable", handler) == "http_error"
    expected = {401: "auth_required", 403: "forbidden", 404: "not_found", 410: "not_found", 429: "rate_limited",
                500: "unavailable", 503: "unavailable", 418: "http_error"}
    for status, code in expected.items():
        assert fetch_code(f"https://jobs.example.fr/{status}", handler) == code
    with pytest.raises(FetchError) as info:
        safe_get("https://jobs.example.fr/404", resolver=resolver(), transport=httpx.MockTransport(handler))
    assert "HTTP 404" in info.value.message and "collez le texte" in info.value.message
    assert info.value.message.startswith("Le serveur PAI n'a pas pu récupérer cette URL") and "Claude" not in info.value.message


def test_anti_bot_protection_is_named():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cloudflare":
            return httpx.Response(403, headers={"cf-mitigated": "challenge", "server": "cloudflare"})
        return httpx.Response(403, headers={"x-datadome": "protected"})

    assert fetch_code("https://jobs.example.fr/cloudflare", handler) == "anti_bot"
    assert fetch_code("https://jobs.example.fr/datadome", handler) == "anti_bot"


def test_single_deadline_covers_redirects_and_slow_bodies():
    import time

    def slow_chunks():
        for _ in range(10):
            time.sleep(0.03)
            yield b"<p>morceau</p>"

    def handler(request):
        if request.url.path == "/redirige-lentement":
            time.sleep(0.12)
            return httpx.Response(302, headers={"Location": "/fin"})
        if request.url.path == "/goutte-a-goutte":
            return httpx.Response(200, content=slow_chunks())
        return httpx.Response(200, text="fin")

    assert fetch_code("https://jobs.example.fr/redirige-lentement", handler, timeout=0.1) == "timeout"
    assert fetch_code("https://jobs.example.fr/goutte-a-goutte", handler, timeout=0.1) == "timeout"


class FakeNetworkStream:
    def __init__(self, server_addr):
        self.server_addr = server_addr

    def get_extra_info(self, info):
        return self.server_addr if info == "server_addr" else None


@pytest.mark.parametrize("peer, ok", [(("10.0.0.5", 443), False), (("127.0.0.1", 443), False), (("::1", 443, 0, 0), False),
                                      ((PUBLIC_IP, 443), True), (None, True)])
def test_connected_peer_is_rechecked_dns_rebinding(peer, ok):
    def handler(request):
        return httpx.Response(200, text="page", extensions={"network_stream": FakeNetworkStream(peer)})

    if ok:
        assert safe_get("https://jobs.example.fr/", resolver=resolver(), transport=httpx.MockTransport(handler)).body == b"page"
    else:
        assert fetch_code("https://jobs.example.fr/", handler) == "blocked_address"


def test_dns_rebinding_blocked_with_real_transport():
    """Vrai transport httpx/httpcore : le contrôle voit une IP publique, la connexion aboutit sur 127.0.0.1."""
    httpcore = pytest.importorskip("httpcore")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"<main>donnees internes</main>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # noqa: ANN002
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class Rebinding(httpcore.SyncBackend):
        def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # noqa: ARG002
            return super().connect_tcp("127.0.0.1", server.server_address[1], timeout, local_address, socket_options)

    transport = httpx.HTTPTransport()
    if not hasattr(transport, "_pool"):
        pytest.skip("structure interne de httpx différente")
    transport._pool = httpcore.ConnectionPool(network_backend=Rebinding())
    try:
        with pytest.raises(FetchError) as info:
            safe_get("http://offres.example.fr/", resolver=resolver(), transport=transport)
        assert info.value.code == "blocked_address"
    finally:
        server.shutdown()
        transport.close()


# ── Offre depuis une URL ─────────────────────────────────────────────────────
DESCRIPTION = ("&lt;p&gt;Acme SaaS édite un logiciel pour les PME françaises. Nous recrutons un "
               "&lt;strong&gt;Business Developer&lt;/strong&gt; pour accélérer notre croissance.&lt;/p&gt;"
               "&lt;ul&gt;&lt;li&gt;Prospecter de nouveaux clients PME&lt;/li&gt;&lt;li&gt;&lt;p&gt;Suivre le pipeline dans HubSpot&lt;/p&gt;&lt;/li&gt;&lt;/ul&gt;"
               "&lt;p&gt;Anglais courant requis.&lt;br&gt;Poste à pourvoir immédiatement.&lt;/p&gt;")
POSTING = {"@context": "https://schema.org", "@type": ["JobPosting"], "title": "Business Developer Junior (H/F)",
           "hiringOrganization": {"@type": "Organization", "name": "Acme SaaS"},
           "jobLocation": [{"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": "Paris", "postalCode": "75009",
                                                          "addressCountry": {"@type": "Country", "name": "FR"}}}],
           "employmentType": ["FULL_TIME", "CDI"], "datePosted": "2026-09-20T08:00:00+02:00", "description": DESCRIPTION,
           "baseSalary": {"@type": "MonetaryAmount", "currency": "EUR",
                          "value": {"@type": "QuantitativeValue", "minValue": 40000, "maxValue": 45000, "unitText": "YEAR"}}}
FALLBACK_TEXT = ("Commercial terrain (H/F) — Lyon. Nous cherchons un commercial terrain pour la région lyonnaise : "
                 "permis B indispensable, CDI, 35 k€ fixe + variable.")


def page(ld: object | None = None, main: str = "") -> str:
    script = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>' if ld is not None else ""
    return (f"<html><head><title>Titre de la page</title>{script}</head><body><nav>Menu Connexion</nav>"
            f"<main>{main}</main><footer>Mentions légales</footer></body></html>")


def site(pages: dict[str, httpx.Response]):
    return httpx.MockTransport(lambda request: pages.get(request.url.path, httpx.Response(404)))


def read(path: str, pages: dict[str, httpx.Response]):
    return offer_from_url(f"https://jobs.example.fr{path}", transport=site(pages), resolver=resolver())


def test_jsonld_jobposting_builds_clean_offer_text():
    graph = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "name": "Carrières"}, POSTING]}
    for ld in (graph, [{"@type": "Organization", "name": "Acme"}, POSTING], {"@type": "WebPage", "mainEntity": POSTING}):
        offer = read("/offre", {"/offre": httpx.Response(200, html=page(ld, main="<p>Texte de la page</p>"))})
        lines = offer.text.splitlines()
        assert lines[:6] == ["Business Developer Junior (H/F)", "Entreprise : Acme SaaS", "Lieu : Paris (75009), FR",
                             "Contrat : Temps plein, CDI", "Salaire : 40 000 – 45 000 EUR par an", "Publiée le : 2026-09-20"]
        assert "- Prospecter de nouveaux clients PME\n- Suivre le pipeline dans HubSpot" in offer.text
        assert "<" not in offer.text and "&lt;" not in offer.text and "Menu Connexion" not in offer.text
        assert offer.title_hint == "Business Developer Junior (H/F)" and offer.company_hint == "Acme SaaS"
        assert offer.source_type == "url" and offer.source_url == "https://jobs.example.fr/offre"
        assert offer.id.startswith("off_") and len(offer.text_hash) == 16


def test_page_text_fallback_when_no_or_thin_jsonld():
    thin = dict(POSTING, description="<p>Voir l'annonce.</p>")
    for ld in (None, thin):
        offer = read("/o", {"/o": httpx.Response(200, html=page(ld, main=f"<h1>Commercial terrain</h1><p>{FALLBACK_TEXT}</p>"))})
        assert FALLBACK_TEXT in offer.text and offer.title_hint == "Titre de la page"
        assert "Menu Connexion" not in offer.text and "Mentions légales" not in offer.text and "Salaire" not in offer.text


def test_plain_text_and_bogus_charsets_are_tolerated():
    body = FALLBACK_TEXT.encode("utf-8")
    for content_type in ("text/plain; charset=utf-8x", "text/html; charset=inconnu"):
        offer = read("/texte", {"/texte": httpx.Response(200, content=body, headers={"Content-Type": content_type})})
        assert FALLBACK_TEXT in offer.text and offer.source_type == "url"


def test_unreadable_page_is_explicit_and_never_invented():
    spa = '<html><body><div id="app"></div><script>window.render()</script></body></html>'
    for body, code in ((spa, "js_required"), (page(dict(POSTING, description=""), main="Chargement…"), "unreadable")):
        with pytest.raises(UrlIngestError) as info:
            read("/spa", {"/spa": httpx.Response(200, html=body)})
        assert info.value.code == code and "collez le texte" in info.value.message and "PDF" in info.value.message
    with pytest.raises(UrlIngestError) as info:
        read("/img", {"/img": httpx.Response(200, content=b"\x89PNG\r\n", headers={"Content-Type": "image/png"})})
    assert info.value.code == "unreadable"


def _pdf(text: str) -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((56, 72), text, fontsize=11)
    return doc.tobytes()


def test_pdf_response_detected_by_type_or_magic():
    pdf = _pdf("Chargé de recrutement (H/F) - CDD 12 mois - Paris\nCabinet Talentis recrute un chargé de recrutement.\n"
               "Sourcing, entretiens et suivi des candidats dans l'ATS.")
    pages = {"/offre.pdf": httpx.Response(200, content=pdf, headers={"Content-Type": "application/pdf"}),
             "/telecharger": httpx.Response(200, content=pdf, headers={"Content-Type": "application/octet-stream"})}
    by_type, by_magic = read("/offre.pdf", pages), read("/telecharger", pages)
    for offer in (by_type, by_magic):
        assert "Cabinet Talentis recrute" in offer.text and offer.source_type == "pdf"
    assert by_type.title_hint == "offre" and by_type.source_url == "https://jobs.example.fr/offre.pdf" and by_magic.title_hint == ""
    with pytest.raises(UrlIngestError) as info:
        read("/vide.pdf", {"/vide.pdf": httpx.Response(200, content=b"%PDF-1.7 illisible", headers={"Content-Type": "application/pdf"})})
    assert info.value.code == "unreadable"


@pytest.mark.parametrize("url", ["https://www.linkedin.com/jobs/view/4242", "https://fr.linkedin.com/jobs/view/1",
                                 "https://lnkd.in/abc", "https://fr.indeed.com/viewjob?jk=1", "https://www.indeed.fr/emplois",
                                 "https://www.glassdoor.fr/Emploi/x.htm", "HTTPS://WWW.LINKEDIN.COM/jobs/"])
def test_login_walled_sites_refused_before_any_network_call(url):
    def failing_resolver(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("aucune résolution DNS attendue")

    with pytest.raises(UrlIngestError) as info:
        offer_from_url(url, transport=httpx.MockTransport(no_network), resolver=failing_resolver)
    assert info.value.code == "login_walled" and isinstance(info.value, IngestError)
    assert "collez le texte de l'offre ou importez le PDF" in info.value.message


def test_redirect_to_login_walled_site_is_refused_before_request():
    requested: list[str] = []

    def short_link(request):
        requested.append(request.url.host)
        return httpx.Response(301, headers={"Location": "https://www.linkedin.com/jobs/view/4242"})

    resolve = resolver()
    with pytest.raises(UrlIngestError) as info:
        offer_from_url("https://lien.example.fr/abc", transport=httpx.MockTransport(short_link), resolver=resolve)
    assert info.value.code == "login_walled"
    assert requested == ["lien.example.fr"] and [host for host, _ in resolve.seen] == ["lien.example.fr"]


def test_login_walled_detection_uses_the_host_only():
    assert is_login_walled("https://www.linkedin.com/jobs") and is_login_walled("https://emplois.indeed.com/x")
    assert not is_login_walled("https://jobs.example.fr/offre?ref=linkedin.com")
    assert not is_login_walled("https://www.welcometothejungle.com/fr/jobs")


def test_fetch_errors_become_coded_ingest_errors():
    with pytest.raises(UrlIngestError) as info:
        offer_from_url("http://192.168.1.1/offre", transport=httpx.MockTransport(no_network), resolver=resolver())
    assert info.value.code == "blocked_address" and isinstance(info.value, IngestError) and str(info.value) == info.value.message


def test_html_to_text_keeps_structure():
    assert html_to_text("<h2>Missions</h2><ul><li>Prospecter</li><li><b>Négocier</b> avec les décideurs</li></ul><p>A<br>B</p>") == \
        "Missions\n\n- Prospecter\n- Négocier avec les décideurs\n\nA\nB"
    assert html_to_text(None) == "" and html_to_text("&lt;p&gt;Échappé&lt;/p&gt;") == "Échappé"


# ── Route /v1/ingest/url ─────────────────────────────────────────────────────
@pytest.fixture()
def fake_web(monkeypatch):
    """La route lit le « web » simulé : MockTransport + résolveur factice (aucun accès Internet)."""
    pages = {"/offre": httpx.Response(200, html=page({"@graph": [POSTING]})),
             "/absente": httpx.Response(404),
             "/lente": None, "/enorme": httpx.Response(200, content=iter([b"x" * 1_000_000] * 4)),
             "/vide": httpx.Response(200, html="<html><body><script>app()</script></body></html>")}

    def handler(request):
        if request.url.path == "/lente":
            raise httpx.ReadTimeout("lent", request=request)
        return pages.get(request.url.path) or httpx.Response(404)

    patched = functools.partial(ingest.offer_from_url, transport=httpx.MockTransport(handler),
                                resolver=resolver({"interne.example.fr": ["10.1.2.3"]}))
    monkeypatch.setattr("pai.api.v1.offer_from_url", patched)


def test_ingest_url_endpoint_returns_offer(client, fake_web):
    r = client.post("/v1/ingest/url", json={"url": "https://jobs.example.fr/offre"}, headers=api_key("analyze"))
    assert r.status_code == 200, r.text
    offer = r.json()["offer"]
    assert set(offer) == {"id", "text", "title_hint", "company_hint", "source_url", "text_hash", "source_type"}
    assert offer["title_hint"] == "Business Developer Junior (H/F)" and offer["company_hint"] == "Acme SaaS"
    assert offer["source_type"] == "url" and offer["source_url"] == "https://jobs.example.fr/offre"
    assert offer["text"].startswith("Business Developer Junior (H/F)\nEntreprise : Acme SaaS")
    analysis = client.post("/v1/analyze-job", json={"offer_text": offer["text"], "offer_url": offer["source_url"],
                                                    "role": offer["title_hint"], "company": offer["company_hint"]},
                           headers=api_key("analyze"))  # parcours de l'interface : URL → texte relu → analyse
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["analysis"]["company"] == "Acme SaaS" and analysis.json()["analysis"]["contract"] == "CDI"


@pytest.mark.parametrize("url, code", [
    ("https://www.linkedin.com/jobs/view/1", "login_walled"), ("ftp://jobs.example.fr/offre", "bad_url"),
    ("http://jobs.example.fr:8443/offre", "bad_url"), ("http://127.0.0.1/admin", "blocked_address"),
    ("http://2130706433/", "blocked_address"), ("https://interne.example.fr/offre", "blocked_address"),
    ("https://jobs.example.fr/absente", "not_found"), ("https://jobs.example.fr/lente", "timeout"),
    ("https://jobs.example.fr/enorme", "too_large"), ("https://jobs.example.fr/vide", "unreadable")])
def test_ingest_url_endpoint_error_codes(client, fake_web, url, code):
    r = client.post("/v1/ingest/url", json={"url": url}, headers=api_key("analyze"))
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == code and isinstance(detail["message"], str) and detail["message"]


def test_ingest_url_endpoint_auth_and_validation(client, fake_web):
    body = {"url": "https://jobs.example.fr/offre"}
    assert "post" in client.get("/openapi.json", headers=api_key("read")).json()["paths"]["/v1/ingest/url"]
    assert client.post("/v1/ingest/url", json=body).status_code == 401
    assert client.post("/v1/ingest/url", json=body, headers=api_key("read")).status_code == 403
    assert client.post("/v1/ingest/url", json={"url": ""}, headers=api_key("analyze")).status_code == 422
    assert client.post("/v1/ingest/url", json={"url": "x" * 2001}, headers=api_key("analyze")).status_code == 422
    login(client)  # parcours de l'interface : cookie de session + jeton CSRF
    assert client.post("/v1/ingest/url", json=body).status_code == 403
    r = client.post("/v1/ingest/url", json=body, headers={"X-CSRF-Token": session_csrf(client)})
    assert r.status_code == 200 and r.json()["offer"]["company_hint"] == "Acme SaaS"
