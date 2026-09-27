/* PAI Studio — application (UI, stockage privé, IA via la capacité `sample`, PDF).
 * Les règles de vérité sont appliquées par PAIEngine (engine.js) : chaque ligne générée
 * est liée à des faits et validée ; ce qui ne peut pas être prouvé est réécrit puis supprimé.
 */
(function () {
  'use strict';
  const E = window.PAIEngine;
  const D = window.PAI_DATA;
  E.setData(D);

  // ─── Utilitaires ─────────────────────────────────────────────────────────
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const nowIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
  const uid = (p) => `${p}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  const fmtDate = (iso) => { try { return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }); } catch (e) { return iso || ''; } };
  const fmtTime = (iso) => { try { return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return iso || ''; } };
  const pct = (v) => (v === null || v === undefined || Number.isNaN(v) ? '—' : `${Math.round(v)}`);
  const lsGet = (k, d) => { try { const v = localStorage.getItem(`pai.${k}`); return v === null ? d : JSON.parse(v); } catch (e) { return d; } };
  const lsSet = (k, v) => { try { localStorage.setItem(`pai.${k}`, JSON.stringify(v)); } catch (e) { /* stockage navigateur indisponible */ } };
  const tone = (v, good = 75, warn = 55) => (v >= good ? 'good' : v >= warn ? 'warn' : 'bad');
  const STATUS_TONE = { CONFIRMED: 'good', IMPORTED: 'accent', INFERRED: 'warn', UNVERIFIED: 'warn', FORBIDDEN: 'bad' };
  const KIND_LABEL = { identity: 'Identité', contact: 'Contact', target: 'Cibles', summary: 'Synthèse', availability: 'Disponibilité', mobility: 'Mobilité',
    education: 'Formation', certification: 'Certifications', language: 'Langues', experience: 'Expériences', responsibility: 'Responsabilités',
    result: 'Résultats', skill: 'Compétences', tool: 'Outils', soft_skill: 'Savoir-être', preference: 'Préférences', media: 'Médias', other: 'Autres' };
  const KIND_ORDER = Object.keys(KIND_LABEL);

  // ─── État ───────────────────────────────────────────────────────────────
  const S = {
    ready: false, caps: { db: null, sample: null, downloads: null, user: null }, storage: 'pending', ai: 'pending', aiLimits: null,
    profile: null, profileVersions: [], packs: [], feedback: [], arena: [], rules: { accepted: [], proposals: [] }, jobagent: [], bench: null,
    view: 'accueil', packId: lsGet('packId', null), packTab: 'synthese', cvIndex: null, compareWith: null, hotLine: null,
    draft: { offer: '', title: '', company: '', questions: '', mode: lsGet('mode', 'STANDARD') },
    run: null, toast: null, arenaPair: null, chat: { turns: [], busy: false }, jobImport: null, editFact: null, calls: [],
  };
  const VIEWS = [
    ['accueil', 'Tableau de bord', 'i-home'], ['nouvelle', 'Nouvelle candidature', 'i-plus'], ['packs', 'Application Packs', 'i-stack'],
    ['lab', 'Training Lab', 'i-lab'], ['arene', 'Benchmark & Arène', 'i-scale'], ['apprentissage', 'Apprentissage', 'i-bulb'],
    ['jobagent', 'Learn from JobAgent', 'i-plug'], ['profil', 'Profil', 'i-user'], ['versions', 'Versions', 'i-history'], ['reglages', 'Réglages', 'i-sliders'],
  ];
  const TAB_VIEWS = ['accueil', 'nouvelle', 'packs', 'profil', 'plus'];

  let renderQueued = false;
  const render = () => { if (renderQueued) return; renderQueued = true; requestAnimationFrame(() => { renderQueued = false; doRender(); }); };
  const toast = (msg) => { S.toast = msg; renderToast(); clearTimeout(toast.t); toast.t = setTimeout(() => { S.toast = null; renderToast(); }, 3600); };

  // ─── Profil (vue enrichie) ───────────────────────────────────────────────
  const Pp = () => (S.profile ? E.P(S.profile) : null);
  const profileTag = (p) => `v${p.version}-${E.hash(p.facts.map((f) => [f.id, f.text, f.status]))}${p.validated ? '' : '-draft'}`;
  const conflicts = (p) => (p.review_queue || []).filter((r) => r.severity === 'conflict');

  // ─── Stockage (capacité db, sinon mémoire) ───────────────────────────────
  const Store = {
    db: null,
    subscribe(db) {
      this.db = db; S.storage = 'db';
      const err = (what) => (e) => { console.warn(what, e); if (e && e.code === 'revoked') { S.storage = 'memory'; render(); } };
      db.doc('pai/profile').onSnapshot((s) => { S.profile = s.exists ? s.data() : null; render(); }, err('profile'));
      db.doc('pai/rules').onSnapshot((s) => { S.rules = s.exists ? Object.assign({ accepted: [], proposals: [] }, s.data()) : { accepted: [], proposals: [] }; render(); }, err('rules'));
      db.doc('bench/summary').onSnapshot((s) => { S.bench = s.exists ? s.data() : null; render(); }, err('bench'));
      db.collection('packs').orderBy('created_at', 'desc').limit(200).onSnapshot((q) => { S.packs = q.docs.map((d) => d.data()).filter((p) => !p.deleted_at); render(); }, err('packs'));
      db.collection('feedback').orderBy('created_at', 'desc').limit(1000).onSnapshot((q) => { S.feedback = q.docs.map((d) => d.data()); render(); }, err('feedback'));
      db.collection('arena').orderBy('created_at', 'desc').limit(500).onSnapshot((q) => { S.arena = q.docs.map((d) => d.data()); render(); }, err('arena'));
      db.collection('profile_versions').orderBy('version', 'desc').limit(60).onSnapshot((q) => { S.profileVersions = q.docs.map((d) => d.data()); render(); }, err('versions'));
      db.collection('jobagent').orderBy('created_at', 'desc').limit(500).onSnapshot((q) => { S.jobagent = q.docs.map((d) => d.data()); render(); }, err('jobagent'));
      db.collection('bench_pairs').limit(100).onSnapshot((q) => { S.benchPairs = q.docs.map((d) => d.data()); render(); }, err('bench_pairs'));
    },
    memory() { S.storage = 'memory'; },
    async put(path, data) {
      if (!this.db) return;
      try { await this.db.doc(path).set(data); } catch (e) {
        if (e && e.code === 'quota_exceeded') toast('Base pleine : supprimez d\'anciens packs dans Réglages.');
        else toast(`Enregistrement impossible (${(e && e.code) || 'erreur'}).`);
        throw e;
      }
    },
    async saveProfile(p, action, detail) {
      const next = clone(p);
      next.history = (next.history || []).concat([{ at: nowIso(), action, detail: detail || '' }]).slice(-200);
      if (!this.db) { S.profile = next; render(); return next; }
      await this.put('pai/profile', next);
      return next;
    },
    async savePack(pack) {
      const body = clone(pack);
      if (body.offer && body.offer.text && body.offer.text.length > 30000) body.offer.text = body.offer.text.slice(0, 30000);
      if ((body.cvs || []).length > 8) body.cvs = body.cvs.slice(-8);
      if (!this.db) { const i = S.packs.findIndex((x) => x.id === body.id); if (i >= 0) S.packs[i] = body; else S.packs.unshift(body); render(); return; }
      await this.put(`packs/${body.id}`, body);
    },
    async addDoc(coll, doc) {
      if (!this.db) { const key = { feedback: 'feedback', arena: 'arena', jobagent: 'jobagent' }[coll]; if (key) S[key].unshift(doc); render(); return; }
      await this.put(`${coll}/${doc.id}`, doc);
    },
    async saveRules(r) { if (!this.db) { S.rules = r; render(); return; } await this.put('pai/rules', r); },
  };

  // ─── IA (capacité sample) ─────────────────────────────────────────────────
  const AI_DENIED = ['not_granted', 'sampling_disabled', 'not_declared', 'capability_disabled', 'capability_removed'];
  const AI = {
    ok: () => !!S.caps.sample && S.ai !== 'denied',
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
      } finally { rec.ms = Math.round(performance.now() - t0); S.calls.push(rec); if (S.run) S.run.calls.push(rec); }
    },
    message(e) {
      const code = (e && e.code) || '';
      return ({ not_granted: "L'utilisation de Claude n'a pas été autorisée pour cette page : mode dégradé (sans IA).",
        rate_limited: 'Limite d\'utilisation atteinte : réessayez dans quelques minutes.', session_expired: 'Session expirée : reconnectez-vous à claude.ai.',
        refused: 'Claude a refusé cette demande.', invalid_json: 'Réponse de Claude illisible : étape passée en voie déterministe.',
        prompt_too_large: 'Offre trop longue pour une seule demande : raccourcissez le texte.', cancelled: 'Annulé.',
        unavailable: 'IA indisponible : voie déterministe utilisée.' })[code] || `Erreur IA (${code || 'inconnue'}) : voie déterministe utilisée.`;
    },
  };

  // ─── PDF : pdfmake (génération) + pdf.js (lecture, aperçu réel, QA) ───────
  const PDF = {
    ready() { return !!(window.pdfMake && window.PAI_FONTS); },
    init() {
      if (window.pdfMake && window.PAI_FONTS) {
        window.pdfMake.vfs = window.PAI_FONTS;
        window.pdfMake.fonts = {
          Fira: { normal: 'FiraSans-Regular.ttf', bold: 'FiraSans-SemiBold.ttf', italics: 'FiraSans-Italic.ttf', bolditalics: 'FiraSans-Bold.ttf' },
          FiraMedium: { normal: 'FiraSans-Medium.ttf', bold: 'FiraSans-Bold.ttf', italics: 'FiraSans-Italic.ttf', bolditalics: 'FiraSans-Bold.ttf' },
        };
      }
      if (window.pdfjsLib) window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js'; // le worker est déjà chargé par <script> : pdf.js l'utilise sur le fil principal
    },
    colors(doc) { return Object.assign({}, E.design(doc.design_profile).colors, doc.colors || {}); },
    stamp(lang, x) {
      return { absolutePosition: { x, y: 12 }, table: { body: [[{ text: lang === 'en' ? 'DRAFT — PROFILE NOT VALIDATED' : 'BROUILLON — PROFIL NON VALIDÉ', fontSize: 7.4, bold: true, color: '#8A2B12' }]] },
        layout: { hLineColor: () => '#8A2B12', vLineColor: () => '#8A2B12', hLineWidth: () => 0.8, vLineWidth: () => 0.8, paddingLeft: () => 5, paddingRight: () => 5, paddingTop: () => 1.5, paddingBottom: () => 1.5, fillColor: () => '#FFFFFF' } };
    },
    cvDef(cv) {
      const d = E.design(cv.design_profile); const c = this.colors(cv); const pt = d.sizes_pt; const M = d.margins_mm; const mm = (v) => v * 2.8346;
      const pageW = cv.paper === 'Letter' ? 612 : 595.28; const innerW = pageW - mm(M.left) - mm(M.right);
      const heads = E.sectionLines(cv, 'headline'); const extras = E.sectionLines(cv, 'extras');
      const content = [];
      content.push({ text: cv.name, bold: true, fontSize: pt.name, color: c.ink, margin: [0, 2, 0, 0] });
      heads.forEach((l) => content.push({ text: l.text, font: 'FiraMedium', fontSize: pt.headline, color: c.accent, margin: [0, 4, 0, 0] }));
      content.push({ text: cv.contact.join('   ·   '), fontSize: pt.meta, color: c.muted, margin: [0, 6, 0, 0] });
      extras.forEach((l) => content.push({ text: l.text, font: 'FiraMedium', fontSize: pt.meta, color: c.accent2, margin: [0, 2, 0, 0] }));
      const headerH = mm(M.top) + pt.name * 1.25 + heads.length * (pt.headline * 1.3 + 4) + pt.meta * 1.4 + 6 + extras.length * (pt.meta * 1.4 + 2) + mm(5);
      const section = (title) => [{ text: title.toUpperCase(), bold: true, fontSize: pt.section + 0.6, color: c.accent, margin: [0, 12, 0, 3] },
        { canvas: [{ type: 'line', x1: 0, y1: 0, x2: innerW, y2: 0, lineWidth: 0.6, lineColor: c.rule }], margin: [0, 0, 0, 5] }];
      const gap = d.header === 'band' ? 14 : 8;
      if (d.header !== 'band') content.push({ canvas: [{ type: 'line', x1: 0, y1: 0, x2: innerW, y2: 0, lineWidth: 1.2, lineColor: c.accent }], margin: [0, 8, 0, 0] });
      const main = []; const side = [];
      const summary = E.sectionLines(cv, 'summary');
      if (summary.length) main.push(...section(cv.section_titles.summary), { text: summary.map((l) => l.text).join(' '), lineHeight: 1.25 });
      main.push(...section(cv.section_titles.experience));
      for (const b of cv.experiences) {
        const bullets = b.bullet_ids.map((id) => E.lineById(cv, id)).filter(Boolean);
        main.push({ stack: [
          { columns: [{ text: b.title, bold: true, fontSize: pt.body + 0.6, width: '*' }, { text: b.period, fontSize: pt.meta, color: c.muted, width: 'auto', alignment: 'right', margin: [0, 1, 0, 0] }], columnGap: 10 },
          { text: [{ text: b.company, font: 'FiraMedium', color: c.ink }, b.city ? ` · ${b.city}` : ''], fontSize: pt.meta, color: c.muted, margin: [0, 1, 0, 0] },
          bullets.length ? { ul: bullets.map((l) => ({ text: l.text, margin: [0, 1, 0, 1] })), type: 'square', markerColor: c.accent, margin: [4, 3, 0, 0] } : { text: '' },
        ], margin: [0, 0, 0, 7], unbreakable: true });
      }
      const target = d.layout === 'two_column' ? side : main;
      const skills = E.sectionLines(cv, 'skills');
      if (skills.length) {
        const groups = {}; skills.forEach((l) => (groups[l.group || ''] = groups[l.group || ''] || []).push(l.text));
        target.push(...section(cv.section_titles.skills));
        for (const [g, items] of Object.entries(groups)) target.push(d.layout === 'two_column'
          ? { stack: [{ text: g, bold: true }, { text: items.join(', '), margin: [0, 1, 0, 5] }] }
          : { columns: [{ text: g, bold: true, width: 64 }, { text: items.join(', '), width: '*' }], columnGap: 8, margin: [0, 0, 0, 2.5] });
      }
      for (const sec of ['education', 'certifications', 'languages']) {
        const ls = E.sectionLines(cv, sec); if (!ls.length) continue;
        target.push(...section(cv.section_titles[sec]), ...ls.map((l) => ({ text: l.text, margin: [0, 0, 0, 2] })));
      }
      if (d.layout === 'two_column') content.push({ columns: [{ stack: main, width: '*' }, { stack: side, width: 170 }], columnGap: 22, margin: [0, gap, 0, 0] });
      else content.push({ stack: main, margin: [0, gap, 0, 0] }, { stack: side });
      if (cv.draft) content.push(this.stamp(cv.language, pageW - mm(M.right) - 176));
      return {
        pageSize: cv.paper === 'Letter' ? 'LETTER' : 'A4', pageMargins: [mm(M.left), mm(M.top), mm(M.right), mm(M.bottom)],
        background: d.header === 'band' ? (page, size) => (page === 1 ? { canvas: [{ type: 'rect', x: 0, y: 0, w: size.width, h: headerH, color: c.band },
          { type: 'line', x1: 0, y1: headerH, x2: size.width, y2: headerH, lineWidth: 2.2, lineColor: c.accent }] } : null) : undefined,
        content, defaultStyle: { font: 'Fira', fontSize: pt.body, color: c.ink, lineHeight: 1.16 },
        info: { title: `CV — ${cv.name}`, author: cv.name, subject: heads.map((l) => l.text).join(' '), keywords: (cv.keywords_covered || []).join(', '), creator: 'PAI Studio' },
      };
    },
    letterDef(letter, name, contact, designId) {
      const c = Object.assign({}, E.design(designId || 'hybrid_modern').colors); const mm = (v) => v * 2.8346;
      const content = [
        { text: name, bold: true, fontSize: 15, color: c.ink },
        { text: contact.join('   ·   '), fontSize: 8.8, color: c.muted, margin: [0, 3, 0, 0] },
        { canvas: [{ type: 'line', x1: 0, y1: 0, x2: 62, y2: 0, lineWidth: 1.6, lineColor: c.accent }], margin: [0, 14, 0, 18] },
        { columns: [{ text: letter.recipient, width: '*' }, { text: letter.place_date, width: 'auto', color: c.muted }], fontSize: 9.6, margin: [0, 0, 0, 18] },
        { text: letter.subject, bold: true, margin: [0, 0, 0, 16] },
      ];
      if (letter.salutation) content.push({ text: letter.salutation, margin: [0, 0, 0, 10] });
      E.letterParagraphs(letter).forEach((p) => content.push({ text: p, margin: [0, 0, 0, 10], lineHeight: 1.3 }));
      content.push({ text: letter.signature, bold: true, margin: [0, 14, 0, 0] });
      if (letter.draft) content.push(this.stamp(letter.language, 595.28 - mm(20) - 176));
      return { pageSize: 'A4', pageMargins: [mm(20), mm(18), mm(20), mm(16)], content, defaultStyle: { font: 'Fira', fontSize: 10.4, color: c.ink, lineHeight: 1.2 },
        info: { title: `Lettre — ${name}`, author: name, creator: 'PAI Studio' } };
    },
    build(def) {
      return new Promise((resolve, reject) => {
        try { window.pdfMake.createPdf(def).getBuffer((buf) => resolve(new Uint8Array(buf))); } catch (e) { reject(e); }
      });
    },
    async open(bytes) { return window.pdfjsLib.getDocument({ data: bytes.slice(0) }).promise; },
    async inspect(bytes) {
      // Reconstitution du texte par positions (comme pdftotext / un ATS) : pas d'espace entre deux fragments contigus.
      const doc = await this.open(bytes); let text = ''; let minSize = 99; let overflow = 0;
      for (let i = 1; i <= doc.numPages; i++) {
        const page = await doc.getPage(i); const vp = page.getViewport({ scale: 1 }); const tc = await page.getTextContent();
        let lastY = null; let lastEnd = null;
        for (const it of tc.items) {
          if (!it.str) { if (it.hasEOL) { text += '\n'; lastY = null; } continue; }
          const size = Math.hypot(it.transform[0], it.transform[1]); const x = it.transform[4]; const y = it.transform[5];
          if (lastY !== null && Math.abs(y - lastY) > size * 0.5) text += '\n';
          else if (lastEnd !== null && x - lastEnd > size * 0.12) text += ' ';
          text += it.str; lastY = y; lastEnd = x + it.width;
          if (it.hasEOL) { text += '\n'; lastY = null; lastEnd = null; }
          if (it.str.trim()) { minSize = Math.min(minSize, size); if (x < 8 || x + it.width > vp.width - 8) overflow++; }
        }
        text += '\n';
      }
      return { pages: doc.numPages, text, minSize: minSize === 99 ? null : Math.round(minSize * 10) / 10, overflow, doc };
    },
    async renderInto(bytes, canvas, width) {
      const doc = await this.open(bytes); const page = await doc.getPage(1); const vp1 = page.getViewport({ scale: 1 });
      const scale = (width / vp1.width) * (window.devicePixelRatio || 1); const vp = page.getViewport({ scale });
      canvas.width = vp.width; canvas.height = vp.height; canvas.style.width = `${width}px`; canvas.style.height = `${(vp.height / vp.width) * width}px`;
      await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
      return doc.numPages;
    },
    async offerTextFromFile(file) {
      const buf = new Uint8Array(await file.arrayBuffer()); const doc = await this.open(buf); let text = '';
      for (let i = 1; i <= Math.min(doc.numPages, 6); i++) { const tc = await (await doc.getPage(i)).getTextContent(); text += tc.items.map((it) => it.str + (it.hasEOL ? '\n' : ' ')).join('') + '\n'; }
      return text.trim();
    },
    async cvFitted(cv, maxPages) {
      let doc = cv; let bytes = await this.build(this.cvDef(doc)); let info = await this.inspect(bytes); let step = 0;
      while (info.pages > maxPages && step < 3) { step++; doc = E.trimForSpace(doc, step); bytes = await this.build(this.cvDef(doc)); info = await this.inspect(bytes); }
      return { doc, bytes, info, trimSteps: step };
    },
    qa(info, cv, requiredTerms, maxPages) {
      const issues = []; const tn = E.norm(info.text);
      if (info.pages > maxPages) issues.push({ severity: 'high', check: 'pagination', detail: `${info.pages} pages (max ${maxPages})` });
      if (info.text.length < 300) issues.push({ severity: 'high', check: 'ats_extraction', detail: 'texte peu ou pas extractible' });
      let cursor = 0; let orderOk = true;
      for (const m of [cv.name, cv.section_titles.experience, cv.section_titles.education]) { const pos = tn.indexOf(E.norm(m), cursor); if (pos < 0) { orderOk = false; break; } cursor = pos + 1; }
      if (!orderOk) issues.push({ severity: 'high', check: 'ordre_lecture', detail: 'ordre de lecture ATS incohérent' });
      if (info.minSize !== null && info.minSize < 7.3) issues.push({ severity: 'medium', check: 'taille', detail: `police minimale ${info.minSize} pt` });
      if (info.overflow) issues.push({ severity: 'high', check: 'debordement', detail: `${info.overflow} segment(s) hors page` });
      const found = requiredTerms.filter((t) => E.supportedBy(t, tn));
      return { ok: !issues.some((i) => i.severity === 'high'), issues, pages: info.pages, min_font_pt: info.minSize, required_found: `${found.length}/${requiredTerms.length}`,
        required_missing: requiredTerms.filter((t) => !found.includes(t)), ats_text_chars: info.text.length };
    },
    async pngBlob(bytes) {
      const canvas = document.createElement('canvas'); await this.renderInto(bytes, canvas, 900);
      return new Promise((res) => canvas.toBlob((b) => res(b), 'image/png'));
    },
  };

  async function save(filename, data) {
    if (!S.caps.downloads) { toast('Téléchargement indisponible dans cette vue.'); return; }
    try { await S.caps.downloads.save({ filename, data }); toast(`${filename} enregistré.`); }
    catch (e) { if (e && e.code !== 'declined') toast(`Téléchargement impossible (${(e && e.code) || 'erreur'}).`); }
  }

  // ─── Pipeline ────────────────────────────────────────────────────────────
  const STEP_LABELS = { ingest: 'Ingestion de l\'offre', analyse: 'Analyse de l\'offre', match: 'Matching profil ↔ offre', strategie: 'Stratégie A/B/C', cv: 'CV : contenu lié aux faits',
    validation: 'Validation claim → evidence', critique: 'Critique (7 juges) et corrections', lettre: 'Lettre de motivation', questions: 'Réponses aux questions', pdf: 'PDF + contrôle qualité', pack: 'Application Pack' };
  const MODE_STEPS = { QUICK: ['ingest', 'analyse', 'match', 'strategie', 'pack'], STANDARD: ['ingest', 'analyse', 'match', 'strategie', 'cv', 'validation', 'critique', 'lettre', 'questions', 'pdf', 'pack'] };
  MODE_STEPS.DEEP = MODE_STEPS.STANDARD;

  function startRun(mode) {
    S.run = { status: 'running', mode, controller: new AbortController(), calls: [], log: [], steps: MODE_STEPS[mode].map((k) => ({ key: k, state: 'todo', detail: '' })), packId: null, error: null, live: '' };
    render();
  }
  const setStep = (key, state, detail) => {
    if (!S.run) return; const st = S.run.steps.find((s) => s.key === key); if (!st) return;
    st.state = state; if (detail !== undefined) st.detail = detail; S.run.log.push({ stage: key, state, detail: detail || '' }); renderRun();
  };
  const liveText = (key) => (text) => { if (!S.run) return; const st = S.run.steps.find((s) => s.key === key); if (st) { st.detail = `Claude rédige… ${text.length.toLocaleString('fr-FR')} caractères`; renderRun(); } };

  async function tryAi(key, fn) {
    if (!AI.ok()) return null;
    try { return await fn(); } catch (e) {
      if (e && e.code === 'cancelled') throw e;
      S.run.log.push({ stage: key, state: 'ai_error', detail: AI.message(e) });
      const st = S.run.steps.find((s) => s.key === key); if (st) st.note = AI.message(e);
      return null;
    }
  }

  async function fixLoop(lines, validator, P, a, opts = {}) {
    const vars = E.commonVars(P, a); const lang = a.language_of_offer === 'en' ? 'anglais' : 'français';
    let report = validator.validateLines(lines); let instructions = opts.instructions || null;
    let targets = new Set(report.rejected_ids.concat(Object.keys(instructions || {})));
    let attempts = 0; const dropped = [];
    while (targets.size && AI.ok() && attempts < 2) {
      attempts++;
      const payload = lines.filter((l) => targets.has(l.id)).map((l) => ({ id: l.id, text: l.text, kind: l.kind, fact_ids: l.fact_ids,
        reasons: ((report.verdicts.find((v) => v.line_id === l.id) || {}).reasons || []).concat(instructions && instructions[l.id] ? [instructions[l.id]] : []) }));
      const fixed = await tryAi(opts.step || 'validation', () => AI.ask('cv_fix', { rejected_lines_json: JSON.stringify(payload), facts_table: vars.facts_table,
        critic_instructions: (opts.general || []).join(' ; ') || 'aucune', truth_rules: vars.truth_rules, language: lang }, { signal: S.run && S.run.controller.signal, cache: false }));
      if (!fixed || !Array.isArray(fixed.lines)) break;
      const byId = new Map(fixed.lines.filter((x) => x && x.id).map((x) => [String(x.id), x]));
      lines = lines.flatMap((l) => {
        const it = byId.get(l.id); if (!it) return [l];
        const t = String(it.text || '').trim();
        if (!t) { dropped.push({ id: l.id, text: l.text, reasons: ((report.verdicts.find((v) => v.line_id === l.id) || {}).reasons || []).concat(['supprimée à la correction : aucune version vraie possible']) }); return []; }
        return [Object.assign({}, l, { text: t, fact_ids: (it.fact_ids || l.fact_ids).map(String) })];
      });
      instructions = null; report = validator.validateLines(lines); targets = new Set(report.rejected_ids);
    }
    const rej = new Set(report.rejected_ids);
    const removed = dropped.concat(lines.filter((l) => rej.has(l.id)).map((l) => ({ id: l.id, text: l.text, reasons: (report.verdicts.find((v) => v.line_id === l.id) || {}).reasons || [] })));
    const kept = lines.filter((l) => !rej.has(l.id));
    const final = validator.validateLines(kept); final.forbidden_hits += report.forbidden_hits;
    return { lines: kept, report: final, removed };
  }

  function critiqueInstructions(ai) {
    const per = {}; const general = [];
    for (const it of (ai && ai.issues) || []) {
      if (!['high', 'medium'].includes(String(it.severity))) continue;
      const fix = `${it.problem || ''} → ${it.fix || ''}`.replace(/^ → | → $/g, '');
      const ids = (it.line_ids || []).map(String);
      if (ids.length) ids.forEach((id) => { per[id] = per[id] ? `${per[id]} ; ${fix}` : fix; }); else general.push(fix);
    }
    return [per, general];
  }

  async function generateCv(P, a, m, strat, offer, opts = {}) {
    const vars = E.commonVars(P, a); const d = E.design(strat.best.design_profile); const signal = S.run.controller.signal;
    let cv = E.buildCvDeterministic(P, a, m, strat, S.profile.validated);
    const ai = await tryAi('cv', () => AI.ask('cv_content', Object.assign({}, vars, {
      strategy_json: JSON.stringify(strat.best), synonyms: JSON.stringify({ equivalents: D.synonyms.equivalents.slice(0, 25), implies: D.synonyms.implies }),
      banned_phrases: D.banned.hard.slice(0, 30).join(', '), feedback_context: opts.feedback || feedbackContext(a),
      language: a.language_of_offer === 'en' ? 'anglais' : 'français', max_bullets_featured: String(d.max_bullets_featured || 4), max_bullets_other: String(d.max_bullets_other || 2),
    }), { signal, onText: liveText('cv'), cache: opts.cache }));
    if (ai && typeof ai === 'object') cv = E.cvFromAi(ai, P, a, m, strat, S.profile.validated);
    return cv;
  }

  async function validateAndCritique(cv, P, a, m, offer, cycles) {
    const validator = E.Validator(S.profile, offer.text, [a.job_title, a.company]);
    setStep('validation', 'run', 'Contrôle de chaque ligne contre les faits');
    let r = await fixLoop(cv.lines, validator, P, a, { step: 'validation' });
    cv.lines = r.lines; cv.removed_lines = (cv.removed_lines || []).concat(r.removed); E.syncBlocks(cv);
    let report = r.report;
    setStep('validation', 'done', `${report.traced}/${report.total} lignes tracées${r.removed.length ? ` · ${r.removed.length} supprimée(s)` : ''}`);
    setStep('critique', 'run', 'Jury : recruteur, manager, ATS, design, factualité, match, secteur');
    const vars = E.commonVars(P, a); let critique = { deterministic: null, ai: null };
    for (let cycle = 0; cycle < Math.max(1, cycles); cycle++) {
      const det = E.deterministicCritique(cv, a, m, report);
      const ai = await tryAi('critique', () => AI.ask('critique', { analysis_json: vars.analysis_json, sector_json: vars.sector_json, country_json: vars.country_json,
        design_json: JSON.stringify(E.design(cv.design_profile)), validation_json: JSON.stringify({ factuality: report.factuality, total: report.total, traced: report.traced, warnings: report.warnings }),
        cv_text: E.cvPlainText(cv), sector_name: vars.sector_name }, { signal: S.run.controller.signal, onText: liveText('critique'), cache: false }));
      critique = { deterministic: det, ai: ai && typeof ai === 'object' ? ai : null, cycles: cycle + 1 };
      const [per, general] = critiqueInstructions(critique.ai);
      det.issues.filter((i) => i.severity === 'high' && !i.line_ids.length).forEach((i) => general.push(i.fix));
      if (!AI.ok() || (!Object.keys(per).length && !general.length)) break;
      let targets = {}; for (const [id, t] of Object.entries(per)) if (E.lineById(cv, id)) targets[id] = t;
      if (!Object.keys(targets).length && general.length) for (const l of E.sectionLines(cv, 'summary').slice(0, 1).concat(E.sectionLines(cv, 'experience').slice(0, 2))) targets[l.id] = general.join(' ; ');
      if (!Object.keys(targets).length) break;
      setStep('critique', 'run', `Cycle ${cycle + 1} : ${Object.keys(targets).length} ligne(s) à corriger`);
      r = await fixLoop(cv.lines, validator, P, a, { instructions: targets, general, step: 'critique' });
      cv.lines = r.lines; cv.removed_lines = cv.removed_lines.concat(r.removed); E.syncBlocks(cv); report = r.report;
    }
    const judges = critique.ai && critique.ai.scores ? Object.entries(critique.ai.scores).map(([k, v]) => `${k} ${v && v.score !== undefined ? v.score : '?'}`).join(' · ') : 'critique déterministe';
    setStep('critique', 'done', judges);
    return { cv, report, critique };
  }

  async function buildLetter(P, a, m, strat, offer) {
    const vars = E.commonVars(P, a); const s = E.sector(a.sector_id); const [lo, hi] = (s.letter_style || {}).length_words || [220, 320];
    const base = E.buildLetterDeterministic(P, a, m, strat, offer, S.profile.validated);
    const ai = await tryAi('lettre', () => AI.ask('letter', { analysis_json: vars.analysis_json, strategy_json: JSON.stringify(strat.best),
      company_facts: JSON.stringify({ source: 'offre', texte: offer.text.slice(0, 1500) }), facts_table: vars.facts_table, sector_json: vars.sector_json,
      banned_phrases: D.banned.hard.slice(0, 30).join(', '), feedback_context: feedbackContext(a), truth_rules: vars.truth_rules, candidate_name: P.value('id.name'),
      language: a.language_of_offer === 'en' ? 'anglais' : 'français', length_words: `${lo} à ${hi}`, company: a.company, job_title: strat.best.title },
    { signal: S.run.controller.signal, onText: liveText('lettre') }));
    const letter = ai && typeof ai === 'object' ? E.letterFromAi(ai, P, base) : base;
    const validator = E.Validator(S.profile, offer.text, [a.job_title, a.company]);
    const r = await fixLoop(letter.lines, validator, P, a, { step: 'lettre' });
    letter.lines = r.lines; letter.removed_lines = r.removed;
    return { letter, report: r.report, checks: E.letterChecks(letter, a) };
  }

  function splitQuestions(raw) { return String(raw || '').split(/\n+|(?<=\?)\s+/).map((q) => q.replace(/^[\s\-•*]+/, '').trim()).filter((q) => q.length > 5).slice(0, 15); }
  function answerDeterministic(q, P) {
    const n = E.norm(q);
    if (/salaire|remuneration|pretention|salary|compensation/.test(n)) return { question: q, type: 'SALARY', answer: '', fact_ids: [], confidence: 'BLOCKED', ask_user: 'Quelles sont vos prétentions salariales (fixe + variable) ?' };
    if (/disponib|date de debut|start date|preavis|notice/.test(n) && P.fact('avail.immediate')) return { question: q, type: 'AVAILABILITY', answer: `${P.value('avail.immediate')}.`, fact_ids: ['avail.immediate'], confidence: 'HIGH', ask_user: '' };
    if (/langue|anglais|english|espagnol|arabe|toeic/.test(n)) { const fs = P.byKind('language'); return { question: q, type: 'LANGUAGE', answer: fs.map((f) => f.text).join(' ; ') + (P.fact('cert.toeic') ? ` (${P.value('cert.toeic')})` : '') + '.', fact_ids: fs.map((f) => f.id).concat(P.fact('cert.toeic') ? ['cert.toeic'] : []), confidence: 'HIGH', ask_user: '' }; }
    if (/mobilit|demenag|relocat/.test(n) && P.fact('mobility.idf')) return { question: q, type: 'ADMIN', answer: `${P.value('mobility.idf')} (confirmée). Au-delà : à préciser.`, fact_ids: ['mobility.idf'], confidence: 'MEDIUM', ask_user: '' };
    return { question: q, type: 'OPEN', answer: '', fact_ids: [], confidence: 'BLOCKED', ask_user: 'Réponse personnelle nécessaire : que souhaitez-vous dire ?' };
  }
  async function buildAnswers(raw, P, a) {
    const qs = splitQuestions(raw); if (!qs.length) return [];
    const vars = E.commonVars(P, a);
    const ai = await tryAi('questions', () => AI.ask('answers', { questions: qs.map((q) => `- ${q}`).join('\n'), analysis_json: vars.analysis_json, facts_table: vars.facts_table,
      truth_rules: vars.truth_rules, candidate_name: P.value('id.name'), language: a.language_of_offer === 'en' ? 'anglais' : 'français' }, { signal: S.run.controller.signal }));
    if (ai && Array.isArray(ai.answers)) {
      const known = new Set(P.usableFacts().map((f) => f.id));
      return ai.answers.map((x) => {
        const ans = { question: String(x.question || ''), type: String(x.type || 'OPEN'), answer: String(x.answer || ''), fact_ids: (x.fact_ids || []).map(String), confidence: String(x.confidence || 'BLOCKED'), ask_user: String(x.ask_user || '') };
        if (ans.confidence !== 'BLOCKED' && (!ans.fact_ids.length || !ans.fact_ids.every((id) => known.has(id)))) { ans.confidence = 'BLOCKED'; ans.answer = ''; ans.ask_user = ans.ask_user || 'Aucun fait du profil ne permet de répondre : à compléter par vous.'; }
        return ans;
      });
    }
    return qs.map((q) => answerDeterministic(q, P));
  }

  function feedbackContext(a) {
    const ctx = S.feedback.filter((f) => f.context && (f.context.sector === a.sector_id)).slice(0, 12)
      .map((f) => `${f.id} [${f.element}] ${f.rating === 1 ? '👍' : f.rating === -1 ? '👎' : '😐'} ${f.comment || ''}`.trim());
    const rules = (S.rules.accepted || []).map((r) => `RÈGLE ${r.id}: ${r.rule_text}`);
    return ctx.concat(rules).join('\n') || 'aucun';
  }

  async function runPipeline() {
    const P = Pp(); if (!P) { toast("Aucun profil : importez d'abord votre Master Profile."); return; }
    const text = (S.draft.offer || '').trim();
    if (text.length < 80) { toast("Collez le texte complet de l'offre (80 caractères minimum)."); return; }
    const mode = S.draft.mode; startRun(mode); const signal = S.run.controller.signal;
    try {
      setStep('ingest', 'run');
      const offer = { id: `off_${E.hash(E.norm(text))}`, source_type: S.draft.sourceType || 'text', source_url: '', fetched_at: nowIso(), title_hint: S.draft.title.trim(), company_hint: S.draft.company.trim(),
        text: text.slice(0, 30000), text_hash: E.hash(E.norm(text)), synthetic: !!S.draft.synthetic };
      const dup = S.packs.find((p) => p.offer && p.offer.text_hash === offer.text_hash);
      setStep('ingest', 'done', `${text.length.toLocaleString('fr-FR')} caractères · empreinte ${offer.text_hash}${dup ? ' · offre déjà analysée (nouvelle version)' : ''}`);

      setStep('analyse', 'run', 'Extraction déterministe');
      const base = E.deterministicAnalysis(offer);
      const aiA = await tryAi('analyse', () => AI.ask('analyze_offer', { offer_text: offer.text.slice(0, 12000), job_title_hint: offer.title_hint, company_hint: offer.company_hint,
        deterministic_json: JSON.stringify(Object.assign({}, base, { sector_scores: undefined })) }, { signal, onText: liveText('analyse') }));
      const a = aiA && typeof aiA === 'object' ? E.mergeAiAnalysis(base, aiA) : base;
      setStep('analyse', 'done', `${a.job_title} · ${a.company} · ${a.contract} · ${E.sector(a.sector_id).name || a.sector_id}${a.source === 'deterministic' ? ' (sans IA)' : ''}`);

      setStep('match', 'run');
      const m = E.computeMatch(P, a);
      setStep('match', 'done', `MATCH ${pct(m.match)} · QUALITY ${pct(m.quality)} · RISK ${pct(m.risk)}`);

      setStep('strategie', 'run', 'Comparaison des positionnements');
      let strat = E.deterministicStrategy(P, a, m); const vars = E.commonVars(P, a);
      const aiS = await tryAi('strategie', () => AI.ask('strategy', Object.assign({}, vars, { match_json: JSON.stringify({ scores: m.scores, match: m.match, quality: m.quality, risk: m.risk, missing: m.missing, strengths: m.strengths }),
        learned_rules: (S.rules.accepted || []).map((r) => r.rule_text).join('\n') || 'aucune', variants: mode === 'DEEP' ? '3' : '2' }),
      { signal, tier: mode === 'QUICK' ? 'default' : undefined, onText: liveText('strategie') }));
      if (aiS && aiS.best && typeof aiS.best === 'object') {
        strat = E.sanitizeStrategy({ options: Array.isArray(aiS.options) ? aiS.options : [], comparison: String(aiS.comparison || ''), chosen: String(aiS.chosen || 'A'),
          best: Object.assign({}, strat.best, aiS.best), source: 'ai' }, P, a);
      }
      setStep('strategie', 'done', `« ${strat.best.title} » · ${strat.best.ats_mode} · ${strat.best.design_profile}`);

      const pack = { id: uid('pack'), created_at: nowIso(), mode, status: 'DRAFT', engine: 'studio', provider: AI.ok() ? 'claude.ai (sample)' : 'aucun (mode dégradé)',
        versions: { offer_v: offer.text_hash, profile_v: profileTag(S.profile), engine_v: D.version.engine, prompt_v: D.version.prompts, rules_v: D.version.rules, cv_v: '', letter_v: '', answers_v: '' },
        offer, analysis: a, match: m, strategy: strat, cvs: [], cv_index: 0, letters: [], letter_index: 0, answers: [], scores: {}, risks: m.risks.map((r) => r.text).concat(strat.best.risks || []),
        next_action: '', missing_profile_data: missingData(S.profile), log: [], calls: [] };
      if (mode === 'QUICK') {
        pack.next_action = 'Lancer le mode STANDARD pour générer le CV et la lettre.';
        return await finishPack(pack);
      }
      const cycles = ((D.models.modes || {})[mode] || {}).critique_cycles || 1;
      setStep('cv', 'run', 'Plan de contenu');
      setStep('lettre', 'run', 'Rédaction en parallèle');
      const letterPromise = buildLetter(P, a, m, strat, offer);
      const variants = [strat];
      if (mode === 'DEEP' && Array.isArray(strat.options) && strat.options.length > 1) {
        const alt = strat.options.find((o) => o && o.key !== strat.chosen);
        if (alt) variants.push(E.sanitizeStrategy({ options: [], chosen: alt.key, best: Object.assign({}, strat.best, alt), source: 'ai' }, P, a));
      }
      const cvs = [];
      for (const [i, st] of variants.entries()) {
        const cv0 = await generateCv(P, a, m, st, offer);
        setStep('cv', 'done', `${cv0.lines.length} lignes (${cv0.source === 'ai' ? 'rédigées par Claude' : 'tirées des faits'})${variants.length > 1 ? ` · variante ${i + 1}/${variants.length}` : ''}`);
        const res = await validateAndCritique(cv0, P, a, m, offer, cycles);
        cvs.push(Object.assign(res, { label: i === 0 ? `V1 · ${st.chosen || 'A'}` : `Variante ${st.chosen}` }));
      }
      const L = await letterPromise;
      setStep('lettre', 'done', `${L.report.traced}/${L.report.total} phrases tracées · ${L.letter.lines.filter((l) => l.kind === 'offer_ref').length} élément(s) de l'annonce`);
      setStep('questions', 'run');
      pack.answers = await buildAnswers(S.draft.questions, P, a);
      setStep('questions', pack.answers.length ? 'done' : 'skip', pack.answers.length ? `${pack.answers.length} réponse(s) · ${pack.answers.filter((x) => x.confidence === 'BLOCKED').length} à compléter` : 'aucune question');

      setStep('pdf', 'run', 'pdfmake → PDF texte, contrôle pdf.js');
      const maxPages = E.country(a.country).max_pages || 1;
      const required = m.coverage.filter((c) => c.covered && c.priority === 'REQUIRED').map((c) => c.term);
      for (const [i, entry] of cvs.entries()) {
        const fit = await PDF.cvFitted(entry.cv, maxPages);
        entry.cv = fit.doc; entry.qa = PDF.qa(fit.info, fit.doc, required, maxPages); entry.qa.trim_steps = fit.trimSteps;
        entry.report = E.Validator(S.profile, offer.text, [a.job_title, a.company]).validateLines(entry.cv.lines);
        if (mode === 'DEEP' && i === 0 && S.aiLimits && S.aiLimits.images) {
          const png = await PDF.pngBlob(fit.bytes);
          const vis = await tryAi('pdf', () => AI.ask('judge_visual', { context: `CV pour « ${a.job_title} » (${a.company}), design ${fit.doc.design_profile}` }, { signal, images: [png], cache: false }));
          if (vis) entry.qa.visual = vis;
        }
      }
      const q0 = cvs[0].qa; setStep('pdf', q0.ok ? 'done' : 'fail', `${q0.pages} page(s) · mots-clés REQUIRED ${q0.required_found}${q0.issues.length ? ' · ' + q0.issues.map((x) => x.check).join(', ') : ' · aucun défaut'}`);
      if (cvs.length > 1) {
        const avg = (e) => { const sc = e.critique.ai && e.critique.ai.scores ? Object.values(e.critique.ai.scores).map((v) => Number(v && v.score) || 0) : [0]; return sc.reduce((x, y) => x + y, 0) / sc.length; };
        cvs.sort((x, y) => avg(y) - avg(x));
      }
      pack.cvs = cvs.map((e, i) => ({ v: i + 1, label: e.label, created_at: nowIso(), source: e.cv.source, doc: e.cv, report: e.report, critique: e.critique, qa: e.qa }));
      pack.letters = [{ v: 1, label: 'V1', created_at: nowIso(), source: L.letter.source, doc: L.letter, report: L.report, checks: L.checks }];
      pack.cv_index = 0; pack.letter_index = 0;
      return await finishPack(pack);
    } catch (e) {
      const cancelled = e && e.code === 'cancelled';
      if (S.run) { S.run.status = cancelled ? 'cancelled' : 'failed'; S.run.error = cancelled ? 'Génération annulée.' : `Échec propre : ${(e && e.message) || e}`; }
      console.error(e); render();
    }
  }

  function computeScores(pack) {
    const cvE = pack.cvs[pack.cv_index]; const lE = pack.letters[pack.letter_index];
    const crit = cvE && cvE.critique ? cvE.critique.deterministic : null;
    const points = E.scoreEvents(cvE && cvE.doc, lE && lE.doc, pack.analysis, pack.match, pack.strategy, { cv: (cvE && cvE.report) || {}, letter: (lE && lE.report) || {} }, crit);
    return { factuality_cv: cvE ? cvE.report.factuality : null, factuality_letter: lE ? lE.report.factuality : null, match: pack.match.match, quality: pack.match.quality, risk: pack.match.risk, points };
  }
  function refreshStatus(pack) {
    const cvE = pack.cvs[pack.cv_index]; const lE = pack.letters[pack.letter_index];
    const perfect = cvE && lE && cvE.report.perfect && lE.report.perfect;
    const pdfOk = cvE && cvE.qa ? cvE.qa.ok : true;
    pack.status = S.profile.validated && perfect && pdfOk ? 'FINAL' : 'DRAFT';
    pack.next_action = pack.status === 'FINAL' ? 'Relire puis postuler vous-même (PAI n\'envoie rien).'
      : !S.profile.validated ? 'Valider le Master Profile (Profil) pour passer les documents en FINAL, puis relire et postuler vous-même.'
        : 'Corriger les lignes signalées (factualité 100 % requise) avant de postuler.';
    pack.scores = computeScores(pack);
    if (cvE) { pack.versions.cv_v = E.hash(cvE.doc.lines); pack.versions.letter_v = lE ? E.hash(lE.doc.lines) : ''; }
    pack.versions.answers_v = pack.answers.length ? E.hash(pack.answers) : '';
  }
  async function finishPack(pack) {
    setStep('pack', 'run');
    if (pack.cvs.length) refreshStatus(pack);
    pack.log = S.run.log.slice(); pack.calls = S.run.calls.slice();
    await Store.savePack(pack);
    S.packId = pack.id; lsSet('packId', pack.id); S.run.status = 'done'; S.run.packId = pack.id;
    setStep('pack', 'done', `Statut ${pack.status}${pack.cvs.length ? ` · factualité CV ${pack.scores.factuality_cv} % · lettre ${pack.scores.factuality_letter} %` : ''}`);
    render();
    return pack;
  }
  function missingData(p) {
    const out = (p.unknowns || []).slice();
    (p.review_queue || []).forEach((r) => out.push(`${r.fact_id} — ${r.reason}`));
    p.facts.filter((f) => f.needs_confirmation && E.usable(f)).forEach((f) => out.push(`À confirmer : ${f.text} (${f.id})`));
    return out;
  }

  // ─── Rendus partagés ───────────────────────────────────────────────────
  const icon = (id) => `<svg class="ico" aria-hidden="true"><use href="#${id}"/></svg>`;
  const chip = (text, t = '') => `<span class="chip ${t}">${esc(text)}</span>`;
  const statusChip = (s) => `<span class="chip ${STATUS_TONE[s] || ''}"><span class="dot"></span>${esc(s)}</span>`;
  const fids = (ids) => (ids || []).map((id) => `<span class="fid" data-fact="${esc(id)}">${esc(id)}</span>`).join(' ');
  const gauge = (label, v, t, sub) => `<div class="gauge"><div class="top"><span class="muted">${esc(label)}</span><span class="n">${pct(v)}</span></div><div class="bar ${t}"><i style="width:${Math.max(0, Math.min(100, v || 0))}%"></i></div>${sub ? `<div class="muted" style="font-size:12.5px">${sub}</div>` : ''}</div>`;
  const packById = (id) => S.packs.find((p) => p.id === id) || null;
  const curPack = () => packById(S.packId);

  function sheetHTML(cv, opts = {}) {
    const d = E.design(cv.design_profile); const c = Object.assign({}, d.colors, cv.colors || {});
    const rej = new Set(opts.rejected || []);
    const L = (l, tag = 'span') => `<${tag} data-line="${esc(l.id)}" class="${rej.has(l.id) ? 'rej' : ''}">${esc(l.text)}</${tag}>`;
    const vars = `--cv-accent:${c.accent};--cv-accent2:${c.accent2};--cv-ink:${c.ink};--cv-muted:${c.muted};--cv-rule:${c.rule};--cv-band:${c.band}`;
    const head = `<div class="${d.header === 'band' ? 'band' : 'plain'}"><div class="nm">${esc(cv.name)}</div>${E.sectionLines(cv, 'headline').map((l) => `<div class="hl">${L(l)}</div>`).join('')}
      <div class="ct">${cv.contact.map(esc).join(' · ')}</div>${E.sectionLines(cv, 'extras').map((l) => `<div class="xt">${L(l)}</div>`).join('')}</div>`;
    const sec = (key, inner) => (inner ? `<div class="sec"><h4>${esc(cv.section_titles[key] || key)}</h4>${inner}</div>` : '');
    const summary = E.sectionLines(cv, 'summary').map((l) => L(l)).join(' ');
    const exps = cv.experiences.map((b) => `<div class="ex"><div class="eh"><span class="et">${esc(b.title)}</span><span class="ep">${esc(b.period)}</span></div>
      <div class="em"><b>${esc(b.company)}</b>${b.city ? ` · ${esc(b.city)}` : ''}</div><ul>${b.bullet_ids.map((id) => E.lineById(cv, id)).filter(Boolean).map((l) => L(l, 'li')).join('')}</ul></div>`).join('');
    const groups = {}; E.sectionLines(cv, 'skills').forEach((l) => (groups[l.group || ''] = groups[l.group || ''] || []).push(l));
    const skills = Object.entries(groups).map(([g, ls]) => `<div class="kr"><b>${esc(g)}</b><span>${ls.map((l) => L(l)).join(', ')}</span></div>`).join('');
    const simple = (k) => E.sectionLines(cv, k).map((l) => `<div>${L(l)}</div>`).join('');
    const mainHtml = sec('summary', summary ? `<p style="margin:0">${summary}</p>` : '') + sec('experience', exps);
    const sideHtml = sec('skills', skills) + sec('education', simple('education')) + sec('certifications', simple('certifications')) + sec('languages', simple('languages'));
    const body = d.layout === 'two_column' ? `<div class="grid2"><div>${mainHtml}</div><div>${sideHtml}</div></div>` : mainHtml + sideHtml;
    return `<div class="sheet-wrap"><div class="sheet ${d.layout === 'two_column' ? 'two' : ''}" style="${vars}">${cv.draft ? `<div class="stamp">${cv.language === 'en' ? 'DRAFT — PROFILE NOT VALIDATED' : 'BROUILLON — PROFIL NON VALIDÉ'}</div>` : ''}${head}<div class="body">${body}</div></div></div>`;
  }
  function letterSheetHTML(letter, name, contact, opts = {}) {
    const rej = new Set(opts.rejected || []);
    const paras = letter.paragraph_order.map((r) => letter.lines.filter((l) => l.section === r)).filter((ls) => ls.length)
      .map((ls) => `<p>${ls.map((l) => `<span data-line="${esc(l.id)}" class="${rej.has(l.id) ? 'rej' : ''}">${esc(l.text)}</span>`).join(' ')}</p>`).join('');
    return `<div class="sheet-wrap"><div class="sheet" style="--cv-accent:#1C5D7A">${letter.draft ? `<div class="stamp">${letter.language === 'en' ? 'DRAFT — PROFILE NOT VALIDATED' : 'BROUILLON — PROFIL NON VALIDÉ'}</div>` : ''}
      <div class="lt"><div style="font-size:19px;font-weight:600">${esc(name)}</div><div style="font-size:11.5px;color:#55606B;margin-top:2px">${contact.map(esc).join(' · ')}</div>
      <div style="width:62px;height:2px;background:#1C5D7A;margin:18px 0 22px"></div>
      <div style="display:flex;justify-content:space-between;gap:12px;font-size:12.6px;margin-bottom:22px"><span>${esc(letter.recipient)}</span><span style="color:#55606B">${esc(letter.place_date)}</span></div>
      <p style="font-weight:600">${esc(letter.subject)}</p>${letter.salutation ? `<p>${esc(letter.salutation)}</p>` : ''}${paras}<p style="font-weight:600;margin-top:18px">${esc(letter.signature)}</p></div></div></div>`;
  }
  function fitSheets() {
    $$('.sheet-wrap').forEach((w) => { const s = $('.sheet', w); if (!s) return; const scale = w.clientWidth / 794; s.style.transform = `scale(${scale})`; w.style.height = `${1123 * scale}px`; });
  }

  // ─── Vues ───────────────────────────────────────────────────────────────
  const V = {};

  V.accueil = () => {
    const P = Pp(); const packs = S.packs; const withCv = packs.filter((p) => p.cvs && p.cvs.length);
    const fact = withCv.length ? withCv.reduce((n, p) => n + (p.scores.factuality_cv || 0), 0) / withCv.length : null;
    const pos = S.feedback.filter((f) => f.rating === 1).length;
    const errors = {}; withCv.forEach((p) => { const c = p.cvs[p.cv_index] && p.cvs[p.cv_index].critique; ((c && c.deterministic && c.deterministic.issues) || []).forEach((i) => { errors[i.type] = (errors[i.type] || 0) + 1; }); });
    const topErrors = Object.entries(errors).sort((x, y) => y[1] - x[1]).slice(0, 4);
    const name = P ? P.value('id.name', '') : '';
    return `<div class="page">
      <div class="stack"><h1 class="title">${name ? `Bonjour ${esc(name.split(' ')[0])}` : 'PAI Studio'}</h1>
      <p class="lede">Collez une offre : PAI l'analyse, choisit l'angle, rédige un CV et une lettre sur mesure avec Claude, puis vérifie chaque ligne contre votre profil. Rien n'est inventé ni envoyé à votre place.</p></div>
      ${!P ? `<div class="notice warn">Aucun Master Profile dans cette page. Importez un export JSON dans <b>Profil</b> pour commencer.</div>` : ''}
      ${S.ai === 'denied' ? `<div class="notice warn">Claude n'est pas autorisé pour cette page : PAI fonctionne en mode dégradé (CV et lettre tirés des faits, sans rédaction IA).</div>` : ''}
      <div class="grid g4">
        <div class="card kpi"><span class="v">${packs.length}</span><span class="l">Application Packs</span></div>
        <div class="card kpi"><span class="v">${fact === null ? '—' : `${Math.round(fact)} %`}</span><span class="l">Factualité moyenne des CV</span></div>
        <div class="card kpi"><span class="v">${S.feedback.length}</span><span class="l">Retours${S.feedback.length ? ` · ${Math.round((100 * pos) / S.feedback.length)} % 👍` : ''}</span></div>
        <div class="card kpi"><span class="v">${S.arena.length}</span><span class="l">Votes en arène à l'aveugle</span></div>
      </div>
      <div class="split">
        <div class="card"><div class="row" style="justify-content:space-between"><h3 class="h3">Derniers packs</h3><button class="btn sm primary" data-act="go" data-arg="nouvelle">${icon('i-plus')} Nouvelle candidature</button></div>
          ${packs.length ? `<div class="list">${packs.slice(0, 6).map(packRow).join('')}</div>` : `<div class="empty">Aucun pack pour l'instant. Collez votre première offre réelle.</div>`}</div>
        <div class="stack">
          <div class="card"><h3 class="h3">Prochaine action</h3><p style="margin:0">${esc(nextAction())}</p></div>
          <div class="card"><h3 class="h3">Profil</h3>${P ? `<div class="row">${chip(`v${S.profile.version}`, 'accent')} ${S.profile.validated ? chip('Validé', 'good') : chip('Non validé : documents en brouillon', 'warn')}</div>
            <p class="muted" style="margin:8px 0 0;font-size:13.5px">${P.usableFacts().length} faits utilisables · ${(S.profile.review_queue || []).length} en revue · ${S.profile.facts.filter((f) => f.needs_confirmation).length} chiffres à confirmer</p>` : '<p class="muted">—</p>'}</div>
          <div class="card"><h3 class="h3">Erreurs principales</h3>${topErrors.length ? `<div class="list">${topErrors.map(([k, n]) => `<div class="item"><span class="grow">${esc(k.replace(/_/g, ' '))}</span>${chip(`${n}×`)}</div>`).join('')}</div>` : '<p class="muted" style="margin:0">Pas encore de données.</p>'}</div>
          <div class="card"><h3 class="h3">Benchmark</h3>${S.bench ? `<p style="margin:0">Moteur ${esc(S.bench.engine_v)} : <b>${pct(S.bench.new_avg)}</b>/100 contre ${pct(S.bench.legacy_avg)} pour l'ancien générateur (${S.bench.n} offres, partie déterministe).</p>` : '<p class="muted" style="margin:0">Aucun résultat importé.</p>'}</div>
        </div>
      </div></div>`;
  };
  function nextAction() {
    const p = S.profile; if (!p) return 'Importer votre Master Profile (Profil → Importer).';
    if (conflicts(p).length) return `Résoudre ${conflicts(p).length} conflit(s) dans Profil, puis valider le profil.`;
    if (!p.validated) return 'Relire vos faits (chiffres à confirmer) et cliquer « Valider le profil » : vos documents passeront de BROUILLON à FINAL.';
    if (!S.packs.length) return 'Coller une vraie offre dans « Nouvelle candidature ».';
    return 'Donner votre avis (👍 😐 👎) sur le dernier pack : c\'est ce qui fait progresser PAI.';
  }
  function packRow(p) {
    const a = p.analysis || {};
    return `<button class="item" data-act="open-pack" data-arg="${esc(p.id)}"><span class="grow"><span class="t">${esc(a.job_title || '—')} · ${esc(a.company || '—')}</span>
      <span class="s">${fmtDate(p.created_at)} · ${esc(p.mode)} · MATCH ${pct(p.match && p.match.match)}${p.offer && p.offer.synthetic ? ' · SYNTHETIC' : ''}</span></span>${chip(p.status, p.status === 'FINAL' ? 'good' : 'warn')}</button>`;
  }

  V.nouvelle = () => {
    const run = S.run;
    return `<div class="page"><div class="stack"><h1 class="title">Nouvelle candidature</h1>
      <p class="lede">Collez l'offre complète (ou importez son PDF). Les sites qui exigent une connexion ne sont jamais aspirés : copiez le texte.</p></div>
      <div class="split"><div class="card stack">
        <div class="field"><label for="f-offer">Texte de l'offre</label><textarea id="f-offer" class="textarea" data-bind="offer" placeholder="Intitulé, entreprise, missions, profil recherché…">${esc(S.draft.offer)}</textarea></div>
        <div class="grid g2"><div class="field"><label for="f-title">Intitulé (facultatif)</label><input id="f-title" class="input" data-bind="title" value="${esc(S.draft.title)}"></div>
          <div class="field"><label for="f-company">Entreprise (facultatif)</label><input id="f-company" class="input" data-bind="company" value="${esc(S.draft.company)}"></div></div>
        <div class="field"><label for="f-questions">Questions du formulaire (une par ligne, facultatif)</label><textarea id="f-questions" class="textarea" style="min-height:90px" data-bind="questions" placeholder="Quelles sont vos prétentions salariales ?">${esc(S.draft.questions)}</textarea></div>
        <div class="row" style="justify-content:space-between">
          <div class="seg" role="group" aria-label="Mode">${['QUICK', 'STANDARD', 'DEEP'].map((m) => `<button data-act="mode" data-arg="${m}" aria-pressed="${S.draft.mode === m}">${m}</button>`).join('')}</div>
          <div class="row"><label class="btn sm ghost" for="f-pdf">Importer un PDF</label><input id="f-pdf" type="file" accept="application/pdf" class="sr" data-change="offer-pdf">
            <button class="btn sm ghost" data-act="example">Exemple (offre fictive)</button></div></div>
        <p class="muted" style="margin:0;font-size:13px">${({ QUICK: 'Analyse, matching et stratégie (≈ 30 s).', STANDARD: 'Pipeline complète : CV, critique, lettre, questions, pack (≈ 2 à 4 min, 6 à 9 appels à Claude).', DEEP: 'Deux variantes de CV, jusqu\'à 3 cycles de critique, contrôle visuel du PDF (≈ 5 à 8 min, 10 à 16 appels).' })[S.draft.mode]}
          ${AI.ok() ? 'Les appels utilisent votre compte Claude.' : 'Claude indisponible : mode dégradé, sans rédaction IA.'}</p>
        <div class="row"><button class="btn primary" data-act="run" ${run && run.status === 'running' ? 'disabled' : ''}>Analyser et générer</button>${run && run.status === 'running' ? '<button class="btn" data-act="cancel">Arrêter</button>' : ''}</div>
      </div>
      <div class="card" id="run-panel">${runPanel()}</div></div></div>`;
  };
  function runPanel() {
    const r = S.run;
    if (!r) return `<h3 class="h3">Progression</h3><ol class="steps" style="padding:0;margin:0">${MODE_STEPS[S.draft.mode].map((k) => `<li class="step"><span class="st"></span><span>${esc(STEP_LABELS[k])}</span><span></span></li>`).join('')}</ol>`;
    return `<h3 class="h3">Progression · ${esc(r.mode)}</h3><ol class="steps" style="padding:0;margin:0">${r.steps.map((s) => `<li class="step ${s.state}"><span class="st"></span><span>${esc(STEP_LABELS[s.key])}<br><span class="d">${esc(s.detail || '')}${s.note ? ` · ${esc(s.note)}` : ''}</span></span><span class="d">${s.state === 'done' ? '✓' : ''}</span></li>`).join('')}</ol>
      ${r.error ? `<div class="notice bad" style="margin-top:10px">${esc(r.error)}</div>` : ''}
      ${r.status === 'done' ? `<div class="row" style="margin-top:12px"><button class="btn primary" data-act="open-pack" data-arg="${esc(r.packId)}">Ouvrir le pack</button><span class="muted" style="font-size:13px">${r.calls.length} appel(s) à Claude</span></div>` : ''}`;
  }
  function renderRun() { const el = $('#run-panel'); if (el) el.innerHTML = runPanel(); }

  V.packs = () => `<div class="page"><div class="stack"><h1 class="title">Application Packs</h1><p class="lede">Chaque pack est figé et versionné : offre, analyse, stratégie, CV, lettre, réponses, scores.</p></div>
    <div class="card">${S.packs.length ? `<div class="list">${S.packs.map(packRow).join('')}</div>` : '<div class="empty">Aucun pack.</div>'}</div></div>`;

  V.pack = () => {
    const p = curPack(); if (!p) return `<div class="page"><div class="empty">Pack introuvable. <button class="btn sm" data-act="go" data-arg="packs">Voir les packs</button></div></div>`;
    const a = p.analysis; const tabs = [['synthese', 'Synthèse'], ['cv', 'CV Studio'], ['lettre', 'Letter Studio'], ['questions', 'Questions'], ['export', 'Export'], ['copilote', 'Copilote']];
    const tab = p.cvs.length ? S.packTab : 'synthese';
    return `<div class="page"><div class="row" style="justify-content:space-between;align-items:flex-start"><div class="stack" style="gap:6px"><h1 class="title">${esc(a.job_title)}</h1>
      <div class="row">${chip(a.company)} ${chip(a.location)} ${chip(a.contract)} ${chip(E.sector(a.sector_id).name || a.sector_id, 'accent')} ${chip(p.status, p.status === 'FINAL' ? 'good' : 'warn')} ${p.offer.synthetic ? chip('SYNTHETIC', 'warn') : ''}</div></div>
      <button class="btn sm ghost" data-act="go" data-arg="packs">← Tous les packs</button></div>
      <div class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" aria-selected="${tab === k}" data-act="pack-tab" data-arg="${k}" ${!p.cvs.length && k !== 'synthese' ? 'disabled' : ''}>${l}</button>`).join('')}</div>
      ${({ synthese: packSynthese, cv: packCv, lettre: packLetter, questions: packQuestions, export: packExport, copilote: packCopilot })[tab](p)}</div>`;
  };

  function packSynthese(p) {
    const m = p.match; const s = p.strategy; const a = p.analysis;
    const subs = Object.entries(m.scores).map(([k, v]) => `<div class="sub"><span class="muted">${esc(k)}</span><div class="bar ${tone(v)}"><i style="width:${v}%"></i></div><span class="v">${pct(v)}</span></div>`).join('');
    const cov = m.coverage.map((c) => `<span class="chip ${c.covered ? 'good' : c.priority === 'REQUIRED' ? 'bad' : 'warn'}" title="${esc(c.covered ? `Prouvé par ${c.fact_ids.join(', ')} (${c.via})` : 'Aucun fait ne le prouve')}">${c.covered ? '✓' : '✗'} ${esc(c.term)} <span class="mono">${esc(c.priority[0])}</span></span>`).join(' ');
    const list = (items, key = 'text') => (items && items.length ? `<ul style="margin:0;padding-left:18px">${items.map((x) => `<li>${esc(typeof x === 'string' ? x : x[key] || x.requirement || '')}${x.fact_ids && x.fact_ids.length ? ` ${fids(x.fact_ids)}` : ''}</li>`).join('')}</ul>` : '<p class="muted" style="margin:0">—</p>');
    const opts = (s.options || []).map((o) => `<div class="card flat stack" style="gap:6px"><div class="row" style="justify-content:space-between"><b>${esc(o.key)} · ${esc(o.angle || '')}</b>${o.key === s.chosen ? chip('Choisi', 'good') : ''}</div>
      <div style="font-size:13.5px">${esc(o.title || '')}</div><div class="muted" style="font-size:13px">${esc(o.hook || '')}</div>${o.score ? `<div class="muted mono">score ${esc(o.score)}</div>` : ''}</div>`).join('');
    return `<div class="grid g3"><div class="card">${gauge('MATCH', m.match, tone(m.match))}</div><div class="card">${gauge('QUALITY', m.quality, tone(m.quality), 'Mots-clés REQUIRED prouvés par des faits')}</div><div class="card">${gauge('RISK', m.risk, tone(100 - m.risk), 'Risque de rejet (plus bas = mieux)')}</div></div>
      <div class="split"><div class="stack">
        <div class="card"><h3 class="h3">Couverture des mots-clés</h3><div class="row" style="gap:6px">${cov || '<span class="muted">Aucun mot-clé détecté.</span>'}</div></div>
        <div class="card"><h3 class="h3">Ce que le recruteur veut vraiment</h3><div class="grid g2"><div><b style="font-size:13px">EXPLICIT</b>${list((a.recruiter_wants || {}).explicit)}</div><div><b style="font-size:13px">INFERRED</b>${list((a.recruiter_wants || {}).inferred)}</div></div></div>
        <div class="card"><h3 class="h3">Stratégie · ${esc(s.best.ats_mode)} · ${esc(s.best.design_profile)}</h3><p style="margin:0 0 6px"><b>${esc(s.best.title)}</b></p><p style="margin:0 0 10px">${esc(s.best.hook || '')}</p>
          <p class="muted" style="margin:0 0 10px;font-size:13.5px">${esc(s.best.why || s.comparison || '')}</p><div class="grid g3">${opts}</div></div>
      </div><div class="stack">
        <div class="card"><h3 class="h3">Sous-scores</h3><div class="stack" style="gap:6px">${subs}</div></div>
        <div class="card"><h3 class="h3">Pourquoi ça colle</h3>${list(m.why_fit)}</div>
        <div class="card"><h3 class="h3">Manques (à ne pas écrire)</h3>${list(m.missing, 'requirement')}</div>
        <div class="card"><h3 class="h3">Risques</h3>${list(p.risks)}</div>
        <div class="card"><h3 class="h3">Prochaine action</h3><p style="margin:0">${esc(p.next_action)}</p></div>
      </div></div>`;
  }

  function cvScoreCards(p, e) {
    const cv = e.doc; const ai = e.critique && e.critique.ai && e.critique.ai.scores ? e.critique.ai.scores : {};
    const js = (k) => (ai[k] && ai[k].score !== undefined ? Number(ai[k].score) * 10 : null);
    const jw = (k) => (ai[k] ? `${ai[k].why || ''}` : '');
    const textN = E.norm(cv.lines.map((l) => l.text).join(' '));
    const wanted = p.match.coverage.filter((c) => c.covered && c.priority !== 'NICE');
    const present = wanted.filter((c) => E.supportedBy(c.term, textN));
    const kw = wanted.length ? (100 * present.length) / wanted.length : 70;
    const ats = Math.round(0.75 * kw + (e.qa && e.qa.ok ? 25 : 0));
    const bullets = E.sectionLines(cv, 'experience'); const strong = bullets.filter((l) => E.extractNumbers(l.text).length || p.match.coverage.some((c) => c.covered && E.supportedBy(c.term, E.norm(l.text))));
    const content = js('HIRING_MANAGER') ?? Math.round(bullets.length ? (100 * strong.length) / bullets.length : 50);
    const avgLen = bullets.length ? bullets.reduce((n, l) => n + l.text.length, 0) / bullets.length : 0;
    const read = js('RECRUITER') ?? Math.round(avgLen && avgLen <= 110 ? 88 : avgLen <= 130 ? 72 : 55);
    const offerTerms = p.match.coverage.filter((c) => c.covered);
    const mirrored = offerTerms.filter((c) => E.supportedBy(c.term, textN)).length;
    const pers = Math.round((offerTerms.length ? 70 * mirrored / offerTerms.length : 40) + (E.norm(E.sectionLines(cv, 'headline').map((l) => l.text).join(' ')).includes(E.norm(p.analysis.job_title).split(' ')[0] || '~') ? 30 : 0));
    const designOk = (E.sector(p.analysis.sector_id).cv_style || {}).design === cv.design_profile || cv.design_profile === 'hybrid_modern';
    const design = js('DESIGN') ?? (designOk ? 85 : 65);
    const role = js('MATCH') !== null ? Math.round((js('MATCH') + p.match.scores.role) / 2) : p.match.scores.role;
    const cards = [
      ['CONTENT', content, jw('HIRING_MANAGER') || `${strong.length}/${bullets.length} puces chiffrées ou alignées sur l'offre`, e.critique && e.critique.ai ? 'Juge HIRING_MANAGER' : 'Calcul déterministe'],
      ['ROLE_FIT', role, jw('MATCH') || `Rôle ${pct(p.match.scores.role)} · secteur ${pct(p.match.scores.sector)}`, 'Matching + juge MATCH'],
      ['ATS_FIT', ats, `${present.length}/${wanted.length} mots-clés prouvés présents · PDF ${e.qa && e.qa.ok ? 'lisible' : 'à vérifier'}`, `Extraction pdf.js : REQUIRED ${e.qa ? e.qa.required_found : '—'}`],
      ['READABILITY', read, jw('RECRUITER') || `Puces de ${Math.round(avgLen)} caractères en moyenne`, 'Juge RECRUITER / densité'],
      ['PERSONALIZATION', Math.min(100, pers), `${mirrored}/${offerTerms.length} termes de l'offre repris quand un fait le prouve`, 'Titre aligné sur l\'intitulé'],
      ['DESIGN_FIT', design, jw('DESIGN') || `${cv.design_profile} pour « ${E.sector(p.analysis.sector_id).name} »`, `Photo ${cv.photo_mode} (règle pays : ${E.country(p.analysis.country).photo || '—'})`],
      ['FACTUALITY', e.report.factuality, `${e.report.traced}/${e.report.total} lignes tracées · ${(cv.removed_lines || []).length} ligne(s) supprimée(s)`, 'Validateur déterministe claim → evidence'],
    ];
    return `<div class="grid g2">${cards.map(([k, v, why, proof]) => `<div class="card flat">${gauge(k, v, tone(v))}<div style="font-size:13px;margin-top:6px">${esc(why)}</div><div class="muted" style="font-size:12px;margin-top:3px">Preuve : ${esc(proof)}</div></div>`).join('')}</div>`;
  }

  function diffLines(A, B) {
    const a = new Map(A.lines.map((l) => [l.id, l])); const b = new Map(B.lines.map((l) => [l.id, l]));
    const cls = new Map();
    for (const [id, l] of b) cls.set(id, !a.has(id) ? 'diff-add' : a.get(id).text !== l.text ? 'diff-mod' : '');
    const removed = [...a.values()].filter((l) => !b.has(l.id));
    return { cls, removed };
  }

  function packCv(p) {
    const idx = S.cvIndex === null || !p.cvs[S.cvIndex] ? p.cv_index : S.cvIndex; const e = p.cvs[idx]; const cv = e.doc;
    const versions = p.cvs.map((x, i) => `<button class="btn sm ${i === idx ? 'primary' : ''}" data-act="cv-version" data-arg="${i}">${esc(x.label || `V${x.v}`)}</button>`).join('');
    const cmp = S.compareWith !== null && p.cvs[S.compareWith] && S.compareWith !== idx ? p.cvs[S.compareWith] : null;
    let compareHtml = '';
    if (cmp) {
      const d = diffLines(cmp.doc, cv);
      compareHtml = `<div class="card"><h3 class="h3">Différences ${esc(cmp.label)} → ${esc(e.label)}</h3>
        <div class="list">${cv.lines.filter((l) => d.cls.get(l.id)).map((l) => `<div class="item"><span class="grow ${d.cls.get(l.id)}">${esc(l.text)}</span><span class="fid">${esc(l.id)}</span></div>`).join('')}
        ${d.removed.map((l) => `<div class="item"><span class="grow diff-del">${esc(l.text)}</span><span class="fid">${esc(l.id)}</span></div>`).join('') || ''}</div>
        ${!cv.lines.some((l) => d.cls.get(l.id)) && !d.removed.length ? '<p class="muted" style="margin:0">Contenu identique (seul le rendu diffère).</p>' : ''}</div>`;
    }
    const qa = e.qa || {};
    const rejected = e.report.rejected_ids || [];
    return `<div class="split"><div class="stack">
        <div class="row" style="justify-content:space-between"><div class="row">${versions}</div><div class="row">
          <select class="select" style="width:auto" data-change="compare" aria-label="Comparer avec"><option value="">Comparer avec…</option>${p.cvs.map((x, i) => (i !== idx ? `<option value="${i}" ${S.compareWith === i ? 'selected' : ''}>${esc(x.label)}</option>` : '')).join('')}</select>
          <button class="btn sm" data-act="real-pdf">PDF réel</button><button class="btn sm primary" data-act="dl-cv">Télécharger le PDF</button></div></div>
        <div class="sheet-host" id="cv-sheet">${sheetHTML(cv, { rejected })}</div>
        <div id="real-pdf-host"></div>
        <p class="muted" style="font-size:12.5px;margin:0">Survolez une ligne pour voir les faits qui la prouvent. ${qa.pages ? `PDF : ${qa.pages} page(s), police min. ${qa.min_font_pt || '—'} pt, REQUIRED ${qa.required_found}.` : ''}</p>
        ${compareHtml}
      </div><div class="stack">
        ${cvScoreCards(p, e)}
        <div class="card stack"><h3 class="h3">Retouches ciblées (nouvelle version)</h3>
          <div class="field"><label for="f-headline">Titre</label><div class="row"><input id="f-headline" class="input" style="flex:1" value="${esc((E.sectionLines(cv, 'headline')[0] || {}).text || '')}"><button class="btn sm" data-act="set-headline">Appliquer</button></div></div>
          <div class="row"><button class="btn sm" data-act="rewrite-summary" ${AI.ok() ? '' : 'disabled'}>Réécrire le résumé</button><button class="btn sm" data-act="regen-feedback" ${AI.ok() ? '' : 'disabled'}>Régénérer avec mes retours</button></div>
          <div class="field"><label>Mode et design</label><div class="seg">${[['ats_classic', 'ATS'], ['hybrid_modern', 'Hybride'], ['human_premium', 'Humain']].map(([k, l]) => `<button data-act="set-design" data-arg="${k}" aria-pressed="${cv.design_profile === k}">${l}</button>`).join('')}</div></div>
          <div class="field"><label>Couleur d'accent</label><div class="row">${['#1C5D7A', '#2F4858', '#6B4E2E', '#3D5A40', '#5B3A6B'].map((c) => `<button class="btn sm" data-act="set-color" data-arg="${c}" aria-label="Couleur ${c}" style="width:34px;background:${c};border-color:${c}"></button>`).join('')}</div></div>
          <div class="field"><label>Ordre des expériences</label>${cv.experiences.map((b, i) => `<div class="row" style="justify-content:space-between"><span style="font-size:13.5px">${esc(b.title)} · ${esc(b.company)}</span><span class="row"><button class="btn sm ghost" data-act="exp-up" data-arg="${i}" ${i === 0 ? 'disabled' : ''} aria-label="Monter">↑</button><button class="btn sm ghost" data-act="exp-down" data-arg="${i}" ${i === cv.experiences.length - 1 ? 'disabled' : ''} aria-label="Descendre">↓</button></span></div>`).join('')}</div>
          <div class="row"><span class="muted" style="font-size:13px">Photo : ${S.profile.facts.some((f) => f.kind === 'media' && E.usable(f)) ? '' : 'aucune photo dans le profil (mode OFF)'}</span></div>
        </div>
        ${feedbackBox(p, 'cv', idx)}
        ${(cv.removed_lines || []).length ? `<div class="card"><h3 class="h3">Lignes supprimées (non prouvées)</h3><div class="list">${cv.removed_lines.map((r) => `<div class="item"><span class="grow"><span class="t" style="white-space:normal;display:block">${esc(r.text)}</span><span class="s" style="display:block">${esc((r.reasons || []).join(' ; '))}</span></span></div>`).join('')}</div></div>` : ''}
        ${e.critique && e.critique.ai && e.critique.ai.ten_second ? `<div class="card"><h3 class="h3">Test des 10 secondes · ${esc(e.critique.ai.ten_second.verdict || '')}</h3><p style="margin:0;font-size:13.5px">${esc(['identity', 'target', 'level', 'value'].map((k) => e.critique.ai.ten_second[k]).filter(Boolean).join(' · '))}</p></div>` : ''}
      </div></div>`;
  }

  function feedbackBox(p, doc, idx) {
    const els = ['titre', 'accroche', 'expériences', 'compétences', 'ordre', 'couleurs', 'photo', 'design', 'longueur', 'ATS', 'personnalisation', 'autre'];
    const mine = S.feedback.filter((f) => f.pack_id === p.id && f.doc === doc);
    return `<div class="card stack"><h3 class="h3">Votre avis (${mine.length})</h3>
      <div class="row"><select id="fb-el" class="select" style="width:auto">${els.map((x) => `<option>${x}</option>`).join('')}</select>
      <div class="seg">${[[1, '👍'], [0, '😐'], [-1, '👎']].map(([v, l]) => `<button data-act="fb-rate" data-arg="${v}" aria-pressed="${S.fbRate === v}">${l}</button>`).join('')}</div></div>
      <textarea id="fb-comment" class="textarea" style="min-height:64px" placeholder="Ce qui marche, ce qui ne marche pas…"></textarea>
      <div class="row"><button class="btn sm primary" data-act="fb-save" data-arg="${doc}:${idx}">Enregistrer l'avis</button></div>
      ${mine.slice(0, 4).map((f) => `<div class="muted" style="font-size:12.5px">${f.rating === 1 ? '👍' : f.rating === -1 ? '👎' : '😐'} ${esc(f.element)} · ${esc(f.comment || '')}</div>`).join('')}</div>`;
  }

  function packLetter(p) {
    const e = p.letters[p.letter_index]; const P = Pp();
    return `<div class="split"><div class="stack"><div class="row" style="justify-content:flex-end"><button class="btn sm primary" data-act="dl-letter">Télécharger le PDF</button></div>
      ${letterSheetHTML(e.doc, P.value('id.name'), E.contactLines(P), { rejected: e.report.rejected_ids })}</div>
      <div class="stack"><div class="card">${gauge('FACTUALITY', e.report.factuality, tone(e.report.factuality, 99, 90), `${e.report.traced}/${e.report.total} phrases tracées`)}</div>
      <div class="card"><h3 class="h3">Contrôles</h3>${(e.checks || []).length ? `<div class="list">${e.checks.map((c) => `<div class="item"><span class="grow">${esc(c.detail)}</span>${chip(c.severity, c.severity === 'high' ? 'bad' : c.severity === 'medium' ? 'warn' : '')}</div>`).join('')}</div>` : '<p style="margin:0">Entreprise et intitulé présents, au moins 2 éléments propres à l\'annonce, aucune phrase creuse.</p>'}</div>
      <div class="card"><h3 class="h3">Phrases et preuves</h3><div class="list">${e.doc.lines.map((l) => `<div class="item"><span class="grow" style="font-size:13.5px">${esc(l.text)}</span><span class="row" style="gap:4px">${chip(l.kind)}${fids(l.fact_ids)}</span></div>`).join('')}</div></div>
      ${feedbackBox(p, 'letter', p.letter_index)}</div></div>`;
  }

  function packQuestions(p) {
    if (!p.answers.length) return '<div class="card empty">Aucune question fournie pour ce pack.</div>';
    const toneOf = { HIGH: 'good', MEDIUM: 'accent', LOW: 'warn', BLOCKED: 'bad' };
    return `<div class="card"><div class="list">${p.answers.map((x, i) => `<div class="item" style="align-items:flex-start"><span class="grow"><span class="t" style="white-space:normal">${esc(x.question)}</span>
      <span class="row" style="gap:6px;margin:4px 0">${chip(x.type)}${chip(x.confidence, toneOf[x.confidence])}${fids(x.fact_ids)}</span>
      ${x.confidence === 'BLOCKED' ? `<span class="s">${esc(x.ask_user)}</span><div class="row" style="margin-top:6px"><input class="input" id="ans-${i}" placeholder="Votre réponse" value="${esc(x.user_answer || '')}" style="flex:1"><button class="btn sm" data-act="answer-save" data-arg="${i}">Enregistrer</button></div>` : `<span style="font-size:14px">${esc(x.answer)}</span>`}</span></div>`).join('')}</div></div>`;
  }

  function packExport(p) {
    const v = p.versions;
    return `<div class="split"><div class="card stack"><h3 class="h3">Télécharger</h3>
      <div class="row"><button class="btn primary" data-act="dl-cv">CV (PDF)</button><button class="btn" data-act="dl-letter">Lettre (PDF)</button><button class="btn" data-act="dl-zip">Pack complet (ZIP)</button><button class="btn" data-act="dl-json">pack.json</button></div>
      <p class="muted" style="margin:0;font-size:13.5px">Le ZIP contient le CV et la lettre en PDF (texte sélectionnable, lisible par les ATS), pack.json (tout le pack) et pack.md (synthèse lisible). ${p.status === 'DRAFT' ? 'Statut BROUILLON : les PDF portent le tampon tant que le profil n\'est pas validé.' : ''}</p></div>
      <div class="card"><h3 class="h3">Versions figées</h3><div class="table-wrap"><table class="t"><tbody>${Object.entries(v).map(([k, x]) => `<tr><th>${esc(k)}</th><td class="mono">${esc(x || '—')}</td></tr>`).join('')}<tr><th>created_at</th><td class="mono">${esc(p.created_at)}</td></tr><tr><th>provider</th><td>${esc(p.provider)}</td></tr><tr><th>appels IA</th><td>${(p.calls || []).length}</td></tr></tbody></table></div></div></div>`;
  }

  function packCopilot(p) {
    const turns = S.chat.pack === p.id ? S.chat.turns : [];
    return `<div class="card stack" style="max-width:820px"><h3 class="h3">Copilote de candidature</h3><p class="muted" style="margin:0;font-size:13.5px">Questions sur l'offre, l'entretien, l'angle à prendre. Le copilote ne connaît que vos faits.</p>
      <div class="stack" id="chat-log">${turns.map((t) => `<div class="card ${t.role === 'user' ? 'flat' : ''}" style="padding:10px 12px;font-size:14px;white-space:pre-wrap">${esc(t.content)}</div>`).join('')}</div>
      <div class="row"><input id="chat-in" class="input" style="flex:1" placeholder="Ex. Quelles questions préparer pour l'entretien ?"><button class="btn primary" data-act="chat-send" ${AI.ok() && !S.chat.busy ? '' : 'disabled'}>Envoyer</button></div></div>`;
  }

  V.lab = () => {
    const packs = S.packs.filter((p) => p.cvs && p.cvs.length);
    return `<div class="page"><div class="stack"><h1 class="title">Training Lab</h1><p class="lede">Annonce → CV → votre avis → V2 → comparaison → score. Ouvrez un pack, donnez votre avis dans CV Studio puis « Régénérer avec mes retours ».</p></div>
      <div class="card">${packs.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Pack</th><th>Versions</th><th>Avis</th><th>Factualité</th><th>Points</th><th></th></tr></thead><tbody>
      ${packs.map((p) => `<tr><td>${esc(p.analysis.job_title)}<div class="muted" style="font-size:12px">${esc(p.analysis.company)} · ${fmtDate(p.created_at)}</div></td><td>${p.cvs.map((c) => esc(c.label)).join(', ')}</td>
      <td class="num">${S.feedback.filter((f) => f.pack_id === p.id).length}</td><td class="num">${pct(p.scores.factuality_cv)} %</td><td class="num">${(p.scores.points || {}).total ?? '—'}</td>
      <td><button class="btn sm" data-act="open-pack-cv" data-arg="${esc(p.id)}">Ouvrir</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Générez un premier pack pour démarrer l\'entraînement.</div>'}</div></div>`;
  };

  V.arene = () => {
    const pair = S.arenaPair; const votes = S.arena; const judged = votes.filter((v) => v.judge && v.choice);
    const agree = judged.filter((v) => v.judge.winner === v.choice).length;
    const b = S.bench;
    return `<div class="page"><div class="stack"><h1 class="title">Benchmark et arène à l'aveugle</h1><p class="lede">Deux CV pour la même offre, sans étiquette. Vous choisissez, vous dites pourquoi, puis l'origine est révélée. Votre préférence est le signal le plus fort.</p></div>
      <div class="grid g3"><div class="card kpi"><span class="v">${votes.length}</span><span class="l">Votes</span></div><div class="card kpi"><span class="v">${judged.length ? `${Math.round((100 * agree) / judged.length)} %` : '—'}</span><span class="l">Accord juge IA ↔ vous (${judged.length} paire(s))</span></div>
        <div class="card kpi"><span class="v">${b ? pct(b.new_avg) : '—'}</span><span class="l">Score benchmark du moteur ${b ? esc(b.engine_v) : ''} (ancien : ${b ? pct(b.legacy_avg) : '—'})</span></div></div>
      <div class="card stack">${pair ? arenaPairHtml(pair) : `<div class="row" style="justify-content:space-between"><span class="muted">${arenaSources().length} paire(s) disponible(s) : versions d'un même pack et comparaisons ancien générateur ↔ PAI.</span><button class="btn primary" data-act="arena-new" ${arenaSources().length ? '' : 'disabled'}>Nouvelle paire</button></div>`}</div>
      ${b ? benchTable(b) : '<div class="card muted">Aucun résultat de benchmark importé.</div>'}
      ${votes.length ? `<div class="card"><h3 class="h3">Historique des votes</h3><div class="list">${votes.slice(0, 20).map((v) => `<div class="item"><span class="grow"><span class="t">${esc(v.title || '')}</span><span class="s">Choix : ${esc(v.choice_label || v.choice)} · ${esc(v.reason || '')}${v.judge ? ` · juge : ${esc(v.judge.winner_label || v.judge.winner)}` : ''}</span></span><span class="s">${fmtDate(v.created_at)}</span></div>`).join('')}</div></div>` : ''}</div>`;
  };
  function arenaSources() {
    const out = [];
    for (const p of S.packs) if (p.cvs && p.cvs.length > 1) for (let i = 1; i < p.cvs.length; i++) out.push({ kind: 'versions', id: `${p.id}:0:${i}`, title: `${p.analysis.job_title} · ${p.analysis.company}`, offer: p.analysis.job_title,
      a: { label: p.cvs[0].label, text: E.cvPlainText(p.cvs[0].doc).replace(/\[[^\]]+\] /g, '') }, b: { label: p.cvs[i].label, text: E.cvPlainText(p.cvs[i].doc).replace(/\[[^\]]+\] /g, '') } });
    for (const bp of S.benchPairs || []) out.push({ kind: 'legacy', id: bp.id, title: `${bp.title} (offre SYNTHETIC)`, offer: bp.title, a: { label: 'Ancien générateur (legacy)', text: bp.legacy_text }, b: { label: 'PAI (moteur déterministe)', text: bp.pai_text } });
    return out;
  }
  function arenaPairHtml(pair) {
    const X = pair.flip ? pair.b : pair.a; const Y = pair.flip ? pair.a : pair.b;
    const box = (k, d) => `<div class="card flat"><h3 class="h3">CV « ${k} »</h3><pre style="white-space:pre-wrap;font:13px/1.45 var(--f-body);margin:0;max-height:560px;overflow:auto">${esc(d.text)}</pre></div>`;
    return `<div class="row" style="justify-content:space-between"><b>${esc(pair.title)}</b>${pair.revealed ? chip(`X = ${X.label} · Y = ${Y.label}`, 'accent') : chip('À l\'aveugle')}</div>
      <div class="grid g2">${box('X', X)}${box('Y', Y)}</div>
      ${pair.revealed ? `<div class="row"><button class="btn" data-act="arena-judge" ${AI.ok() ? '' : 'disabled'}>Demander l'avis du juge IA (2 ordres)</button><button class="btn primary" data-act="arena-new">Paire suivante</button>${pair.judge ? chip(`Juge : ${pair.judge.winner_label}`, 'accent') : ''}</div>`
    : `<div class="field"><label for="arena-reason">Pourquoi ?</label><input id="arena-reason" class="input" placeholder="Plus clair, plus concret, mieux ciblé…"></div>
      <div class="row"><button class="btn primary" data-act="arena-vote" data-arg="X">X est meilleur</button><button class="btn primary" data-act="arena-vote" data-arg="Y">Y est meilleur</button><button class="btn" data-act="arena-vote" data-arg="TIE">Égalité</button></div>`}`;
  }
  function benchTable(b) {
    return `<div class="card"><h3 class="h3">Benchmark déterministe · ${esc(b.n)} offres (${esc(b.synthetic ? 'SYNTHETIC' : 'réelles')}) · ${fmtDate(b.created_at)}</h3>
      <div class="table-wrap"><table class="t"><thead><tr><th>Offre</th><th class="num">Ancien</th><th class="num">PAI</th><th>Factualité (ancien / PAI)</th><th>Mots-clés couverts (ancien / PAI)</th></tr></thead><tbody>
      ${(b.rows || []).map((r) => `<tr><td>${esc(r.title)}</td><td class="num">${pct(r.legacy_score)}</td><td class="num"><b>${pct(r.pai_score)}</b></td><td>${pct(r.legacy_factuality)} / ${pct(r.pai_factuality)} %${r.legacy_forbidden ? ` · <span style="color:var(--bad)">${r.legacy_forbidden} fait(s) interdit(s) chez l'ancien</span>` : ''}</td><td>${pct(r.legacy_kw)} / ${pct(r.pai_kw)} %</td></tr>`).join('')}</tbody></table></div>
      <p class="muted" style="margin:10px 0 0;font-size:13px">${esc(b.conclusion || '')}</p></div>`;
  }

  V.apprentissage = () => {
    const fb = S.feedback; const min = ((D.scoring || {}).learning || {}).min_feedback_for_trend || 5;
    const byEl = {}; fb.forEach((f) => { const k = f.element; byEl[k] = byEl[k] || { n: 0, pos: 0, neg: 0 }; byEl[k].n++; if (f.rating === 1) byEl[k].pos++; if (f.rating === -1) byEl[k].neg++; });
    const byCtx = {}; fb.forEach((f) => { const k = `${(f.context || {}).sector || '—'} · ${f.element}`; byCtx[k] = byCtx[k] || { n: 0, pos: 0 }; byCtx[k].n++; if (f.rating === 1) byCtx[k].pos++; });
    const props = (S.rules.proposals || []).filter((r) => r.status === 'proposed');
    return `<div class="page"><div class="stack"><h1 class="title">Apprentissage</h1><p class="lede">Le moteur propose des règles à partir de vos retours ; vous les acceptez ou les refusez. Rien n'est appliqué automatiquement, et la taille de l'échantillon est toujours affichée.</p></div>
      <div class="grid g4"><div class="card kpi"><span class="v">${fb.length}</span><span class="l">Retours</span></div><div class="card kpi"><span class="v">${fb.length ? Math.round((100 * fb.filter((f) => f.rating === 1).length) / fb.length) : '—'}${fb.length ? ' %' : ''}</span><span class="l">Positifs</span></div>
        <div class="card kpi"><span class="v">${fb.length ? Math.round((100 * fb.filter((f) => f.rating === -1).length) / fb.length) : '—'}${fb.length ? ' %' : ''}</span><span class="l">Négatifs</span></div><div class="card kpi"><span class="v">${(S.rules.accepted || []).length}</span><span class="l">Règles acceptées</span></div></div>
      <div class="split"><div class="card"><h3 class="h3">Patterns par contexte (seuil : ${min} retours)</h3>${Object.keys(byCtx).length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Contexte</th><th class="num">n</th><th class="num">👍</th><th>Statut</th></tr></thead><tbody>
        ${Object.entries(byCtx).sort((x, y) => y[1].n - x[1].n).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v.n}</td><td class="num">${Math.round((100 * v.pos) / v.n)} %</td><td>${v.n >= min ? chip('OBSERVED', 'accent') : chip('INSUFFICIENT DATA', 'warn')}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted" style="margin:0">Aucun retour pour l\'instant.</p>'}
        <p class="muted" style="font-size:12.5px;margin:10px 0 0">Corrélation ≠ causalité. Une conclusion sur les résultats réels demande au moins ${((D.scoring || {}).learning || {}).min_comparable_applications_for_conclusion || 20} candidatures comparables.</p></div>
        <div class="stack"><div class="card stack"><h3 class="h3">Règles proposées</h3><button class="btn" data-act="propose-rules" ${AI.ok() && fb.length ? '' : 'disabled'}>Analyser mes retours</button>
          ${props.length ? props.map((r) => `<div class="card flat stack" style="gap:6px"><b style="font-size:14px">${esc(r.rule_text)}</b><span class="muted" style="font-size:12.5px">${esc([r.sector, r.role, r.context].filter(Boolean).join(' · '))} · n = ${esc(r.n_cases)} · ${esc(r.confidence)}</span>
            <div class="row"><button class="btn sm primary" data-act="rule-accept" data-arg="${esc(r.id)}">Accepter</button><button class="btn sm" data-act="rule-refuse" data-arg="${esc(r.id)}">Refuser</button></div></div>`).join('') : '<p class="muted" style="margin:0">Aucune proposition en attente.</p>'}</div>
          <div class="card"><h3 class="h3">Règles acceptées</h3>${(S.rules.accepted || []).length ? `<div class="list">${S.rules.accepted.map((r) => `<div class="item"><span class="grow" style="font-size:13.5px">${esc(r.rule_text)}</span><button class="btn sm ghost danger" data-act="rule-remove" data-arg="${esc(r.id)}">Retirer</button></div>`).join('')}</div>` : '<p class="muted" style="margin:0">Aucune.</p>'}</div>
          <div class="card"><h3 class="h3">Par élément</h3>${Object.keys(byEl).length ? Object.entries(byEl).map(([k, v]) => `<div class="sub"><span class="muted">${esc(k)}</span><div class="bar ${tone((100 * v.pos) / v.n)}"><i style="width:${(100 * v.pos) / v.n}%"></i></div><span class="v">${v.n}</span></div>`).join('') : '<p class="muted" style="margin:0">—</p>'}</div></div></div></div>`;
  };

  V.jobagent = () => {
    const imp = S.jobImport;
    return `<div class="page"><div class="stack"><h1 class="title">Learn from JobAgent</h1><p class="lede">IMPORT → REVIEW → ACCEPT, élément par élément. Aucun import silencieux : chaque élément accepté entre dans le profil en statut UNVERIFIED, avec sa provenance, et vous le confirmez ensuite.</p></div>
      <div class="notice warn">Statut : <b>PROFILE_IMPORT_REQUIRED</b>. Le lien /profil du JobAgent (trycloudflare, temporaire) n'était pas accessible depuis l'environnement de construction. Importez un export JSON, texte ou Markdown produit par le JobAgent.</div>
      <div class="card stack"><div class="row"><label class="btn primary" for="f-ja">Importer un fichier</label><input id="f-ja" type="file" accept=".json,.txt,.md,application/json,text/plain" class="sr" data-change="ja-file"><span class="muted" style="font-size:13px">JSON, TXT ou MD · lu dans votre navigateur</span></div></div>
      ${imp ? `<div class="card stack"><h3 class="h3">${esc(imp.name)} · ${imp.items.length} élément(s) détecté(s)</h3><div class="list">${imp.items.map((it, i) => `<div class="item" style="align-items:flex-start"><input type="checkbox" id="ja-${i}" ${it.pick ? 'checked' : ''} data-change="ja-pick" data-arg="${i}" aria-label="Sélectionner">
        <span class="grow"><span class="t" style="white-space:normal">${esc(it.text)}</span><span class="s mono">${esc(it.path)}</span></span>
        <select class="select" style="width:auto" data-change="ja-kind" data-arg="${i}" aria-label="Type">${KIND_ORDER.filter((k) => !['identity', 'contact'].includes(k)).map((k) => `<option value="${k}" ${it.kind === k ? 'selected' : ''}>${KIND_LABEL[k]}</option>`).join('')}</select></div>`).join('')}</div>
        <div class="row"><button class="btn primary" data-act="ja-accept">Ajouter la sélection au profil (UNVERIFIED)</button><button class="btn" data-act="ja-cancel">Annuler</button></div></div>` : ''}
      ${S.jobagent.length ? `<div class="card"><h3 class="h3">Historique des imports</h3><div class="list">${S.jobagent.map((j) => `<div class="item"><span class="grow"><span class="t">${esc(j.name)}</span><span class="s">${j.accepted} accepté(s) sur ${j.total} · empreinte ${esc(j.hash)}</span></span><span class="s">${fmtDate(j.created_at)}</span></div>`).join('')}</div></div>` : ''}</div>`;
  };

  V.profil = () => {
    const p = S.profile;
    if (!p) return `<div class="page"><h1 class="title">Profil</h1><div class="card stack"><p style="margin:0">Aucun Master Profile. Importez un export JSON (depuis PAI ou le serveur PAI : <span class="mono">python -m pai export-profile</span>).</p>
      <div class="row"><label class="btn primary" for="f-prof">Importer un profil JSON</label><input id="f-prof" type="file" accept="application/json,.json" class="sr" data-change="profile-file"></div></div></div>`;
    const P = Pp(); const groups = {}; p.facts.forEach((f) => (groups[f.kind] = groups[f.kind] || []).push(f));
    const toConfirm = p.facts.filter((f) => f.needs_confirmation && E.usable(f));
    const row = (f) => S.editFact === f.id
      ? `<div class="item" style="align-items:flex-start"><span class="grow stack" style="gap:6px"><textarea id="ef-text" class="textarea" style="min-height:60px">${esc(f.text)}</textarea>
          <div class="row"><select id="ef-status" class="select" style="width:auto">${['CONFIRMED', 'IMPORTED', 'INFERRED', 'UNVERIFIED', 'FORBIDDEN'].map((s) => `<option ${f.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select>
          <button class="btn sm primary" data-act="fact-save" data-arg="${esc(f.id)}">Enregistrer</button><button class="btn sm" data-act="fact-cancel">Annuler</button></div></span></div>`
      : `<div class="item" style="align-items:flex-start"><span class="grow"><span style="font-size:14px">${esc(f.text)}</span><span class="s" style="display:block"><span class="fid">${esc(f.id)}</span> · ${esc(f.source)}${f.note ? ` · ${esc(f.note)}` : ''}</span></span>
        <span class="row" style="gap:6px">${f.needs_confirmation ? chip('à confirmer', 'warn') : ''}${statusChip(f.status)}<button class="btn sm ghost" data-act="fact-edit" data-arg="${esc(f.id)}" aria-label="Modifier ${esc(f.id)}">Modifier</button></span></div>`;
    return `<div class="page"><div class="row" style="justify-content:space-between;align-items:flex-start"><div class="stack" style="gap:6px"><h1 class="title">Master Profile</h1>
        <div class="row">${chip(`v${p.version}`, 'accent')} ${p.validated ? chip(`Validé le ${fmtDate(p.validated_at)}`, 'good') : chip('Non validé', 'warn')} ${chip(`${P.usableFacts().length} faits utilisables`)} <span class="mono muted">${esc(profileTag(p))}</span></div></div>
        <div class="row"><button class="btn primary" data-act="profile-validate" ${p.validated || conflicts(p).length ? 'disabled' : ''}>Valider le profil v${p.version}</button>
          <button class="btn sm" data-act="profile-export" data-arg="json">JSON</button><button class="btn sm" data-act="profile-export" data-arg="csv">CSV</button><button class="btn sm" data-act="profile-export" data-arg="md">MD</button>
          <label class="btn sm" for="f-prof">Importer</label><input id="f-prof" type="file" accept="application/json,.json" class="sr" data-change="profile-file"></div></div>
      ${conflicts(p).length ? `<div class="notice bad">${conflicts(p).length} conflit(s) à résoudre avant validation.</div>` : ''}
      ${(p.review_queue || []).length ? `<div class="card"><h3 class="h3">File REVIEW (${p.review_queue.length})</h3><div class="list">${p.review_queue.map((r, i) => { const f = P.fact(r.fact_id); return `<div class="item" style="align-items:flex-start"><span class="grow"><span style="font-size:14px">${esc(r.reason)}</span><span class="s" style="display:block"><span class="fid">${esc(r.fact_id)}</span>${f ? ` · ${esc(f.text)}` : ''}</span></span>
        <span class="row" style="gap:6px">${chip(r.severity, r.severity === 'conflict' ? 'bad' : r.severity === 'warning' ? 'warn' : '')}${f && f.status !== 'FORBIDDEN' ? `<button class="btn sm" data-act="review-confirm" data-arg="${i}">Confirmer</button><button class="btn sm" data-act="review-reject" data-arg="${i}">Écarter</button>` : `<button class="btn sm" data-act="review-dismiss" data-arg="${i}">Compris</button>`}</span></div>`; }).join('')}</div></div>` : ''}
      ${toConfirm.length ? `<div class="card"><h3 class="h3">Chiffres importés à confirmer (${toConfirm.length})</h3><div class="list">${toConfirm.map((f) => `<div class="item"><span class="grow" style="font-size:14px">${esc(f.text)} <span class="fid">${esc(f.id)}</span></span><button class="btn sm primary" data-act="fact-confirm" data-arg="${esc(f.id)}">Confirmer</button><button class="btn sm" data-act="fact-edit" data-arg="${esc(f.id)}">Corriger</button></div>`).join('')}</div></div>` : ''}
      <div class="split"><div class="stack">${KIND_ORDER.filter((k) => groups[k]).map((k) => `<div class="card"><h3 class="h3">${KIND_LABEL[k]} (${groups[k].length})</h3><div class="list">${groups[k].map(row).join('')}</div></div>`).join('')}</div>
        <div class="stack"><div class="card stack"><h3 class="h3">Ajouter un fait (CONFIRMED)</h3><div class="field"><label for="nf-kind">Type</label><select id="nf-kind" class="select">${KIND_ORDER.map((k) => `<option value="${k}">${KIND_LABEL[k]}</option>`).join('')}</select></div>
          <div class="field"><label for="nf-parent">Rattaché à (facultatif)</label><select id="nf-parent" class="select"><option value="">—</option>${P.experiences().map((e) => `<option value="${esc(e.id)}">${esc(e.data.title)} · ${esc(e.data.company)}</option>`).join('')}</select></div>
          <div class="field"><label for="nf-text">Énoncé exact</label><textarea id="nf-text" class="textarea" style="min-height:70px" placeholder="Ex. Bachelor REM — École X (2021-2024)"></textarea></div><button class="btn primary" data-act="fact-add">Ajouter</button></div>
          <div class="card"><h3 class="h3">Données manquantes (UNKNOWN)</h3><ul style="margin:0;padding-left:18px">${(p.unknowns || []).map((u) => `<li style="font-size:13.5px">${esc(u)}</li>`).join('')}</ul></div>
          <div class="card"><h3 class="h3">Historique</h3><div class="list">${(p.history || []).slice(-8).reverse().map((h) => `<div class="item"><span class="grow" style="font-size:13px">${esc(h.action)} · ${esc(h.detail)}</span><span class="s">${fmtTime(h.at)}</span></div>`).join('')}</div></div></div></div></div>`;
  };

  V.versions = () => `<div class="page"><h1 class="title">Versions</h1>
    <div class="grid g3"><div class="card kpi"><span class="v mono" style="font-size:20px">${esc(D.version.engine)}</span><span class="l">engine_v</span></div><div class="card kpi"><span class="v mono" style="font-size:20px">${esc(D.version.rules)}</span><span class="l">rules_v</span></div><div class="card kpi"><span class="v mono" style="font-size:20px">${esc(D.version.prompts)}</span><span class="l">prompt_v</span></div></div>
    <div class="split"><div class="card"><h3 class="h3">Versions validées du profil</h3>${S.profileVersions.length ? `<div class="list">${S.profileVersions.map((v) => `<div class="item"><span class="grow"><span class="t">v${v.version}</span><span class="s">${esc(v.tag || '')} · ${(v.facts || []).length} faits</span></span><span class="s">${fmtDate(v.validated_at)}</span></div>`).join('')}</div>` : '<p class="muted" style="margin:0">Aucune version validée pour l\'instant.</p>'}</div>
    <div class="card"><h3 class="h3">Prompts</h3><div class="table-wrap"><table class="t"><tbody>${Object.entries(D.prompts).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td class="num mono">v${v.version}</td></tr>`).join('')}</tbody></table></div></div></div>
    <div class="card"><h3 class="h3">Packs</h3><div class="table-wrap"><table class="t"><thead><tr><th>Pack</th><th>profile_v</th><th>cv_v</th><th>letter_v</th><th>engine_v</th><th>prompt_v</th><th>rules_v</th></tr></thead><tbody>
    ${S.packs.map((p) => `<tr><td>${esc(p.analysis.job_title)}</td>${['profile_v', 'cv_v', 'letter_v', 'engine_v', 'prompt_v', 'rules_v'].map((k) => `<td class="mono">${esc(p.versions[k] || '—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div></div>`;

  V.reglages = () => {
    const P = Pp(); const lim = S.aiLimits;
    const todo = ['Clé API Anthropic : seulement pour le serveur PAI auto-hébergé (PAI Studio n\'en a pas besoin).', 'Accès SSH au serveur Oracle 24/7 (déploiement docker compose « pai »).',
      'Domaine géré sur Cloudflare (tunnel nommé) ou compte Tailscale (Funnel) pour l\'URL stable du serveur.', 'Export JSON du JobAgent ou nouvelle URL /profil (le lien trycloudflare a expiré ou est bloqué).',
      'Photo professionnelle (fond neutre, cadrage buste).', 'Anciens CV et lettres en PDF, pour le benchmark « ancien vs nouveau » sur de vraies offres.', 'Offres réelles (texte collé) pour remplacer les 13 offres SYNTHETIC du benchmark.'];
    return `<div class="page"><h1 class="title">Réglages</h1><div class="split"><div class="stack">
      <div class="card"><h3 class="h3">Intelligence</h3><div class="list">
        <div class="item"><span class="grow">Claude (capacité sample)</span>${S.ai === 'denied' ? chip('Refusé : mode dégradé', 'bad') : S.caps.sample ? chip('Disponible', 'good') : chip('Indisponible', 'warn')}</div>
        <div class="item"><span class="grow">Images (contrôle visuel du PDF en DEEP)</span>${lim && lim.images ? chip('Oui', 'good') : chip('Non', '')}</div>
        <div class="item"><span class="grow">Stockage privé (capacité db)</span>${S.storage === 'db' ? chip('Actif', 'good') : chip('Mémoire seulement : rien n\'est conservé', 'warn')}</div>
        <div class="item"><span class="grow">Téléchargements</span>${S.caps.downloads ? chip('Actif', 'good') : chip('Indisponible', 'warn')}</div></div></div>
      <div class="card"><h3 class="h3">Niveau de modèle par tâche</h3><div class="table-wrap"><table class="t"><tbody>${Object.entries(D.models.artifact_tiers || {}).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div>
        <p class="muted" style="font-size:12.5px;margin:8px 0 0">quick : extraction · default : rédaction · complex : stratégie, critique, jugement. Les appels utilisent votre compte Claude.</p></div></div>
      <div class="stack"><div class="card"><h3 class="h3">À fournir pour le niveau suivant</h3><ul style="margin:0;padding-left:18px">${todo.map((t) => `<li style="font-size:13.5px;margin-bottom:4px">${esc(t)}</li>`).join('')}</ul></div>
        <div class="card stack"><h3 class="h3">Sauvegarde</h3><p class="muted" style="margin:0;font-size:13.5px">Export complet (profil, packs, retours, votes, règles) au format JSON, restaurable dans PAI.</p><button class="btn" data-act="backup" ${P ? '' : 'disabled'}>Exporter tout</button></div></div></div></div>`;
  };

  // ─── Coquille, rendu ───────────────────────────────────────────────────────
  function renderShell() {
    $('#nav').innerHTML = VIEWS.map(([k, l, ic], i) => `${i === 3 ? '<div class="group">Mesurer</div>' : ''}${i === 7 ? '<div class="group">Données</div>' : ''}<button data-act="go" data-arg="${k}">${icon(ic)}<span>${l}</span></button>`).join('');
    $('#tabbar').innerHTML = [['accueil', 'Accueil', 'i-home'], ['nouvelle', 'Nouvelle', 'i-plus'], ['packs', 'Packs', 'i-stack'], ['profil', 'Profil', 'i-user'], ['plus', 'Plus', 'i-more']]
      .map(([k, l, ic]) => `<button data-act="go" data-arg="${k}"><svg aria-hidden="true"><use href="#${ic}"/></svg>${l}</button>`).join('');
    $('#rail-foot').textContent = `moteur ${D.version.engine} · règles ${D.version.rules}`;
  }
  function renderTop() {
    const p = S.profile;
    $('#topbar').innerHTML = `<span class="chip ${S.caps.sample && S.ai !== 'denied' ? 'good' : 'warn'}"><span class="dot"></span>${S.caps.sample && S.ai !== 'denied' ? 'Claude connecté' : 'Mode dégradé (sans IA)'}</span>
      ${p ? `<span class="chip ${p.validated ? 'good' : 'warn'}">Profil v${p.version} · ${p.validated ? 'validé' : 'non validé'}</span>` : '<span class="chip warn">Aucun profil</span>'}
      ${S.run && S.run.status === 'running' ? `<button class="chip accent" data-act="go" data-arg="nouvelle" style="cursor:pointer">Génération en cours…</button>` : ''}
      <span class="spacer"></span><span class="muted" style="font-size:12.5px">${S.storage === 'db' ? 'Données privées enregistrées' : S.storage === 'memory' ? 'Données non conservées' : ''}</span>`;
  }
  function renderToast() { let el = $('#toast'); if (!S.toast) { if (el) el.remove(); return; } if (!el) { el = document.createElement('div'); el.id = 'toast'; el.className = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); } el.textContent = S.toast; }
  let lastView = null;
  function doRender() {
    const view = S.view === 'plus' ? 'plus' : S.view;
    $$('#nav button').forEach((b) => b.setAttribute('aria-current', b.dataset.arg === view || (view === 'pack' && b.dataset.arg === 'packs') ? 'page' : 'false'));
    $$('#tabbar button').forEach((b) => b.setAttribute('aria-current', b.dataset.arg === view || (view === 'pack' && b.dataset.arg === 'packs') || (!TAB_VIEWS.includes(view) && view !== 'pack' && b.dataset.arg === 'plus') ? 'page' : 'false'));
    renderTop();
    const main = $('#main');
    const active = document.activeElement; const activeId = active && active.id; const sel = active && active.selectionStart;
    main.innerHTML = view === 'plus' ? plusView() : (V[view] || V.accueil)();
    if (activeId) { const el = document.getElementById(activeId); if (el && el !== document.body) { el.focus(); try { if (sel !== undefined && sel !== null) el.setSelectionRange(sel, sel); } catch (e) { /* champ sans sélection */ } } }
    if (lastView !== view) { window.scrollTo(0, 0); lastView = view; }
    fitSheets();
  }
  function plusView() {
    return `<div class="page"><h1 class="title">Plus</h1><div class="card"><div class="list">${VIEWS.filter(([k]) => !TAB_VIEWS.includes(k)).map(([k, l, ic]) => `<button class="item" data-act="go" data-arg="${k}">${icon(ic)}<span class="grow">${l}</span></button>`).join('')}</div></div></div>`;
  }

  // ─── Actions ───────────────────────────────────────────────────────────────
  async function mutateProfile(fn, action, detail, keepValidation) {
    const p = clone(S.profile); fn(p);
    if (!keepValidation) { p.version = (p.version || 1) + 1; p.validated = false; p.validated_at = null; }
    await Store.saveProfile(p, action, detail); toast('Profil enregistré.');
  }
  async function newCvVersion(label, mutate) {
    const p = clone(curPack()); const base = p.cvs[S.cvIndex === null ? p.cv_index : S.cvIndex];
    const doc = clone(base.doc); await mutate(doc);
    const report = E.Validator(S.profile, p.offer.text, [p.analysis.job_title, p.analysis.company]).validateLines(doc.lines);
    let qa = base.qa;
    try { const fit = await PDF.cvFitted(doc, E.country(p.analysis.country).max_pages || 1); Object.assign(doc, fit.doc); qa = PDF.qa(fit.info, fit.doc, p.match.coverage.filter((c) => c.covered && c.priority === 'REQUIRED').map((c) => c.term), E.country(p.analysis.country).max_pages || 1); } catch (e) { console.warn(e); }
    p.cvs.push({ v: p.cvs.length + 1, label: `V${p.cvs.length + 1} · ${label}`, created_at: nowIso(), source: doc.source, doc, report, critique: base.critique, qa });
    p.cv_index = p.cvs.length - 1; S.cvIndex = p.cv_index; S.compareWith = p.cvs.length - 2;
    refreshStatus(p); await Store.savePack(p);
    if (!report.perfect) toast(`Nouvelle version : ${report.rejected_ids.length} ligne(s) sans preuve à corriger.`); else toast('Nouvelle version enregistrée.');
  }
  const ACT = {
    go: (el) => { S.view = el.dataset.arg; render(); },
    'open-pack': (el) => { S.packId = el.dataset.arg; lsSet('packId', S.packId); S.view = 'pack'; S.packTab = 'synthese'; S.cvIndex = null; S.compareWith = null; render(); },
    'open-pack-cv': (el) => { ACT['open-pack'](el); S.packTab = 'cv'; render(); },
    'pack-tab': (el) => { S.packTab = el.dataset.arg; render(); },
    mode: (el) => { S.draft.mode = el.dataset.arg; lsSet('mode', S.draft.mode); render(); },
    run: () => { runPipeline(); },
    cancel: () => { if (S.run && S.run.controller) S.run.controller.abort(); },
    example: () => { const off = Object.values(D.examples || {})[0]; if (off) { S.draft.offer = off.text; S.draft.title = off.title; S.draft.company = off.company; S.draft.synthetic = true; render(); toast('Exemple chargé : offre FICTIVE (marquée SYNTHETIC).'); } },
    'cv-version': (el) => { S.cvIndex = Number(el.dataset.arg); render(); },
    'real-pdf': async () => {
      const p = curPack(); const e = p.cvs[S.cvIndex === null ? p.cv_index : S.cvIndex]; const host = $('#real-pdf-host'); if (!host) return;
      host.innerHTML = '<p class="muted">Rendu du PDF réel…</p>';
      try { const bytes = await PDF.build(PDF.cvDef(e.doc)); const canvas = document.createElement('canvas'); host.innerHTML = '<h3 class="h3" style="margin:6px 0">PDF réel (pdf.js)</h3>'; host.appendChild(canvas); await PDF.renderInto(bytes, canvas, host.clientWidth); }
      catch (err) { host.innerHTML = `<div class="notice bad">Rendu impossible : ${esc(err.message || err)}</div>`; }
    },
    'dl-cv': async () => { const p = curPack(); const e = p.cvs[S.cvIndex === null ? p.cv_index : S.cvIndex]; const bytes = await PDF.build(PDF.cvDef(e.doc)); await save(`CV_${slug(p.analysis.company)}_${slug(p.analysis.job_title)}.pdf`, new Blob([bytes], { type: 'application/pdf' })); },
    'dl-letter': async () => { const p = curPack(); const P = Pp(); const e = p.letters[p.letter_index]; const bytes = await PDF.build(PDF.letterDef(e.doc, P.value('id.name'), E.contactLines(P), p.strategy.best.design_profile)); await save(`Lettre_${slug(p.analysis.company)}_${slug(p.analysis.job_title)}.pdf`, new Blob([bytes], { type: 'application/pdf' })); },
    'dl-json': async () => { const p = curPack(); await save(`pack_${slug(p.analysis.company)}.json`, JSON.stringify(p, null, 2)); },
    'dl-zip': async () => {
      const p = curPack(); const P = Pp(); if (!window.JSZip) { toast('JSZip indisponible.'); return; }
      const z = new window.JSZip(); const base = `${slug(p.analysis.company)}_${slug(p.analysis.job_title)}`;
      if (p.cvs.length) z.file(`CV_${base}.pdf`, await PDF.build(PDF.cvDef(p.cvs[p.cv_index].doc)));
      if (p.letters.length) z.file(`Lettre_${base}.pdf`, await PDF.build(PDF.letterDef(p.letters[p.letter_index].doc, P.value('id.name'), E.contactLines(P), p.strategy.best.design_profile)));
      z.file('pack.json', JSON.stringify(p, null, 2)); z.file('pack.md', packMarkdown(p)); z.file('versions.json', JSON.stringify(p.versions, null, 2));
      await save(`PAI_Pack_${base}.zip`, await z.generateAsync({ type: 'blob' }));
    },
    'set-headline': async () => { const v = ($('#f-headline') || {}).value || ''; if (!v.trim()) return; await newCvVersion('titre', (d) => { const h = E.sectionLines(d, 'headline')[0]; if (h) h.text = v.trim(); }); },
    'set-design': async (el) => { const k = el.dataset.arg; await newCvVersion(`design ${k}`, (d) => { d.design_profile = k; d.ats_mode = k === 'ats_classic' ? 'ATS_FIRST' : k === 'human_premium' ? 'HUMAN_FIRST' : 'HYBRID'; }); },
    'set-color': async (el) => { const c = el.dataset.arg; await newCvVersion('couleur', (d) => { d.colors = Object.assign({}, d.colors || {}, { accent: c }); }); },
    'exp-up': async (el) => { const i = Number(el.dataset.arg); await newCvVersion('ordre', (d) => { const x = d.experiences.splice(i, 1)[0]; d.experiences.splice(i - 1, 0, x); }); },
    'exp-down': async (el) => { const i = Number(el.dataset.arg); await newCvVersion('ordre', (d) => { const x = d.experiences.splice(i, 1)[0]; d.experiences.splice(i + 1, 0, x); }); },
    'rewrite-summary': async () => {
      const p = curPack(); const P = Pp(); const a = p.analysis; toast('Claude réécrit le résumé…');
      S.run = S.run && S.run.status === 'running' ? S.run : { status: 'idle', controller: new AbortController(), calls: [], log: [], steps: [] };
      await newCvVersion('résumé', async (d) => {
        const ins = {}; E.sectionLines(d, 'summary').forEach((l) => { ins[l.id] = 'Réécrire plus percutant et plus spécifique à l\'offre, 45 mots max au total, sans rien ajouter qui ne soit dans les faits.'; });
        const r = await fixLoop(d.lines, E.Validator(S.profile, p.offer.text, [a.job_title, a.company]), P, a, { instructions: ins });
        d.lines = r.lines; d.removed_lines = (d.removed_lines || []).concat(r.removed); E.syncBlocks(d);
      });
    },
    'regen-feedback': async () => {
      const p = curPack(); const P = Pp(); const a = p.analysis; const fb = S.feedback.filter((f) => f.pack_id === p.id);
      if (!fb.length) { toast('Donnez d\'abord votre avis (👍 😐 👎) sur ce CV.'); return; }
      toast('Claude régénère le CV avec vos retours…');
      S.run = { status: 'idle', controller: new AbortController(), calls: [], log: [], steps: [] };
      const text = fb.map((f) => `[${f.element}] ${f.rating === 1 ? '👍' : f.rating === -1 ? '👎' : '😐'} ${f.comment || ''}`).join('\n');
      try {
        const cv0 = await generateCv(P, a, p.match, p.strategy, p.offer, { feedback: `RETOURS SUR LA VERSION PRÉCÉDENTE :\n${text}`, cache: false });
        const validator = E.Validator(S.profile, p.offer.text, [a.job_title, a.company]);
        const r = await fixLoop(cv0.lines, validator, P, a, {}); cv0.lines = r.lines; cv0.removed_lines = r.removed; E.syncBlocks(cv0);
        await newCvVersion('avec vos retours', (d) => { Object.keys(d).forEach((k) => delete d[k]); Object.assign(d, cv0); });
      } catch (e) { toast(AI.message(e)); }
    },
    'fb-rate': (el) => { S.fbRate = Number(el.dataset.arg); $$('[data-act="fb-rate"]').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.arg) === S.fbRate))); },
    'fb-save': async (el) => {
      if (S.fbRate === undefined) { toast('Choisissez 👍, 😐 ou 👎.'); return; }
      const p = curPack(); const [doc, idx] = el.dataset.arg.split(':');
      const f = { id: uid('fb'), pack_id: p.id, doc, version: Number(idx), element: ($('#fb-el') || {}).value || 'autre', rating: S.fbRate, comment: ($('#fb-comment') || {}).value || '',
        context: { sector: p.analysis.sector_id, role: p.analysis.job_title, country: p.analysis.country }, strategy: p.strategy.best.ats_mode, created_at: nowIso() };
      await Store.addDoc('feedback', f); S.fbRate = undefined; toast('Avis enregistré : il nourrira les prochaines générations.'); render();
    },
    'answer-save': async (el) => { const p = clone(curPack()); const i = Number(el.dataset.arg); p.answers[i].user_answer = ($(`#ans-${i}`) || {}).value || ''; await Store.savePack(p); toast('Réponse enregistrée dans le pack.'); },
    'chat-send': async () => {
      const inp = $('#chat-in'); const msg = (inp && inp.value || '').trim(); if (!msg) return;
      const p = curPack(); const P = Pp(); if (S.chat.pack !== p.id) S.chat = { pack: p.id, turns: [], busy: false };
      S.chat.turns.push({ role: 'user', content: msg }); S.chat.busy = true; render();
      const rules = E.render('chat', { candidate_name: P.value('id.name'), facts_table: E.factsTable(P), offer_context: `${p.analysis.job_title} · ${p.analysis.company} — ${p.offer.text.slice(0, 2500)}`, truth_rules: E.truthRules(P) });
      const turns = [{ role: 'user', content: rules }].concat(S.chat.turns.slice(-10));
      const reply = { role: 'assistant', content: '…' }; S.chat.turns.push(reply);
      try { const r = await S.caps.sample(turns, { modelTier: 'quick', cache: false, onText: ({ text }) => { reply.content = text; const log = $('#chat-log'); if (log && log.lastElementChild) log.lastElementChild.textContent = text; } }); reply.content = r.text; }
      catch (e) { reply.content = e && e.text ? e.text : AI.message(e); }
      S.chat.busy = false; render();
    },
    'arena-new': () => { const src = arenaSources(); if (!src.length) return; const pick = src[Math.floor(Math.random() * src.length)]; S.arenaPair = Object.assign({}, pick, { flip: Math.random() < 0.5, revealed: false }); render(); },
    'arena-vote': async (el) => {
      const pair = S.arenaPair; const choice = el.dataset.arg; const X = pair.flip ? pair.b : pair.a; const Y = pair.flip ? pair.a : pair.b;
      const vote = { id: uid('vote'), pair_id: pair.id, kind: pair.kind, title: pair.title, shown: { X: X.label, Y: Y.label }, choice, choice_label: choice === 'TIE' ? 'Égalité' : (choice === 'X' ? X : Y).label, reason: ($('#arena-reason') || {}).value || '', created_at: nowIso(), judge: null };
      await Store.addDoc('arena', vote); pair.revealed = true; pair.voteId = vote.id; pair.vote = vote; render();
    },
    'arena-judge': async () => {
      const pair = S.arenaPair; const X = pair.flip ? pair.b : pair.a; const Y = pair.flip ? pair.a : pair.b; toast('Le juge IA compare dans les deux ordres…');
      try {
        const r1 = await AI.ask('judge_pair', { offer_summary: pair.offer, doc_a: X.text.slice(0, 9000), doc_b: Y.text.slice(0, 9000) }, { cache: false });
        const r2 = await AI.ask('judge_pair', { offer_summary: pair.offer, doc_a: Y.text.slice(0, 9000), doc_b: X.text.slice(0, 9000) }, { cache: false });
        const w1 = r1.winner; const w2 = r2.winner === 'X' ? 'Y' : r2.winner === 'Y' ? 'X' : 'TIE';
        const winner = w1 === w2 ? w1 : 'TIE';
        pair.judge = { winner, winner_label: winner === 'TIE' ? 'Égalité / désaccord entre les deux ordres' : (winner === 'X' ? X : Y).label, orders: [r1, r2] };
        if (pair.vote) await Store.addDoc('arena', Object.assign({}, pair.vote, { judge: pair.judge }));
        render();
      } catch (e) { toast(AI.message(e)); }
    },
    'propose-rules': async () => {
      toast('Analyse de vos retours…');
      const min = ((D.scoring || {}).learning || {}).min_feedback_for_trend || 5;
      try {
        const out = await AI.ask('learning_rules', { feedback_json: JSON.stringify(S.feedback.slice(0, 150).map((f) => ({ id: f.id, context: f.context, element: f.element, rating: f.rating, comment: f.comment, strategy: f.strategy }))),
          existing_rules: (S.rules.accepted || []).map((r) => r.rule_text).join('\n') || 'aucune', min_feedback: String(min) }, { cache: false });
        const props = (out.proposals || []).filter((r) => Number(r.n_cases) >= min).map((r) => Object.assign({ id: uid('rule'), status: 'proposed', created_at: nowIso() }, r));
        await Store.saveRules(Object.assign({}, S.rules, { proposals: (S.rules.proposals || []).concat(props) }));
        toast(props.length ? `${props.length} règle(s) proposée(s).` : `Pas assez de retours concordants (${min} minimum par contexte) : INSUFFICIENT DATA.`);
      } catch (e) { toast(AI.message(e)); }
    },
    'rule-accept': async (el) => { const r = (S.rules.proposals || []).find((x) => x.id === el.dataset.arg); if (!r) return; r.status = 'accepted'; await Store.saveRules(Object.assign({}, S.rules, { accepted: (S.rules.accepted || []).concat([r]), rules_version: (S.rules.rules_version || 0) + 1 })); toast('Règle acceptée : elle guidera les prochaines générations.'); },
    'rule-refuse': async (el) => { const r = (S.rules.proposals || []).find((x) => x.id === el.dataset.arg); if (!r) return; r.status = 'refused'; await Store.saveRules(Object.assign({}, S.rules)); },
    'rule-remove': async (el) => { await Store.saveRules(Object.assign({}, S.rules, { accepted: (S.rules.accepted || []).filter((x) => x.id !== el.dataset.arg), rules_version: (S.rules.rules_version || 0) + 1 })); },
    'ja-accept': async () => {
      const imp = S.jobImport; const picked = imp.items.filter((x) => x.pick); if (!picked.length) { toast('Sélectionnez au moins un élément.'); return; }
      await mutateProfile((p) => { picked.forEach((it, i) => { const id = `ja.${imp.hash}.${i + 1}`; if (!p.facts.some((f) => f.id === id)) p.facts.push({ id, kind: it.kind, text: it.text, data: {}, status: 'UNVERIFIED', source: `jobagent:${imp.name}`, provenance: `${imp.name}#${it.path} (sha:${imp.hash})`, confidence: 0.5, parent: null, terms: [], needs_confirmation: true, approved: false, note: 'Importé du JobAgent : à confirmer', created_at: nowIso(), updated_at: nowIso() }); p.review_queue = (p.review_queue || []).concat([{ fact_id: id, reason: 'Import JobAgent : confirmer ou écarter', severity: 'warning' }]); }); }, 'jobagent_import', `${picked.length} élément(s) de ${imp.name}`);
      await Store.addDoc('jobagent', { id: uid('ja'), name: imp.name, hash: imp.hash, total: imp.items.length, accepted: picked.length, created_at: nowIso() });
      S.jobImport = null; render();
    },
    'ja-cancel': () => { S.jobImport = null; render(); },
    'profile-validate': async () => {
      const p = clone(S.profile); p.validated = true; p.validated_at = nowIso();
      await Store.saveProfile(p, 'validate', `Profil v${p.version} validé`);
      if (Store.db) await Store.put(`profile_versions/v${p.version}`, Object.assign({}, p, { tag: profileTag(p) }));
      toast(`Profil v${p.version} validé : les prochains packs pourront passer en FINAL.`);
    },
    'profile-export': async (el) => {
      const p = S.profile; const f = el.dataset.arg;
      if (f === 'json') await save(`master_profile_v${p.version}.json`, JSON.stringify(p, null, 2));
      if (f === 'csv') await save(`master_profile_v${p.version}.csv`, ['id,kind,status,text,parent,source,provenance'].concat(p.facts.map((x) => [x.id, x.kind, x.status, x.text, x.parent || '', x.source, x.provenance || ''].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))).join('\n'));
      if (f === 'md') await save(`master_profile_v${p.version}.md`, `# Master Profile v${p.version}\n\n` + p.facts.map((x) => `- \`${x.id}\` **${x.status}** — ${x.text}`).join('\n') + '\n');
    },
    'fact-edit': (el) => { S.editFact = el.dataset.arg; render(); },
    'fact-cancel': () => { S.editFact = null; render(); },
    'fact-save': async (el) => {
      const id = el.dataset.arg; const text = ($('#ef-text') || {}).value || ''; const status = ($('#ef-status') || {}).value;
      await mutateProfile((p) => { const f = p.facts.find((x) => x.id === id); if (!f) return; f.text = text.trim() || f.text; f.status = status; f.updated_at = nowIso(); if (status === 'CONFIRMED') { f.needs_confirmation = false; f.source = f.source.startsWith('user') ? f.source : `${f.source} + user`; } p.review_queue = (p.review_queue || []).filter((r) => r.fact_id !== id || status === 'UNVERIFIED'); }, 'fact_edit', id);
      S.editFact = null;
    },
    'fact-confirm': async (el) => { const id = el.dataset.arg; await mutateProfile((p) => { const f = p.facts.find((x) => x.id === id); if (f) { f.status = 'CONFIRMED'; f.needs_confirmation = false; f.updated_at = nowIso(); } p.review_queue = (p.review_queue || []).filter((r) => r.fact_id !== id); }, 'fact_confirm', id); },
    'fact-add': async () => {
      const text = (($('#nf-text') || {}).value || '').trim(); if (text.length < 2) { toast('Écrivez l\'énoncé exact du fait.'); return; }
      const kind = ($('#nf-kind') || {}).value || 'other'; const parent = ($('#nf-parent') || {}).value || null;
      await mutateProfile((p) => { p.facts.push({ id: `${kind}.u${Date.now().toString(36)}`, kind, text, data: {}, status: 'CONFIRMED', source: 'user:pai_studio', provenance: nowIso(), confidence: 1, parent, terms: [], needs_confirmation: false, approved: false, note: '', created_at: nowIso(), updated_at: nowIso() }); }, 'fact_add', text.slice(0, 60));
    },
    'review-confirm': async (el) => { const i = Number(el.dataset.arg); const r = S.profile.review_queue[i]; await mutateProfile((p) => { const f = p.facts.find((x) => x.id === r.fact_id); if (f) { f.status = 'CONFIRMED'; f.needs_confirmation = false; } p.review_queue.splice(i, 1); }, 'review_confirm', r.fact_id); },
    'review-reject': async (el) => { const i = Number(el.dataset.arg); const r = S.profile.review_queue[i]; await mutateProfile((p) => { const f = p.facts.find((x) => x.id === r.fact_id); if (f) { f.status = 'UNVERIFIED'; f.note = 'Écarté par l\'utilisateur'; } p.review_queue.splice(i, 1); }, 'review_reject', r.fact_id); },
    'review-dismiss': async (el) => { const i = Number(el.dataset.arg); await mutateProfile((p) => { p.review_queue.splice(i, 1); }, 'review_dismiss', '', true); },
    backup: async () => { await save(`pai_backup_${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify({ exported_at: nowIso(), versions: D.version, profile: S.profile, packs: S.packs, feedback: S.feedback, arena: S.arena, rules: S.rules, jobagent: S.jobagent }, null, 2)); },
  };
  const slug = (t) => String(t || 'pack').normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_|_$/g, '').slice(0, 30) || 'pack';
  function packMarkdown(p) {
    const a = p.analysis; const m = p.match; const s = p.strategy.best; const P = Pp();
    const L = p.letters[p.letter_index];
    return [`# Application Pack — ${a.job_title} · ${a.company}`, '', `Statut : **${p.status}** · ${p.mode} · ${p.provider} · ${p.created_at}${p.offer.synthetic ? ' · SYNTHETIC' : ''}`, '',
      '## Versions', '', ...Object.entries(p.versions).map(([k, v]) => `- ${k} : ${v || '—'}`), '', '## Matching', '', `MATCH ${m.match} · QUALITY ${m.quality} · RISK ${m.risk}`, '',
      ...m.coverage.map((c) => `- ${c.covered ? '✅' : '❌'} ${c.term} (${c.priority})`), '', '## Stratégie', '', `- Titre : ${s.title}`, `- Accroche : ${s.hook}`, `- ${s.ats_mode} · ${s.design_profile} · photo ${s.photo_mode}`, '',
      '## Factualité', '', `- CV : ${p.scores.factuality_cv} % · lettre : ${p.scores.factuality_letter} %`, '',
      ...(L ? ['## Lettre', '', L.doc.subject, '', L.doc.salutation, '', ...E.letterParagraphs(L.doc).map((x) => `${x}\n`), L.doc.signature, ''] : []),
      ...(p.answers.length ? ['## Questions', '', ...p.answers.map((x) => `**${x.question}** (${x.confidence})\n\n${x.answer || x.user_answer || `➜ À fournir : ${x.ask_user}`}\n`)] : []),
      '## Risques', '', ...p.risks.map((r) => `- ${r}`), '', '## Prochaine action', '', p.next_action, '', `_${P ? P.value('id.name') : ''} — généré par PAI Studio_`].join('\n');
  }

  function parseJobAgent(name, text) {
    const items = []; let hash = E.hash(text);
    const push = (path, val) => { const t = String(val).trim(); if (t.length >= 3 && t.length <= 300 && !/^https?:\/\//.test(t) && !/^[\d\s.:-]+$/.test(t)) items.push({ path, text: t, kind: guessKind(path + ' ' + t), pick: false }); };
    try {
      const walk = (v, path) => { if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${path}[${i}]`)); else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => walk(x, path ? `${path}.${k}` : k)); else if (typeof v === 'string') push(path, v); };
      walk(JSON.parse(text), '');
    } catch (e) { text.split('\n').map((l) => l.replace(/^[\s\-*#•]+/, '').trim()).forEach((l, i) => push(`ligne ${i + 1}`, l)); }
    hash = hash.slice(0, 7);
    return { name, hash, items: items.slice(0, 300) };
  }
  function guessKind(t) {
    const n = E.norm(t);
    if (/diplome|bachelor|master|bts|licence|formation|ecole|education/.test(n)) return 'education';
    if (/toeic|toefl|certif/.test(n)) return 'certification';
    if (/anglais|english|espagnol|arabe|langue|language/.test(n)) return 'language';
    if (/\d+\s?%|\+\d|k€|leads|objectif|ca /.test(n)) return 'result';
    if (/experience|poste|job|entreprise|company/.test(n)) return 'experience';
    if (/hubspot|excel|crm|outil|tool|salesforce|canva|notion/.test(n)) return 'tool';
    return 'other';
  }

  // ─── Événements ─────────────────────────────────────────────────────────────
  document.addEventListener('click', (ev) => {
    const el = ev.target.closest('[data-act]'); if (!el || el.disabled) return;
    const fn = ACT[el.dataset.act]; if (!fn) return;
    ev.preventDefault();
    Promise.resolve(fn(el, ev)).catch((e) => { console.error(e); toast(`Action impossible : ${(e && e.message) || e}`); });
  });
  document.addEventListener('input', (ev) => { const b = ev.target.dataset && ev.target.dataset.bind; if (b) { S.draft[b] = ev.target.value; if (b === 'offer') S.draft.synthetic = false; } });
  document.addEventListener('change', async (ev) => {
    const t = ev.target; const kind = t.dataset && t.dataset.change; if (!kind) return;
    try {
      if (kind === 'offer-pdf' && t.files[0]) { toast('Lecture du PDF…'); S.draft.offer = await PDF.offerTextFromFile(t.files[0]); S.draft.sourceType = 'pdf'; S.draft.synthetic = false; render(); toast('Texte de l\'offre extrait du PDF.'); }
      if (kind === 'profile-file' && t.files[0]) {
        const data = JSON.parse(await t.files[0].text());
        if (!data || !Array.isArray(data.facts)) throw new Error('Ce fichier n\'est pas un Master Profile PAI.');
        await Store.saveProfile(Object.assign({ review_queue: [], unknowns: [], history: [] }, data), 'import', t.files[0].name); toast(`Profil importé (${data.facts.length} faits).`);
      }
      if (kind === 'ja-file' && t.files[0]) { S.jobImport = parseJobAgent(t.files[0].name, await t.files[0].text()); render(); }
      if (kind === 'ja-pick') { S.jobImport.items[Number(t.dataset.arg)].pick = t.checked; }
      if (kind === 'ja-kind') { S.jobImport.items[Number(t.dataset.arg)].kind = t.value; }
      if (kind === 'compare') { S.compareWith = t.value === '' ? null : Number(t.value); render(); }
    } catch (e) { toast(`Import impossible : ${(e && e.message) || e}`); }
  });
  let pop = null;
  document.addEventListener('mouseover', (ev) => {
    const el = ev.target.closest('.sheet [data-line]'); const p = curPack();
    if (!el || !p || !S.profile) { if (pop && !ev.target.closest('.popover')) { pop.remove(); pop = null; } return; }
    const docs = p.cvs.map((c) => c.doc).concat(p.letters.map((l) => l.doc));
    const line = docs.flatMap((d) => d.lines).find((l) => l.id === el.dataset.line); if (!line) return;
    const P = Pp(); const facts = (line.fact_ids || []).map((id) => P.fact(id)).filter(Boolean);
    if (!pop) { pop = document.createElement('div'); pop.className = 'popover'; document.body.appendChild(pop); }
    pop.innerHTML = `<div class="row" style="justify-content:space-between;margin-bottom:6px"><span class="fid">${esc(line.id)}</span>${chip(line.kind)}</div>${facts.length ? facts.map((f) => `<div class="ft"><div>${esc(f.text)}</div><div class="muted" style="font-size:12px"><span class="fid">${esc(f.id)}</span> ${statusChip(f.status)}</div></div>`).join('') : `<div class="muted">${line.kind === 'offer_ref' ? `Citation de l'offre : « ${esc(line.offer_quote)} »` : line.kind === 'headline' ? 'Titre visé (intitulé de l\'offre), pas un poste occupé.' : 'Aucun fait lié.'}</div>`}`;
    const r = el.getBoundingClientRect(); const top = Math.min(window.innerHeight - pop.offsetHeight - 8, r.bottom + 6); const left = Math.min(window.innerWidth - pop.offsetWidth - 8, Math.max(8, r.left));
    pop.style.top = `${Math.max(8, top)}px`; pop.style.left = `${left}px`;
  });
  window.addEventListener('resize', fitSheets);
  window.addEventListener('hashchange', () => { const h = location.hash.slice(1); if (h && (V[h] || h === 'plus')) { S.view = h; render(); } });

  // ─── Démarrage ──────────────────────────────────────────────────────────────
  async function boot() {
    renderShell(); PDF.init();
    const h = location.hash.slice(1); if (h && V[h]) S.view = h;
    render();
    const use = (n) => (window.claude && typeof window.claude.use === 'function' ? window.claude.use(n).catch(() => null) : Promise.resolve(null));
    const [db, sample, downloads, user] = await Promise.all([use('db'), use('sample'), use('downloads'), use('user')]);
    S.caps = { db, sample, downloads, user };
    S.ai = sample ? 'ready' : 'off';
    if (sample && sample.limits) sample.limits().then((l) => { S.aiLimits = l; render(); }).catch(() => {});
    if (db) Store.subscribe(db); else Store.memory();
    S.ready = true; render();
  }
  window.__PAI_DEBUG__ = { PDF, E, S };
  boot();
})();
