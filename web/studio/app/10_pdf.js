// ─── PDF : gabarits PAIDesigns (pdfmake) + pdf.js (lecture, aperçu réel, contrôle qualité) ──
const PDF = {
  cache: new Map(), queue: [], busy: false,
  ready() { return !!(window.pdfMake && window.PAI_FONTS); },
  init() {
    if (window.pdfMake && window.PAI_FONTS) DS.registerFonts(window.pdfMake, window.PAI_FONTS);
    // Le worker est chargé par une balise script : pdf.js l'utilise sur le fil principal (aucun appel réseau supplémentaire).
    if (window.pdfjsLib) window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js';
  },
  // Contexte de rendu d'un CV : palette, densité, photo (déjà recadrée) et mode photo retenus pour cette version.
  ctx(doc, over = {}) {
    const fam = DS.familyOf(doc.design_profile); const d = D.designs[fam] || {};
    const pal = over.palette || doc.palette || d.palette_default || 'petrol';
    const accent = over.accent !== undefined ? over.accent : (doc.colors && doc.colors.accent);
    const mode = over.photo_mode || doc.photo_mode || 'OFF';
    const A = S.photoAssets;
    return { palette: DS.palette(pal, accent), density: over.density || doc.density || d.density || 'balanced',
      photo: A ? { circle: A.circle, square: A.square, scale: (S.photo && S.photo.scale) || 1 } : null, photoMode: A ? mode : 'OFF' };
  },
  cvDef(doc, over) { return DS.cv(E, doc, PDF.ctx(doc, over)); },
  letterDef(letterDoc, cvDoc, P, over = {}) {
    const base = cvDoc || { design_profile: 'ats_hybrid' };
    const layout = over.layout || letterDoc.layout || base.design_profile;
    const c = PDF.ctx(base, over);
    const head = (E.sectionLines(base, 'headline')[0] || {}).text || '';
    return DS.letter(E, letterDoc, Object.assign(c, { designId: layout, name: P.value('id.name'), contact: E.contactLines(P), headline: head, photoMode: 'OFF' }));
  },
  build(def) {
    return new Promise((resolve, reject) => {
      try { window.pdfMake.createPdf(def).getBuffer((buf) => resolve(new Uint8Array(buf))); } catch (e) { reject(e); }
    });
  },
  async open(bytes) { return window.pdfjsLib.getDocument({ data: bytes.slice(0), isEvalSupported: false }).promise; },
  async inspect(bytes) {
    // Texte reconstitué par positions (comme pdftotext / un ATS) + remplissage de la dernière page.
    const doc = await this.open(bytes); let text = ''; let minSize = 99; let overflow = 0; let fill = 0;
    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i); const vp = page.getViewport({ scale: 1 }); const tc = await page.getTextContent();
      let lastY = null; let lastEnd = null; let lowest = vp.height;
      for (const it of tc.items) {
        if (!it.str) { if (it.hasEOL) { text += '\n'; lastY = null; } continue; }
        const size = Math.hypot(it.transform[0], it.transform[1]); const x = it.transform[4]; const y = it.transform[5];
        if (lastY !== null && Math.abs(y - lastY) > size * 0.5) text += '\n';
        else if (lastEnd !== null && x - lastEnd > size * 0.12) text += ' ';
        text += it.str; lastY = y; lastEnd = x + it.width;
        if (it.hasEOL) { text += '\n'; lastY = null; lastEnd = null; }
        if (it.str.trim()) { minSize = Math.min(minSize, size); if (x < 8 || x + it.width > vp.width - 8) overflow++; lowest = Math.min(lowest, y); }
      }
      text += '\n';
      if (i === doc.numPages) fill = Math.max(0, Math.min(1, (vp.height - lowest) / vp.height));
    }
    return { pages: doc.numPages, text, minSize: minSize === 99 ? null : Math.round(minSize * 10) / 10, overflow, fill: Math.round(fill * 100) / 100, doc };
  },
  async renderInto(bytes, canvas, width) {
    const doc = await this.open(bytes); const page = await doc.getPage(1); const vp1 = page.getViewport({ scale: 1 });
    const scale = (width / vp1.width) * Math.min(2, window.devicePixelRatio || 1); const vp = page.getViewport({ scale });
    canvas.width = Math.round(vp.width); canvas.height = Math.round(vp.height);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
    return doc.numPages;
  },
  async offerTextFromFile(file) {
    const buf = new Uint8Array(await file.arrayBuffer()); const doc = await this.open(buf); let text = '';
    for (let i = 1; i <= Math.min(doc.numPages, 6); i++) { const tc = await (await doc.getPage(i)).getTextContent(); text += tc.items.map((it) => it.str + (it.hasEOL ? '\n' : ' ')).join('') + '\n'; }
    return text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  },
  // Mise à la page : d'abord la densité (sans rien retirer), puis retrait des lignes les moins utiles (jamais d'ajout),
  // et à l'inverse on aère une page trop vide. Une densité choisie à la main n'est pas modifiée.
  async cvFitted(cv, maxPages) {
    const fam = DS.familyOf(cv.design_profile); let density = cv.density || (D.designs[fam] || {}).density || 'balanced';
    const locked = !!cv.density_locked;
    let doc = cv; let bytes = await this.build(this.cvDef(doc, { density })); let info = await this.inspect(bytes);
    if (info.pages > maxPages && !locked && density !== 'compact') { density = 'compact'; bytes = await this.build(this.cvDef(doc, { density })); info = await this.inspect(bytes); }
    let step = 0;
    while (info.pages > maxPages && step < 3) { step++; doc = E.trimForSpace(doc, step); bytes = await this.build(this.cvDef(doc, { density })); info = await this.inspect(bytes); }
    if (!locked && info.pages <= maxPages && info.fill < 0.78 && density !== 'airy') {
      const b2 = await this.build(this.cvDef(doc, { density: 'airy' })); const i2 = await this.inspect(b2);
      if (i2.pages <= maxPages) { density = 'airy'; bytes = b2; info = i2; }
    }
    doc = Object.assign({}, doc, { density });
    return { doc, bytes, info, trimSteps: step };
  },
  qa(info, cv, requiredTerms, maxPages) {
    const issues = []; const tn = E.norm(info.text);
    if (info.pages > maxPages) issues.push({ severity: 'high', check: 'pagination', detail: `${info.pages} pages (max ${maxPages})` });
    if (info.text.length < 300) issues.push({ severity: 'high', check: 'ats_extraction', detail: 'texte peu ou pas extractible' });
    let cursor = 0; let orderOk = true;
    for (const m of [cv.name, cv.section_titles.experience, cv.section_titles.education]) { const pos = tn.indexOf(E.norm(m), cursor); if (pos < 0) { orderOk = false; break; } cursor = pos + 1; }
    if (!orderOk) issues.push({ severity: 'high', check: 'ordre_lecture', detail: 'ordre de lecture ATS incohérent' });
    if (info.minSize !== null && info.minSize < 6.4) issues.push({ severity: 'medium', check: 'taille', detail: `police minimale ${info.minSize} pt` });
    if (info.overflow) issues.push({ severity: 'high', check: 'debordement', detail: `${info.overflow} segment(s) hors page` });
    if (info.pages === 1 && info.fill < 0.6) issues.push({ severity: 'low', check: 'remplissage', detail: `page remplie à ${Math.round(info.fill * 100)} %` });
    const found = requiredTerms.filter((t) => E.supportedBy(t, tn));
    return { ok: !issues.some((i) => i.severity === 'high'), issues, pages: info.pages, min_font_pt: info.minSize, fill: info.fill, required_found: `${found.length}/${requiredTerms.length}`,
      required_missing: requiredTerms.filter((t) => !found.includes(t)), ats_text_chars: info.text.length };
  },
  async pngBlob(bytes, width = 900) {
    const canvas = document.createElement('canvas'); await this.renderInto(bytes, canvas, width);
    return new Promise((res) => canvas.toBlob((b) => res(b), 'image/png'));
  },

  // ── Aperçus réels (image de la page 1, mise en cache par empreinte du rendu) ──
  key(kind, doc, extra) {
    return `${kind}-${E.hash([doc.lines, doc.experiences, doc.design_profile, doc.palette, doc.colors, doc.density, doc.photo_mode, doc.draft, doc.layout, doc.subject, extra || '', S.photoAssets ? S.photoAssets.id : 'nophoto'])}`;
  },
  invalidate() { PDF.cache.clear(); },
  want(key, defFn, width = 880) {
    if (!PDF.cache.has(key)) PDF.cache.set(key, { url: null, defFn, width, err: null, pages: 0 });
    return PDF.cache.get(key);
  },
  hydrate(root = document) {
    for (const el of $$('.paper[data-pv]', root)) {
      const ent = PDF.cache.get(el.dataset.pv);
      if (!ent) continue;
      if (ent.url) PDF.paint(el, ent);
      else if (!ent.err && !PDF.queue.includes(el.dataset.pv)) PDF.queue.push(el.dataset.pv);
    }
    PDF.pump();
  },
  paint(el, ent) {
    if (el.querySelector('img.pv')) return;
    const img = new Image(); img.className = 'pv'; img.alt = ''; img.decoding = 'async'; img.src = ent.url;
    const fresh = !ent.shown; ent.shown = true;
    img.onload = () => { if (fresh) requestAnimationFrame(() => img.classList.add('ready')); else img.classList.add('ready', 'instant'); };
    el.appendChild(img);
    if (ent.pages > 1) el.setAttribute('data-pages', `${ent.pages} pages`);
  },
  async pump() {
    if (PDF.busy || !PDF.ready() || !window.pdfjsLib) return;
    PDF.busy = true;
    try {
      while (PDF.queue.length) {
        const key = PDF.queue.shift(); const ent = PDF.cache.get(key); if (!ent || ent.url) continue;
        try {
          const bytes = await PDF.build(ent.defFn()); const canvas = document.createElement('canvas');
          ent.pages = await PDF.renderInto(bytes, canvas, ent.width); ent.url = canvas.toDataURL('image/jpeg', 0.9);
        } catch (e) { ent.err = String((e && e.message) || e); console.warn('aperçu', e); }
        for (const el of $$(`.paper[data-pv="${key}"]`)) { if (ent.url) PDF.paint(el, ent); else el.classList.add('failed'); }
        await new Promise((r) => setTimeout(r, 0));
      }
    } finally { PDF.busy = false; }
    if (PDF.cache.size > 60) { const keys = [...PDF.cache.keys()]; keys.slice(0, PDF.cache.size - 60).forEach((k) => PDF.cache.delete(k)); }
  },
};

