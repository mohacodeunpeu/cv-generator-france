/* PAI — application (interface, stockage privé, IA, PDF). Les règles de vérité sont appliquées par PAIEngine
 * (engine.js) : chaque ligne générée est liée à des faits et validée ; ce qui ne peut pas être prouvé est
 * réécrit puis supprimé. Les gabarits PDF (designs.js) ne font que la mise en page. */
const E = window.PAIEngine;
const DS = window.PAIDesigns;
const D = window.PAI_DATA;
E.setData(D);
const SERVER = window.PAI_SERVER === true;

// ─── Utilitaires ─────────────────────────────────────────────────────────────
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clone = (o) => JSON.parse(JSON.stringify(o));
const nowIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
const uid = (p) => `${p}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const fmtDate = (iso) => { try { return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }); } catch (e) { return iso || ''; } };
const fmtTime = (iso) => { try { return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return iso || ''; } };
const pct = (v) => (v === null || v === undefined || Number.isNaN(v) ? '—' : `${Math.round(v)}`);
const clamp = (v, a = 0, b = 100) => Math.max(a, Math.min(b, Number(v) || 0));
const lsGet = (k, d) => { try { const v = localStorage.getItem(`pai.${k}`); return v === null ? d : JSON.parse(v); } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(`pai.${k}`, JSON.stringify(v)); } catch (e) { /* stockage navigateur indisponible */ } };
const tone = (v, good = 75, warn = 55) => (v >= good ? 'good' : v >= warn ? 'warn' : 'bad');
const slug = (t) => String(t || 'pack').normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_|_$/g, '').slice(0, 30) || 'pack';
const firstName = (n) => String(n || '').trim().split(/\s+/)[0] || '';
const STATUS_TONE = { CONFIRMED: 'good', IMPORTED: 'accent', INFERRED: 'warn', UNVERIFIED: 'warn', FORBIDDEN: 'bad' };
const STATUS_LABEL = { CONFIRMED: 'Validé', IMPORTED: 'Importé', INFERRED: 'Déduit', UNVERIFIED: 'À vérifier', FORBIDDEN: 'Interdit' };
const KIND_LABEL = { identity: 'Identité', contact: 'Contact', target: 'Cibles', summary: 'Synthèse', availability: 'Disponibilité', mobility: 'Mobilité',
  education: 'Formation', certification: 'Certifications', language: 'Langues', experience: 'Expériences', responsibility: 'Responsabilités',
  result: 'Résultats', skill: 'Compétences', tool: 'Outils', soft_skill: 'Savoir-être', preference: 'Préférences', media: 'Médias', other: 'Autres' };
const KIND_ORDER = Object.keys(KIND_LABEL);
const UNK = { company: 'Entreprise non précisée', location: 'Lieu non précisé', contract: 'Contrat non précisé' };
const disp = (v, k) => (!v || v === 'UNKNOWN' ? UNK[k] : v);
const DESIGN_NAME = (id) => (D.designs[DS.familyOf(id)] || {}).name || id;

// ─── État ────────────────────────────────────────────────────────────────────
const S = {
  ready: false, caps: { db: null, sample: null, downloads: null, user: null }, storage: 'pending', ai: 'pending', aiLimits: null,
  profile: null, profileVersions: [], packs: [], feedback: [], arena: [], rules: { accepted: [], proposals: [] }, jobagent: [], bench: null, benchPairs: [], documents: [],
  photo: null, photoAssets: null, prefs: {}, server: { status: null, ai: null, aiLoaded: false, aiTest: {} },
  view: 'accueil', packId: lsGet('packId', null), packTab: 'overview', cvIndex: null, compareWith: null, previewMode: 'pdf', letterMode: 'pdf',
  draft: { input: '', offer: '', title: '', company: '', questions: '', mode: lsGet('mode', 'STANDARD'), sourceType: 'text', sourceUrl: '', showMore: false, notice: null, busy: false, synthetic: false },
  run: null, toast: null, arenaPair: null, chat: { turns: [], busy: false }, jobImport: null, editFact: null, calls: [], moreOpen: false,
  profileFilter: 'all', onboard: null, lab: { packId: null, rate: undefined, reasons: [] }, fbRate: undefined, fbReasons: [], themeChoice: lsGet('theme', 'system'),
};

const NAV_MAIN = [['accueil', 'Accueil', 'i-home'], ['analyser', 'Analyser', 'i-spark'], ['studio', 'CV Studio', 'i-layout'], ['packs', 'Application Packs', 'i-stack'], ['lab', 'Training Lab', 'i-flask'], ['learning', 'Learning', 'i-bulb']];
const NAV_SECOND = [['benchmark', 'Benchmark', 'i-scale'], ['profil', 'Profil', 'i-user'], ['versions', 'Versions', 'i-history'], ['reglages', 'Réglages', 'i-sliders']];
const TABS = [['accueil', 'Accueil', 'i-home'], ['analyser', 'Analyser', 'i-spark'], ['studio', 'Studio', 'i-layout'], ['packs', 'Packs', 'i-stack'], ['more', 'Plus', 'i-more']];
const ALIASES = { nouvelle: 'analyser', apprentissage: 'learning', arene: 'benchmark', jobagent: 'learning', plus: 'accueil' };
const VIEW_TITLE = Object.fromEntries(NAV_MAIN.concat(NAV_SECOND).map(([k, l]) => [k, l]).concat([['pack', 'Application Pack']]));

let renderQueued = false;
const render = () => { if (renderQueued) return; renderQueued = true; requestAnimationFrame(() => { renderQueued = false; doRender(); }); };
const toast = (msg, ic) => { S.toast = { msg, ic: ic || 'i-info' }; renderToast(); clearTimeout(toast.t); toast.t = setTimeout(() => { S.toast = null; renderToast(); }, 4200); };

// ─── Profil (vue enrichie) ───────────────────────────────────────────────────
const Pp = () => (S.profile ? E.P(S.profile) : null);
const profileTag = (p) => `v${p.version}-${E.hash(p.facts.map((f) => [f.id, f.text, f.status]))}${p.validated ? '' : '-draft'}`;
const conflicts = (p) => (p && p.review_queue || []).filter((r) => r.severity === 'conflict');

// ─── Stockage (capacité db sur claude.ai, /v1/store sur le serveur, sinon mémoire) ──
const Store = {
  db: null,
  subscribe(db) {
    this.db = db; S.storage = 'db';
    const err = (what) => (e) => { console.warn(what, e); if (e && e.code === 'revoked') { S.storage = 'memory'; render(); } };
    db.doc('pai/profile').onSnapshot((s) => { S.profile = s.exists ? s.data() : null; render(); }, err('profile'));
    db.doc('pai/rules').onSnapshot((s) => { S.rules = s.exists ? Object.assign({ accepted: [], proposals: [] }, s.data()) : { accepted: [], proposals: [] }; render(); }, err('rules'));
    db.doc('pai/prefs').onSnapshot((s) => { S.prefs = s.exists ? s.data() || {} : {}; render(); }, err('prefs'));
    db.doc('pai/photo').onSnapshot((s) => { S.photo = s.exists ? s.data() : null; Photo.refresh(); }, err('photo'));
    db.doc('bench/summary').onSnapshot((s) => { S.bench = s.exists ? s.data() : null; render(); }, err('bench'));
    db.collection('packs').orderBy('created_at', 'desc').limit(200).onSnapshot((q) => { S.packs = q.docs.map((d) => d.data()).filter((p) => !p.deleted_at); render(); }, err('packs'));
    db.collection('feedback').orderBy('created_at', 'desc').limit(1000).onSnapshot((q) => { S.feedback = q.docs.map((d) => d.data()); render(); }, err('feedback'));
    db.collection('arena').orderBy('created_at', 'desc').limit(500).onSnapshot((q) => { S.arena = q.docs.map((d) => d.data()); render(); }, err('arena'));
    db.collection('profile_versions').orderBy('version', 'desc').limit(60).onSnapshot((q) => { S.profileVersions = q.docs.map((d) => d.data()); render(); }, err('versions'));
    db.collection('jobagent').orderBy('created_at', 'desc').limit(500).onSnapshot((q) => { S.jobagent = q.docs.map((d) => d.data()); render(); }, err('jobagent'));
    db.collection('documents').orderBy('created_at', 'desc').limit(50).onSnapshot((q) => { S.documents = q.docs.map((d) => d.data()); render(); }, err('documents'));
    db.collection('bench_pairs').limit(100).onSnapshot((q) => { S.benchPairs = q.docs.map((d) => d.data()); render(); }, err('bench_pairs'));
  },
  memory() { S.storage = 'memory'; },
  async put(path, data) {
    if (!this.db) return;
    try { await this.db.doc(path).set(data); } catch (e) {
      if (e && e.code === 'quota_exceeded') toast('Base pleine : supprime d\'anciens packs dans Réglages.', 'i-alert');
      else toast(`Enregistrement impossible (${(e && e.code) || 'erreur'}).`, 'i-alert');
      throw e;
    }
  },
  async del(path) { if (this.db) await this.db.doc(path).delete(); },
  async saveProfile(p, action, detail) {
    const next = clone(p);
    next.history = (next.history || []).concat([{ at: nowIso(), action, detail: detail || '' }]).slice(-200);
    if (!this.db) { S.profile = next; render(); return next; }
    await this.put('pai/profile', next);
    return next;
  },
  async savePack(pack) {
    const body = fitPack(clone(pack));
    if (!this.db) { const i = S.packs.findIndex((x) => x.id === body.id); if (i >= 0) S.packs[i] = body; else S.packs.unshift(body); render(); return body; }
    await this.put(`packs/${body.id}`, body);
    return body;
  },
  async addDoc(coll, doc) {
    if (!this.db) { const key = { feedback: 'feedback', arena: 'arena', jobagent: 'jobagent', documents: 'documents' }[coll]; if (key) S[key].unshift(doc); render(); return; }
    await this.put(`${coll}/${doc.id}`, doc);
  },
  async saveRules(r) { if (!this.db) { S.rules = r; render(); return; } await this.put('pai/rules', r); },
  async savePrefs(p) { if (!this.db) { S.prefs = p; render(); return; } await this.put('pai/prefs', p); },
  async savePhoto(p) { if (!this.db) { S.photo = p; await Photo.refresh(); return; } if (p) await this.put('pai/photo', p); else await this.del('pai/photo'); },
};

// Un document stocké fait au plus 256 Kio (claude.ai comme serveur PAI). Un pack qui grossit (versions) est allégé
// dans cet ordre : rapports détaillés des versions non retenues résumés, versions intermédiaires retirées
// (V1 et la version retenue sont toujours gardées), journaux raccourcis, texte de l'offre tronqué.
const DOC_LIMIT = 230 * 1024;
const docBytes = (o) => new TextEncoder().encode(JSON.stringify(o)).length;
function slimEntry(e) {
  if (!e || (e.report && e.report.slim)) return;
  const r = e.report || {};
  e.report = { factuality: r.factuality, traced: r.traced, total: r.total, perfect: r.perfect, rejected_ids: r.rejected_ids || [], forbidden_hits: r.forbidden_hits || 0, warnings: (r.warnings || []).slice(0, 5), slim: true };
  if (e.critique) {
    const c = e.critique; const det = c.deterministic;
    e.critique = { deterministic: det ? { issues: (det.issues || []).slice(0, 8), major_gaps: det.major_gaps || [] } : null, ai: c.ai && c.ai.scores ? { scores: c.ai.scores } : null, cycles: c.cycles, slim: true };
  }
}
function fitPack(body) {
  if (body.offer && body.offer.text && body.offer.text.length > 30000) body.offer.text = body.offer.text.slice(0, 30000);
  if (docBytes(body) <= DOC_LIMIT) return body;
  (body.cvs || []).forEach((c, i) => { if (i !== body.cv_index) slimEntry(c); });
  (body.letters || []).forEach((l, i) => { if (i !== body.letter_index) slimEntry(l); });
  body.log = (body.log || []).slice(-60); body.calls = (body.calls || []).slice(-60);
  while (docBytes(body) > DOC_LIMIT && (body.cvs || []).length > 3) {
    const keep = new Set([0, body.cv_index, body.cvs.length - 1]);
    const drop = body.cvs.findIndex((_, i) => !keep.has(i)); if (drop < 0) break;
    const sel = body.cvs[body.cv_index]; body.cvs.splice(drop, 1); body.cv_index = Math.max(0, body.cvs.indexOf(sel));
    body.trimmed_versions = (body.trimmed_versions || 0) + 1;
  }
  while (docBytes(body) > DOC_LIMIT && (body.letters || []).length > 2) {
    const sel = body.letters[body.letter_index]; const drop = body.letters.findIndex((l, i) => i !== 0 && i !== body.letter_index); if (drop < 0) break;
    body.letters.splice(drop, 1); body.letter_index = Math.max(0, body.letters.indexOf(sel));
  }
  if (docBytes(body) > DOC_LIMIT && body.offer) body.offer.text = body.offer.text.slice(0, 12000);
  if (docBytes(body) > DOC_LIMIT) { slimEntry(body.cvs[body.cv_index]); if (body.letters[body.letter_index]) slimEntry(body.letters[body.letter_index]); }
  return body;
}

// ─── IA : capacité sample (claude.ai) ou fournisseur du serveur ───────────────
const AI_DENIED = ['not_granted', 'sampling_disabled', 'not_declared', 'capability_disabled', 'capability_removed'];
const PROVIDER_LABEL = { claude: 'Claude (Anthropic)', gemini: 'Gemini (Google)', mistral: 'Mistral AI', openai: 'OpenAI ou compatible', local: 'IA locale (Ollama…)', null: 'Désactivé (sans IA)' };
const PROVIDER_SHORT = { claude: 'Claude', gemini: 'Gemini', mistral: 'Mistral', openai: 'OpenAI', local: "L'IA locale", null: "L'IA" };
const AI = {
  ok: () => !!S.caps.sample && S.ai !== 'denied' && !(SERVER && S.server.status && S.server.status.ai_mode === 'DEGRADED'),
  mode: () => (!AI.ok() ? 'DEGRADED' : SERVER ? ((S.server.status && S.server.status.ai_mode) || 'REMOTE') : 'REMOTE'),
  provider: () => (SERVER ? ((S.server.status && S.server.status.active_provider) || '') : 'claude'),
  label: () => (SERVER ? `${PROVIDER_LABEL[AI.provider()] || 'IA du serveur'} (serveur PAI)` : 'Claude (claude.ai)'),
  short: () => (SERVER ? (PROVIDER_SHORT[AI.provider()] || "L'IA") : 'Claude'),
  async ask(task, vars, opts = {}) {
    if (!AI.ok()) { const e = new Error('IA indisponible'); e.code = 'unavailable'; throw e; }
    const prompt = E.render(task, vars);
    const tier = opts.tier || E.tierFor(task);
    const t0 = performance.now();
    const rec = { task, tier, at: nowIso(), ms: 0, ok: false, code: '' };
    try {
      const res = await S.caps.sample.json(prompt, { modelTier: tier, signal: opts.signal, images: opts.images,
        onText: opts.onText ? ({ text }) => opts.onText(text) : undefined, cache: opts.cache === undefined ? { gcTime: 600000 } : opts.cache });
      rec.ok = true; S.ai = 'ready';
      return res;
    } catch (e) {
      rec.code = (e && e.code) || 'erreur';
      if (AI_DENIED.includes(rec.code)) { S.ai = 'denied'; render(); }
      throw e;
    } finally { rec.ms = Math.round(performance.now() - t0); S.calls.push(rec); if (CUR) CUR.calls.push(rec); }
  },
  message(e) {
    const code = (e && e.code) || '';
    return ({ not_granted: SERVER ? 'Aucun fournisseur IA configuré sur le serveur : mode dégradé (sans IA).' : "L'utilisation de Claude n'a pas été autorisée pour cette page : mode dégradé (sans IA).",
      rate_limited: 'Limite d\'utilisation ou plafond de coût atteint : réessaie plus tard.', session_expired: 'Session expirée : reconnecte-toi.',
      refused: 'L\'IA a refusé cette demande.', invalid_json: 'Réponse de l\'IA illisible : étape passée en voie déterministe.',
      prompt_too_large: 'Offre trop longue pour une seule demande : raccourcis le texte.', cancelled: 'Annulé.', upstream_error: 'Fournisseur IA en erreur : voie déterministe utilisée.',
      unavailable: 'IA indisponible : voie déterministe utilisée.' })[code] || `Erreur IA (${code || 'inconnue'}) : voie déterministe utilisée.`;
  },
};

// Appels directs à l'API du serveur PAI (mode serveur uniquement).
const Srv = {
  async req(method, url, body) { if (!SERVER || typeof window.PAI_API !== 'function') { const e = new Error('Serveur PAI indisponible'); e.code = 'no_server'; throw e; } return window.PAI_API(method, url, body); },
  async loadStatus() { if (!SERVER) return; try { S.server.status = await Srv.req('GET', '/v1/status'); } catch (e) { S.server.status = null; } render(); },
  async loadAi() { if (!SERVER) return; try { S.server.ai = await Srv.req('GET', '/v1/settings/ai'); } catch (e) { S.server.ai = null; } S.server.aiLoaded = true; render(); },
};

async function save(filename, data) {
  if (!S.caps.downloads) { toast('Téléchargement indisponible dans cette vue.', 'i-alert'); return; }
  try { await S.caps.downloads.save({ filename, data }); toast(`${filename} enregistré.`, 'i-download'); }
  catch (e) { if (e && e.code !== 'declined') toast(`Téléchargement impossible (${(e && e.code) || 'erreur'}).`, 'i-alert'); }
}

// Thème : réglage par visiteur (préférence locale, sans incidence sur les données).
function applyTheme() {
  const r = document.documentElement;
  if (S.themeChoice === 'dark' || S.themeChoice === 'light') r.setAttribute('data-theme', S.themeChoice); else r.removeAttribute('data-theme');
}