// Aperçu A4 réel : squelette animé pendant le rendu, puis image de la vraie page PDF.
function paper(kind, doc, defFn, opts = {}) {
  const w = opts.width || 880; const key = `${PDF.key(kind, doc, opts.extra)}-${w}`; PDF.want(key, defFn, w);
  return `<div class="paper${opts.cls ? ` ${opts.cls}` : ''}" data-pv="${key}" role="img" aria-label="${esc(opts.label || 'Aperçu du document PDF')}">
    <div class="skeleton" aria-hidden="true"><i class="h"></i><i class="m"></i><i class="s"></i><i></i><i class="m"></i><i></i><i class="s"></i><i class="m"></i><i></i><i class="s"></i></div>
    ${opts.badge ? `<span class="stamp-tag">${opts.badge}</span>` : ''}</div>`;
}
const cvPaper = (doc, opts = {}) => paper('cv', doc, () => PDF.cvDef(doc), Object.assign({ label: `Aperçu du CV — ${DESIGN_NAME(doc.design_profile)}` }, opts));
const letterPaper = (letterDoc, cvDoc, opts = {}) => { const P = Pp(); return paper('lt', letterDoc, () => PDF.letterDef(letterDoc, cvDoc, P, opts), Object.assign({ label: 'Aperçu de la lettre', extra: [cvDoc && cvDoc.design_profile, cvDoc && cvDoc.palette, opts.layout] }, opts)); };
