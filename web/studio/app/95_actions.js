// ─── Actions ─────────────────────────────────────────────────────────────────
async function mutateProfile(fn, action, detail, keepValidation) {
  const p = clone(S.profile); fn(p);
  if (!keepValidation) { p.version = (p.version || 1) + 1; p.validated = false; p.validated_at = null; }
  await Store.saveProfile(p, action, detail); toast(keepValidation ? 'Profil enregistré.' : `Profil v${p.version} enregistré : à revalider.`, 'i-user');
}
const confirmFact = (f, note) => { f.status = 'CONFIRMED'; f.needs_confirmation = false; f.updated_at = nowIso(); if (note) f.note = note; if (!String(f.source || '').includes('user')) f.source = `${f.source || 'import'} + user`; };
const discardFact = (f, note) => { f.status = 'UNVERIFIED'; f.needs_confirmation = false; f.updated_at = nowIso(); f.note = note; };
const requiredTerms = (p) => p.match.coverage.filter((c) => c.covered && c.priority === 'REQUIRED').map((c) => c.term);
const PRESENTATION = ['design_profile', 'palette', 'density', 'density_locked', 'photo_mode', 'colors', 'design_why'];

// Nouvelle version de CV : part de la version affichée (ou `opts.base`), applique le brouillon de présentation puis la modification,
// revalide chaque ligne, remet en page, contrôle le PDF. La version précédente reste intacte (versionnage complet).
async function newCvVersion(label, mutate, opts = {}) {
  const live = curPack(); if (!live) return null;
  const p = clone(live); const baseIdx = opts.base !== undefined ? opts.base : cvIdx(live); const base = p.cvs[baseIdx];
  const draft = studioDraft(live, baseIdx);
  const doc = Object.assign(clone(base.doc), draft || {}); if (doc.colors === null) delete doc.colors;
  await mutate(doc);
  const maxP = E.country(p.analysis.country).max_pages || 1; let fitted = doc; let qa = base.qa;
  try { const fit = await PDF.cvFitted(doc, maxP); fitted = fit.doc; qa = PDF.qa(fit.info, fit.doc, requiredTerms(p), maxP); qa.trim_steps = fit.trimSteps; } catch (e) { console.warn(e); }
  const report = E.Validator(S.profile, p.offer.text, [p.analysis.job_title, p.analysis.company]).validateLines(fitted.lines);
  const critique = opts.presentationOnly ? base.critique : { deterministic: E.deterministicCritique(fitted, p.analysis, p.match, report), ai: null, cycles: 0 };
  const v = Math.max(...p.cvs.map((x) => x.v || 0)) + 1;
  p.cvs.push({ v, label: `V${v}`, created_at: nowIso(), source: fitted.source, doc: fitted, report, critique, qa, change: label, from: base.label || `V${base.v}` });
  p.cv_index = p.cvs.length - 1;
  refreshStatus(p); const saved = await Store.savePack(p);
  S.cvIndex = saved.cv_index; S.compareWith = Math.max(0, saved.cvs.findIndex((x) => x.v === base.v)); S.studio = null;
  toast(report.perfect ? `V${v} enregistrée · ${label}` : `V${v} : ${report.rejected_ids.length} ligne(s) sans preuve à corriger.`, report.perfect ? 'i-check' : 'i-alert');
  render();
  return v;
}
function setDraft(changes) {
  const p = curPack(); if (!p) return; const idx = cvIdx(p);
  if (!S.studio || S.studio.packId !== p.id || S.studio.index !== idx) S.studio = { packId: p.id, index: idx, changes: {} };
  Object.assign(S.studio.changes, changes);
  const base = p.cvs[idx].doc; for (const [k, v] of Object.entries(S.studio.changes)) if (JSON.stringify(base[k]) === JSON.stringify(v) || (v === null && base[k] === undefined)) delete S.studio.changes[k];
  render();
}
async function sideTask(fn) {
  if (S.run && S.run.status === 'running') { const e = new Error('Une analyse est en cours : attends qu\'elle se termine.'); e.code = 'busy'; throw e; }
  const prev = CUR; CUR = { controller: new AbortController(), calls: [], log: [], steps: [] };
  try { return await fn(); } finally { CUR = prev; }
}
async function regenerateWithFeedback(p, reasons, comment) {
  const P = Pp(); const a = p.analysis; const baseIdx = p.cvs.length - 1; const base = p.cvs[baseIdx];
  const wantsContent = reasons.some((r) => ['Titre', 'Accroche', 'Expérience', 'Compétence', 'Personnalisation', 'Autre'].includes(r)) || !!String(comment || '').trim();
  let aiDoc = null; const notes = [];
  if (AI.ok() && wantsContent) {
    const fb = S.feedback.filter((f) => f.pack_id === p.id).map((f) => `[${(f.reasons || [f.element]).join(', ')}] ${rateIcon(f.rating)} ${f.comment || ''}`).join('\n');
    try {
      await sideTask(async () => {
        const cv0 = await generateCv(P, a, p.match, p.strategy, p.offer, { feedback: `RETOURS SUR LA VERSION PRÉCÉDENTE :\n${fb}`, cache: false });
        const r = await fixLoop(cv0.lines, E.Validator(S.profile, p.offer.text, [a.job_title, a.company]), P, a, {});
        cv0.lines = r.lines; cv0.removed_lines = r.removed; E.syncBlocks(cv0); aiDoc = cv0;
      });
    } catch (e) { toast(AI.message(e), 'i-alert'); }
    if (aiDoc) { PRESENTATION.forEach((k) => { if (base.doc[k] !== undefined) aiDoc[k] = base.doc[k]; }); notes.push(`contenu réécrit par ${AI.short()}`); }
  }
  const det = deterministicV2(p, aiDoc || base.doc, aiDoc ? reasons.filter((r) => ['Design', 'Couleur', 'Photo', 'ATS'].includes(r)) : reasons);
  notes.push(...det.notes);
  if (!aiDoc && !compareDocs(base.doc, det.doc).length) { toast('Aucun ajustement possible sans IA pour ces raisons : choisis Design, Couleur, Photo, ATS, Titre, Expérience, Accroche ou Compétence.', 'i-info'); return null; }
  return newCvVersion(notes.join(' · ') || 'avis', (d) => { Object.keys(d).forEach((k) => delete d[k]); Object.assign(d, clone(det.doc)); }, { base: baseIdx, presentationOnly: !aiDoc && !reasons.some((r) => ['Titre', 'Expérience', 'Accroche', 'Compétence', 'Personnalisation'].includes(r)) });
}
async function saveFeedback(p, doc, version, rating, reasons, comment) {
  const f = { id: uid('fb'), pack_id: p.id, doc, version, element: reasons[0] || 'Autre', reasons, rating, comment: comment || '',
    context: { sector: p.analysis.sector_id, role: p.analysis.job_title, country: p.analysis.country }, strategy: p.strategy.best.ats_mode,
    design: p.cvs[version] ? p.cvs[version].doc.design_profile : '', created_at: nowIso() };
  await Store.addDoc('feedback', f); return f;
}
function packMarkdown(p) {
  const a = p.analysis; const m = p.match; const s = p.strategy.best; const P = Pp(); const L = p.letters[p.letter_index]; const e = p.cvs[p.cv_index];
  return [`# Application Pack — ${a.job_title} · ${disp(a.company, 'company')}`, '', `Statut : **${p.status}** · ${p.mode} · ${p.provider} · ${p.created_at}${p.offer.synthetic ? ' · SYNTHETIC' : ''}`, '',
    '## Versions', '', ...Object.entries(p.versions).map(([k, v]) => `- ${k} : ${v || '—'}`), '', '## Correspondance', '', `MATCH ${m.match} · QUALITY ${m.quality} · RISK ${m.risk}`, '',
    ...m.coverage.map((c) => `- ${c.covered ? '✅' : '❌'} ${c.term} (${c.priority})`), '', '## Stratégie', '', `- Titre : ${s.title}`, `- Accroche : ${s.hook}`, `- ${s.ats_mode} · ${e ? DESIGN_NAME(e.doc.design_profile) : s.design_profile}`, '',
    ...(p.design ? ['## Pourquoi ce design', '', ...p.design.why.map((w) => `- ${w.k} : ${w.t}`), ''] : []),
    '## Factualité', '', `- CV : ${p.scores.factuality_cv} % · lettre : ${p.scores.factuality_letter} %`, '',
    ...(L ? ['## Lettre', '', L.doc.subject, '', L.doc.salutation, '', ...E.letterParagraphs(L.doc).map((x) => `${x}\n`), L.doc.signature, ''] : []),
    ...(p.answers.length ? ['## Questions', '', ...p.answers.map((x) => `**${x.question}** (${x.confidence})\n\n${x.answer || x.user_answer || `➜ À fournir : ${x.ask_user}`}\n`)] : []),
    '## Risques', '', ...p.risks.map((r) => `- ${r}`), '', '## Prochaine action', '', p.next_action, '', `_${P ? P.value('id.name') : ''} — préparé avec PAI (Personal Application Intelligence). PAI n'envoie rien : tu postules toi-même._`].join('\n');
}
const fileBase = (p) => `${slug(p.analysis.company)}_${slug(p.analysis.job_title)}`;
function draftPending() { const p = curPack(); return p && studioDraft(p, cvIdx(p)) && Object.keys(studioDraft(p, cvIdx(p))).length; }
async function readOfferPdf(file) {
  if (!file || !/pdf$/i.test(file.type || file.name)) { toast('Choisis un fichier PDF.', 'i-alert'); return; }
  toast('Lecture du PDF…', 'i-file');
  const text = await PDF.offerTextFromFile(file);
  if (text.length < 80) { toast('PDF sans texte lisible (scan ?) : colle le texte de l\'offre.', 'i-alert'); return; }
  Object.assign(S.draft, { input: text, sourceType: 'pdf', fileName: file.name.slice(0, 80), synthetic: false, textMode: true, notice: null });
  if (S.run && S.run.status !== 'running') S.run = null;
  render(); toast(`Texte extrait du PDF (${text.length.toLocaleString('fr-FR')} caractères). Clique sur Analyser.`, 'i-check');
}
async function setPhotoFromFile(file) {
  const ph = await Photo.fromFile(file); await Store.savePhoto(ph);
  toast(Photo.lowRes(ph) ? `Photo enregistrée · basse résolution (${Photo.px(ph)} px) : utilisable, mais un original plus grand serait plus net.` : 'Photo enregistrée : recadre-la si besoin.', 'i-camera');
}

const ACT = {
  go: (el) => {
    const a = el.dataset.arg; setMore(false);
    if (a === 'profil-photo') { S.view = 'profil'; S.profileFocus = 'photo-card'; } else S.view = a;
    if (S.view === 'onboarding') S.onboard = null;
    render();
  },
  'open-more': () => setMore(!S.moreOpen), 'close-more': () => setMore(false),
  'open-pack': (el) => { S.packId = el.dataset.arg; lsSet('packId', S.packId); S.view = 'pack'; S.packTab = 'overview'; S.cvIndex = null; S.compareWith = null; S.studio = null; render(); },
  'open-studio': (el) => { S.packId = el.dataset.arg; lsSet('packId', S.packId); S.view = 'studio'; S.cvIndex = null; S.studio = null; render(); },
  'open-lab': (el) => { S.lab.packId = el.dataset.arg; S.view = 'lab'; render(); },
  'pack-tab': (el) => { S.packTab = el.dataset.arg; if (S.view !== 'pack') S.view = 'pack'; render(); },
  mode: (el) => { S.draft.mode = el.dataset.arg; lsSet('mode', S.draft.mode); render(); },
  analyze: async () => {
    const raw = (S.draft.input || '').trim();
    if (!raw) { toast("Colle un lien ou le texte de l'offre.", 'i-info'); const t = $('#cmd-input'); if (t) t.focus(); return; }
    S.draft.notice = null;
    const common = { title: S.draft.title, company: S.draft.company, questions: S.draft.questions, synthetic: S.draft.synthetic };
    if (looksLikeUrl(raw)) {
      if (!SERVER) { S.draft.notice = { tone: 'warn', text: Ingest.message({ code: 'no_fetch_here', message: "Dans claude.ai, PAI ne peut pas ouvrir un lien (sécurité de la page). Colle le texte de l'offre ou importe son PDF — la lecture de liens fonctionne sur ton serveur PAI." }), fallback: true }; render(); return; }
      await runPipeline(Object.assign({ url: raw }, common));
    } else await runPipeline(Object.assign({ text: raw, sourceType: S.draft.sourceType === 'pdf' ? 'pdf' : 'text', fileName: S.draft.fileName || '' }, common));
  },
  'cmd-text': () => { const wasUrl = looksLikeUrl(S.draft.input); S.draft.textMode = !S.draft.textMode || wasUrl; if (wasUrl) S.draft.input = ''; S.draft.notice = null; render(); requestAnimationFrame(() => { const t = $('#cmd-input'); if (t) t.focus(); }); },
  'cmd-text-go': () => { S.run = null; Object.assign(S.draft, { textMode: true, input: '', notice: null, sourceType: 'text' }); S.view = 'analyser'; render(); requestAnimationFrame(() => { const t = $('#cmd-input'); if (t) t.focus(); }); },
  'cmd-clear': () => { Object.assign(S.draft, { input: '', sourceType: 'text', fileName: '', notice: null, synthetic: false }); render(); requestAnimationFrame(() => { const t = $('#cmd-input'); if (t) t.focus(); }); },
  'focus-cmd': () => { if (!['accueil', 'analyser'].includes(S.view) || (S.view === 'analyser' && S.run)) S.view = 'accueil'; render(); requestAnimationFrame(() => { const t = $('#cmd-input'); if (t) { t.focus(); t.scrollIntoView({ block: 'center', behavior: 'smooth' }); } }); },
  'new-analysis': () => { if (S.run && S.run.status === 'running') return; S.run = null; S.view = 'analyser'; render(); requestAnimationFrame(() => { const t = $('#cmd-input'); if (t) t.focus(); }); },
  cancel: () => { if (S.run && S.run.controller) S.run.controller.abort(); },
  example: () => {
    const off = Object.values(D.examples || {})[0]; if (!off) return;
    Object.assign(S.draft, { input: off.text, title: off.title, company: off.company, synthetic: true, textMode: true, sourceType: 'text', notice: null });
    render(); toast('Exemple chargé : offre FICTIVE (marquée SYNTHETIC).', 'i-info');
  },
  'rerun-standard': async () => { const p = curPack(); if (!p) return; S.draft.mode = 'STANDARD'; lsSet('mode', 'STANDARD'); await runPipeline({ text: p.offer.text, sourceType: p.offer.source_type === 'url' ? 'text' : p.offer.source_type, sourceUrl: p.offer.source_url, title: p.offer.title_hint, company: p.offer.company_hint, synthetic: p.offer.synthetic, questions: '' }); },

  // ── CV Studio ──
  'cv-version': (el) => { S.cvIndex = Number(el.dataset.arg); S.studio = null; render(); },
  'cv-version-open': (el) => { S.cvIndex = Number(el.dataset.arg); S.studio = null; S.packTab = 'cv'; render(); },
  'cv-keep': async (el) => { const p = clone(curPack()); p.cv_index = Number(el.dataset.arg); refreshStatus(p); await Store.savePack(p); S.cvIndex = p.cv_index; toast(`${p.cvs[p.cv_index].label} retenue pour ce pack.`, 'i-check'); render(); },
  'toggle-gallery': () => { S.galleryOpen = !S.galleryOpen; render(); },
  'preview-mode': (el) => { S.previewMode = el.dataset.arg; render(); },
  'letter-mode': (el) => { S.letterMode = el.dataset.arg; render(); },
  'set-design': (el) => {
    const f = el.dataset.arg; const p = curPack(); const doc = viewDoc(p, cvIdx(p)); const dd = D.designs[f] || {};
    const ch = { design_profile: f };
    if (!(dd.palettes || []).includes(doc.palette)) ch.palette = dd.palette_default || 'petrol';
    if (doc.photo_mode === 'SIDEBAR' && f !== 'digital_creative') ch.photo_mode = 'HEADER';
    if (doc.photo_mode === 'HEADER' && f === 'digital_creative') ch.photo_mode = 'SIDEBAR';
    setDraft(ch);
  },
  'set-palette': (el) => setDraft({ palette: el.dataset.arg, colors: null }),
  'set-density': (el) => setDraft({ density: el.dataset.arg, density_locked: true }),
  'set-photo': (el) => { const p = curPack(); const fam = DS.familyOf(viewDoc(p, cvIdx(p)).design_profile); const m = el.dataset.arg; setDraft({ photo_mode: m === 'SIDEBAR' && fam !== 'digital_creative' ? 'HEADER' : m }); },
  'design-auto': () => {
    const p = curPack(); const au = designFor(p.analysis, p.strategy, p.offer.text);
    setDraft({ design_profile: au.design, palette: au.palette, density: au.density, photo_mode: au.photo_mode, design_why: au.why, density_locked: false });
    toast(`Auto : ${DESIGN_NAME(au.design)} · ${paletteLabel(au.palette)}. Détail dans « Pourquoi ce design ? ».`, 'i-wand');
  },
  'studio-save': async () => { const p = curPack(); const ch = studioDraft(p, cvIdx(p)) || {}; const what = Object.keys(ch).filter((k) => k !== 'design_why' && k !== 'density_locked').map((k) => ({ design_profile: `design ${DESIGN_NAME(ch.design_profile)}`, palette: `couleurs ${paletteLabel(ch.palette)}`, density: `densité ${DENSITY_LABEL[ch.density]}`, photo_mode: PHOTO_LABEL[ch.photo_mode], colors: '' })[k]).filter(Boolean);
    await newCvVersion(`Présentation : ${what.join(', ') || 'mise en page'}`, () => {}, { presentationOnly: true }); },
  'studio-reset': () => { S.studio = null; render(); },
  'set-headline': async () => { const v = (($('#f-headline') || {}).value || '').trim(); if (!v) return; await newCvVersion('Titre modifié', (d) => { const h = E.sectionLines(d, 'headline')[0]; if (h) h.text = v; }); },
  'exp-up': async (el) => { const i = Number(el.dataset.arg); await newCvVersion('Ordre des expériences', (d) => { const x = d.experiences.splice(i, 1)[0]; d.experiences.splice(i - 1, 0, x); }); },
  'exp-down': async (el) => { const i = Number(el.dataset.arg); await newCvVersion('Ordre des expériences', (d) => { const x = d.experiences.splice(i, 1)[0]; d.experiences.splice(i + 1, 0, x); }); },
  'rewrite-summary': async () => {
    const p = curPack(); const P = Pp(); const a = p.analysis; toast(`${AI.short()} réécrit l'accroche…`, 'i-wand');
    await newCvVersion('Accroche réécrite', (d) => sideTask(async () => {
      const ins = {}; E.sectionLines(d, 'summary').forEach((l) => { ins[l.id] = 'Réécrire plus percutant et plus spécifique à l\'offre, 45 mots max au total, sans rien ajouter qui ne soit dans les faits.'; });
      const r = await fixLoop(d.lines, E.Validator(S.profile, p.offer.text, [a.job_title, a.company]), P, a, { instructions: ins });
      d.lines = r.lines; d.removed_lines = (d.removed_lines || []).concat(r.removed); E.syncBlocks(d);
    }));
  },
  'set-letter-layout': async (el) => {
    const p = clone(curPack()); const L = p.letters[p.letter_index]; const f = el.dataset.arg; if ((L.doc.layout || p.cvs[p.cv_index].doc.design_profile) === f) return;
    const v = Math.max(...p.letters.map((x) => x.v || 0)) + 1;
    p.letters.push(Object.assign(clone(L), { v, label: `V${v}`, created_at: nowIso(), doc: Object.assign(clone(L.doc), { layout: f }), change: `mise en page ${DESIGN_NAME(f)}` }));
    p.letter_index = p.letters.length - 1; refreshStatus(p); await Store.savePack(p); toast(`Lettre V${v} : mise en page ${DESIGN_NAME(f)}.`, 'i-check');
  },

  // ── Téléchargements ──
  'dl-cv': async () => {
    if (draftPending()) { toast('Enregistre d\'abord l\'aperçu en nouvelle version (ou annule-le) : seul un document versionné se télécharge.', 'i-info'); return; }
    const p = curPack(); const e = p.cvs[cvIdx(p)]; const bytes = await PDF.build(PDF.cvDef(e.doc));
    await save(`CV_${fileBase(p)}.pdf`, new Blob([bytes], { type: 'application/pdf' }));
  },
  'dl-letter': async () => { const p = curPack(); const P = Pp(); const L = p.letters[p.letter_index]; const bytes = await PDF.build(PDF.letterDef(L.doc, p.cvs[p.cv_index].doc, P)); await save(`Lettre_${fileBase(p)}.pdf`, new Blob([bytes], { type: 'application/pdf' })); },
  'dl-json': async () => { const p = curPack(); await save(`pack_${fileBase(p)}.json`, JSON.stringify(p, null, 2)); },
  'dl-zip': async () => {
    const p = curPack(); const P = Pp(); if (!window.JSZip) { toast('JSZip indisponible.', 'i-alert'); return; }
    toast('Préparation du pack…', 'i-download');
    const z = new window.JSZip(); const b = fileBase(p);
    if (p.cvs.length) z.file(`CV_${b}.pdf`, await PDF.build(PDF.cvDef(p.cvs[p.cv_index].doc)));
    if (p.letters.length) z.file(`Lettre_${b}.pdf`, await PDF.build(PDF.letterDef(p.letters[p.letter_index].doc, p.cvs[p.cv_index].doc, P)));
    z.file('pack.json', JSON.stringify(p, null, 2)); z.file('pack.md', packMarkdown(p)); z.file('versions.json', JSON.stringify(p.versions, null, 2)); z.file('offre.txt', p.offer.text);
    await save(`PAI_Pack_${b}.zip`, await z.generateAsync({ type: 'blob' }));
  },
  'answer-save': async (el) => { const p = clone(curPack()); const i = Number(el.dataset.arg); p.answers[i].user_answer = ($(`#ans-${i}`) || {}).value || ''; await Store.savePack(p); toast('Réponse enregistrée dans le pack.', 'i-check'); },
  'chat-send': async () => {
    const inp = $('#chat-in'); const msg = (inp && inp.value || '').trim(); if (!msg || !AI.ok()) return;
    const p = curPack(); const P = Pp(); if (S.chat.pack !== p.id) S.chat = { pack: p.id, turns: [], busy: false };
    S.chat.turns.push({ role: 'user', content: msg }); S.chat.busy = true; render();
    const rules = E.render('chat', { candidate_name: P.value('id.name'), facts_table: E.factsTable(P), offer_context: `${p.analysis.job_title} · ${p.analysis.company} — ${p.offer.text.slice(0, 2500)}`, truth_rules: E.truthRules(P) });
    const reply = { role: 'assistant', content: '…' }; const turns = [{ role: 'user', content: rules }].concat(S.chat.turns.slice(-10)); S.chat.turns.push(reply);
    try { const r = await S.caps.sample(turns, { modelTier: 'quick', cache: false, onText: ({ text }) => { reply.content = text; const log = $('#chat-log'); if (log && log.lastElementChild) log.lastElementChild.textContent = text; } }); reply.content = r.text; }
    catch (e) { reply.content = e && e.text ? e.text : AI.message(e); }
    S.chat.busy = false; render();
  },

  // ── Avis, Training Lab ──
  'fb-rate': (el) => { S.fbRate = Number(el.dataset.arg); render(); },
  'fb-reason': (el) => { const r = el.dataset.arg; S.fbReasons = S.fbReasons.includes(r) ? S.fbReasons.filter((x) => x !== r) : S.fbReasons.concat([r]); render(); },
  'fb-save': async (el) => {
    if (S.fbRate === undefined) { toast('Choisis 👍, 😐 ou 👎.', 'i-info'); return; }
    const p = curPack(); const [doc, idx] = el.dataset.arg.split(':');
    await saveFeedback(p, doc, Number(idx), S.fbRate, S.fbReasons.slice(), S.fbComment || '');
    S.fbRate = undefined; S.fbReasons = []; S.fbComment = ''; toast('Avis enregistré : il nourrira les prochaines versions.', 'i-check'); render();
  },
  'lab-v2': (el) => { S.lab.packId = el.dataset.arg; if (S.fbRate !== undefined) S.lab.rate = S.fbRate; if (S.fbReasons.length) S.lab.reasons = S.fbReasons.slice(); S.view = 'lab'; render(); },
  'lab-open': (el) => { S.lab.packId = el.dataset.arg; S.lab.rate = undefined; S.lab.reasons = []; render(); },
  'lab-rate': (el) => { S.lab.rate = Number(el.dataset.arg); render(); },
  'lab-reason': (el) => { const r = el.dataset.arg; S.lab.reasons = S.lab.reasons.includes(r) ? S.lab.reasons.filter((x) => x !== r) : S.lab.reasons.concat([r]); render(); },
  'lab-generate': async (el) => {
    const p = packById(el.dataset.arg); if (!p) return;
    if (S.lab.rate === undefined) { toast('Choisis d\'abord ton verdict : 👍, 😐 ou 👎.', 'i-info'); return; }
    const reasons = S.lab.reasons.slice(); const comment = S.lab.comment || '';
    await saveFeedback(p, 'cv', p.cvs.length - 1, S.lab.rate, reasons, comment);
    S.lab.busy = true; S.packId = p.id; lsSet('packId', p.id); render();
    try { const v = await regenerateWithFeedback(p, reasons, comment); if (v) { S.lab.rate = undefined; S.lab.reasons = []; S.lab.comment = ''; } }
    finally { S.lab.busy = false; render(); }
  },

  // ── Learning ──
  'propose-det': async () => {
    const have = new Set((S.rules.proposals || []).concat(S.rules.accepted || []).map((r) => r.rule_text));
    const props = deterministicProposals().filter((r) => !have.has(r.rule_text)).map((r) => Object.assign({ id: uid('rule'), status: 'proposed', created_at: nowIso() }, r));
    if (!props.length) { toast(`Pas de motif négatif répété au-dessus du seuil : INSUFFICIENT DATA.`, 'i-info'); return; }
    await Store.saveRules(Object.assign({}, S.rules, { proposals: (S.rules.proposals || []).concat(props) })); toast(`${props.length} règle(s) proposée(s) : à toi de décider.`, 'i-bulb');
  },
  'propose-rules': async () => {
    toast('Analyse de tes avis…', 'i-spark');
    const min = ((D.scoring || {}).learning || {}).min_feedback_for_trend || 5;
    try {
      const out = await AI.ask('learning_rules', { feedback_json: JSON.stringify(S.feedback.slice(0, 150).map((f) => ({ id: f.id, context: f.context, element: f.element, reasons: f.reasons, rating: f.rating, comment: f.comment, strategy: f.strategy }))),
        existing_rules: (S.rules.accepted || []).map((r) => r.rule_text).join('\n') || 'aucune', min_feedback: String(min) }, { cache: false });
      const props = (out.proposals || []).filter((r) => Number(r.n_cases) >= min).map((r) => Object.assign({ id: uid('rule'), status: 'proposed', created_at: nowIso(), source: 'IA' }, r));
      await Store.saveRules(Object.assign({}, S.rules, { proposals: (S.rules.proposals || []).concat(props) }));
      toast(props.length ? `${props.length} règle(s) proposée(s).` : `Pas assez d'avis concordants (${min} minimum par contexte) : INSUFFICIENT DATA.`, 'i-bulb');
    } catch (e) { toast(AI.message(e), 'i-alert'); }
  },
  'rule-accept': async (el) => { const r = (S.rules.proposals || []).find((x) => x.id === el.dataset.arg); if (!r) return; r.status = 'accepted'; r.accepted_at = nowIso(); await Store.saveRules(Object.assign({}, S.rules, { accepted: (S.rules.accepted || []).concat([r]), rules_version: (S.rules.rules_version || 0) + 1 })); toast('Règle acceptée : nouvelle version des règles.', 'i-check'); },
  'rule-refuse': async (el) => { const r = (S.rules.proposals || []).find((x) => x.id === el.dataset.arg); if (!r) return; r.status = 'refused'; await Store.saveRules(Object.assign({}, S.rules)); },
  'rule-remove': async (el) => { await Store.saveRules(Object.assign({}, S.rules, { accepted: (S.rules.accepted || []).filter((x) => x.id !== el.dataset.arg), rules_version: (S.rules.rules_version || 0) + 1 })); toast('Règle retirée.', 'i-info'); },
  'ja-accept': async () => {
    const imp = S.jobImport; const picked = imp.items.filter((x) => x.pick); if (!picked.length) { toast('Sélectionne au moins un élément.', 'i-info'); return; }
    const src = imp.origin === 'document' ? 'document' : 'jobagent';
    await mutateProfile((p) => { picked.forEach((it, i) => { const id = `${src === 'document' ? 'doc' : 'ja'}.${imp.hash}.${i + 1}`; if (p.facts.some((f) => f.id === id)) return;
      p.facts.push({ id, kind: it.kind, text: it.text, data: {}, status: 'UNVERIFIED', source: `${src}:${imp.name}`, provenance: `${imp.name}#${it.path} (sha:${imp.hash})`, confidence: 0.5, parent: null, terms: [], needs_confirmation: true, approved: false, note: `Importé (${src === 'document' ? 'ancien document' : 'JobAgent'}) : à confirmer`, created_at: nowIso(), updated_at: nowIso() });
      p.review_queue = (p.review_queue || []).concat([{ fact_id: id, reason: `Import ${src === 'document' ? 'd\'un ancien document' : 'JobAgent'} : confirmer ou écarter`, severity: 'warning' }]); }); }, `${src}_import`, `${picked.length} élément(s) de ${imp.name}`);
    if (src === 'jobagent') await Store.addDoc('jobagent', { id: uid('ja'), name: imp.name, hash: imp.hash, total: imp.items.length, accepted: picked.length, created_at: nowIso() });
    S.jobImport = null; render();
  },
  'ja-cancel': () => { S.jobImport = null; render(); },

  // ── Benchmark ──
  'arena-new': () => { const src = arenaSources(); if (!src.length) return; const pick = src[Math.floor(Math.random() * src.length)]; S.arenaPair = Object.assign({}, pick, { flip: Math.random() < 0.5, revealed: false }); render(); },
  'arena-vote': async (el) => {
    const pair = S.arenaPair; const choice = el.dataset.arg; const X = pair.flip ? pair.b : pair.a; const Y = pair.flip ? pair.a : pair.b;
    const vote = { id: uid('vote'), pair_id: pair.id, kind: pair.kind, synthetic: !!pair.synthetic, title: pair.title, shown: { X: X.label, Y: Y.label }, choice, choice_label: choice === 'TIE' ? 'Égalité' : (choice === 'X' ? X : Y).label, reason: ($('#arena-reason') || {}).value || '', created_at: nowIso(), judge: null };
    await Store.addDoc('arena', vote); pair.revealed = true; pair.vote = vote; render();
  },
  'arena-judge': async () => {
    const pair = S.arenaPair; const X = pair.flip ? pair.b : pair.a; const Y = pair.flip ? pair.a : pair.b; toast('Le juge IA compare dans les deux ordres…', 'i-scale');
    try {
      const r1 = await AI.ask('judge_pair', { offer_summary: pair.offer, doc_a: X.text.slice(0, 9000), doc_b: Y.text.slice(0, 9000) }, { cache: false });
      const r2 = await AI.ask('judge_pair', { offer_summary: pair.offer, doc_a: Y.text.slice(0, 9000), doc_b: X.text.slice(0, 9000) }, { cache: false });
      const w1 = r1.winner; const w2 = r2.winner === 'X' ? 'Y' : r2.winner === 'Y' ? 'X' : 'TIE'; const winner = w1 === w2 ? w1 : 'TIE';
      pair.judge = { winner, winner_label: winner === 'TIE' ? 'Égalité / désaccord entre les deux ordres' : (winner === 'X' ? X : Y).label, orders: [r1, r2] };
      if (pair.vote) await Store.addDoc('arena', Object.assign({}, pair.vote, { judge: pair.judge }));
      render();
    } catch (e) { toast(AI.message(e), 'i-alert'); }
  },

  // ── Profil ──
  'profile-filter': (el) => { S.profileFilter = el.dataset.arg; render(); },
  'profile-validate': async () => {
    if (conflicts(S.profile).length) { toast('Tranche d\'abord les conflits.', 'i-alert'); return; }
    const p = clone(S.profile); p.validated = true; p.validated_at = nowIso();
    await Store.saveProfile(p, 'validate', `Profil v${p.version} validé`);
    if (Store.db) await Store.put(`profile_versions/v${p.version}`, Object.assign({}, p, { tag: profileTag(p) }));
    toast(`Profil v${p.version} validé : tes prochains packs pourront passer en FINAL.`, 'i-shield');
  },
  'profile-export': async (el) => {
    const p = S.profile; const f = el.dataset.arg;
    if (f === 'json') await save(`master_profile_v${p.version}.json`, JSON.stringify(p, null, 2));
    if (f === 'csv') await save(`master_profile_v${p.version}.csv`, ['id,kind,status,text,parent,source,provenance'].concat(p.facts.map((x) => [x.id, x.kind, x.status, x.text, x.parent || '', x.source, x.provenance || ''].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))).join('\n'));
    if (f === 'md') await save(`master_profile_v${p.version}.md`, `# Master Profile v${p.version}\n\n` + p.facts.map((x) => `- \`${x.id}\` **${x.status}** — ${x.text}`).join('\n') + '\n');
  },
  'conflict-pick': async (el) => {
    const [si, pick] = el.dataset.arg.split(':'); const i = Number(si); const r = S.profile.review_queue[i]; if (!r) return;
    const { A, B, other } = conflictPair(r, S.profile);
    await mutateProfile((p) => {
      const fa = A && p.facts.find((f) => f.id === A.id); const fb = B && p.facts.find((f) => f.id === B.id);
      if (pick === 'A') { if (fa) confirmFact(fa, 'Conflit tranché : source A retenue'); if (fb) discardFact(fb, `Écarté : conflit tranché en faveur de ${fa ? fa.id : 'A'}`); }
      if (pick === 'B') { if (fb) { confirmFact(fb, 'Conflit tranché : source B retenue'); if (fa) discardFact(fa, `Écarté : conflit tranché en faveur de ${fb.id}`); } else if (fa && other) { fa.text = other; confirmFact(fa, 'Conflit tranché : texte B retenu'); } }
      if (pick === 'BOTH') { if (fa) confirmFact(fa, fb ? `Distinct de ${fb.id} (confirmé par toi)` : ''); if (fb) confirmFact(fb, fa ? `Distinct de ${fa.id} (confirmé par toi)` : ''); }
      p.review_queue = (p.review_queue || []).filter((x, j) => j !== i);
    }, 'conflict_resolve', `${r.fact_id} → ${pick === 'BOTH' ? 'les deux' : pick}`);
  },
  'conflict-edit': (el) => { S.conflictEdit = Number(el.dataset.arg); render(); },
  'conflict-edit-cancel': () => { S.conflictEdit = null; render(); },
  'conflict-edit-save': async (el) => {
    const i = Number(el.dataset.arg); const r = S.profile.review_queue[i]; const text = (($('#cf-text') || {}).value || '').trim(); if (!r || text.length < 2) return;
    const { A, B } = conflictPair(r, S.profile);
    await mutateProfile((p) => {
      const keep = p.facts.find((f) => f.id === (B || A).id); const drop = B && A ? p.facts.find((f) => f.id === A.id) : null;
      if (keep) { keep.text = text; confirmFact(keep, 'Conflit tranché : énoncé corrigé par toi'); }
      if (drop) discardFact(drop, `Fusionné dans ${keep ? keep.id : '—'}`);
      p.review_queue = (p.review_queue || []).filter((x, j) => j !== i);
    }, 'conflict_edit', r.fact_id);
    S.conflictEdit = null;
  },
  'fact-edit': (el) => { S.editFact = el.dataset.arg; render(); },
  'fact-cancel': () => { S.editFact = null; render(); },
  'fact-save': async (el) => {
    const id = el.dataset.arg; const text = ($('#ef-text') || {}).value || ''; const status = ($('#ef-status') || {}).value;
    await mutateProfile((p) => { const f = p.facts.find((x) => x.id === id); if (!f) return; f.text = text.trim() || f.text; f.status = status; f.updated_at = nowIso(); if (status === 'CONFIRMED') confirmFact(f); p.review_queue = (p.review_queue || []).filter((r) => r.fact_id !== id || status === 'UNVERIFIED'); }, 'fact_edit', id);
    S.editFact = null;
  },
  'fact-confirm': async (el) => { const id = el.dataset.arg; await mutateProfile((p) => { const f = p.facts.find((x) => x.id === id); if (f) confirmFact(f); p.review_queue = (p.review_queue || []).filter((r) => r.fact_id !== id || r.severity === 'conflict'); }, 'fact_confirm', id); },
  'fact-add': async () => {
    const text = (($('#nf-text') || {}).value || '').trim(); if (text.length < 2) { toast('Écris l\'énoncé exact du fait.', 'i-info'); return; }
    const kind = ($('#nf-kind') || {}).value || 'other'; const parent = ($('#nf-parent') || {}).value || null;
    await mutateProfile((p) => { p.facts.push({ id: `${kind}.u${Date.now().toString(36)}`, kind, text, data: {}, status: 'CONFIRMED', source: 'user:pai_studio', provenance: nowIso(), confidence: 1, parent, terms: [], needs_confirmation: false, approved: false, note: '', created_at: nowIso(), updated_at: nowIso() }); }, 'fact_add', text.slice(0, 60));
    S.newFactText = '';
  },
  'unknown-fill': (el) => { S.newFactText = ''; S.profileFilter = 'all'; S.profileFocus = 'add-fact'; render(); toast(`À renseigner : ${el.dataset.arg}`, 'i-info'); },
  'review-confirm': async (el) => { const i = Number(el.dataset.arg); const r = S.profile.review_queue[i]; await mutateProfile((p) => { const f = p.facts.find((x) => x.id === r.fact_id); if (f) confirmFact(f); p.review_queue.splice(i, 1); }, 'review_confirm', r.fact_id); },
  'review-reject': async (el) => { const i = Number(el.dataset.arg); const r = S.profile.review_queue[i]; await mutateProfile((p) => { const f = p.facts.find((x) => x.id === r.fact_id); if (f) discardFact(f, 'Écarté par toi'); p.review_queue.splice(i, 1); }, 'review_reject', r.fact_id); },
  'review-dismiss': async (el) => { const i = Number(el.dataset.arg); await mutateProfile((p) => { p.review_queue.splice(i, 1); }, 'review_dismiss', '', true); },

  // ── Photo ──
  'photo-size': async (el) => { if (!S.photo) return; await Store.savePhoto(Object.assign({}, S.photo, { scale: Number(el.dataset.arg), updated_at: nowIso() })); },
  'photo-mode': async (el) => { await Store.savePrefs(Object.assign({}, S.prefs, { photo_mode: el.dataset.arg })); toast(`Photo : ${({ AUTO: 'PAI décide', HEADER: 'en-tête', SIDEBAR: 'colonne', OFF: 'jamais' })[el.dataset.arg]} pour les prochains CV.`, 'i-camera'); },
  'photo-delete': async () => { await Store.savePhoto(null); toast('Photo retirée de PAI.', 'i-info'); },

  // ── Onboarding, préférences ──
  'ob-step': (el) => { S.onboard = Number(el.dataset.arg); render(); },
  'ob-done': async (el) => {
    const k = el.dataset.arg; const ob = Object.assign({ done: {} }, (S.prefs || {}).onboarding); ob.done = Object.assign({}, ob.done, { [k]: true });
    if (OB_STEPS.every(([x]) => ob.done[x])) ob.finished_at = ob.finished_at || nowIso();
    await Store.savePrefs(Object.assign({}, S.prefs, { onboarding: ob }));
    const next = OB_STEPS.findIndex(([x]) => !ob.done[x]); S.onboard = next < 0 ? OB_STEPS.length - 1 : next; render();
  },
  'pref-design': async (el) => { await Store.savePrefs(Object.assign({}, S.prefs, { design: el.dataset.arg })); },
  'pref-palette': async (el) => { await Store.savePrefs(Object.assign({}, S.prefs, { palette: el.dataset.arg })); },
  'doc-review': (el) => { const d = S.documents.find((x) => x.id === el.dataset.arg); if (!d || !d.text) { toast('Texte du document indisponible.', 'i-info'); return; } S.jobImport = Object.assign(parseJobAgent(d.name, d.text), { origin: 'document' }); render(); },

  // ── Réglages ──
  theme: (el) => { S.themeChoice = el.dataset.arg; lsSet('theme', S.themeChoice); applyTheme(); render(); },
  'ai-open': (el) => { S.server.aiOpen = S.server.aiOpen === el.dataset.arg ? '__none__' : el.dataset.arg; render(); },
  'ai-test': async (el) => {
    const id = el.dataset.arg; S.server.aiTest[id] = { busy: true }; render();
    try {
      if (!SERVER) { const t0 = performance.now(); const r = await S.caps.sample('Réponds uniquement par OK.', { modelTier: 'quick', cache: false }); S.server.aiTest[id] = { ok: /ok/i.test(String(r.text || '')), latency_ms: Math.round(performance.now() - t0), model: r.modelTierApplied || 'quick', error: /ok/i.test(String(r.text || '')) ? '' : 'Réponse inattendue' }; }
      else S.server.aiTest[id] = await Srv.req('POST', '/v1/settings/ai/test', { provider: id });
    } catch (e) { S.server.aiTest[id] = { ok: false, error: (e && (e.message || e.code)) || 'erreur' }; if (!SERVER && e && AI_DENIED.includes(e.code)) S.ai = 'denied'; }
    render();
  },
  'ai-activate': async (el) => { try { S.server.ai = await Srv.req('PUT', '/v1/settings/ai', { active: el.dataset.arg }); await Srv.loadStatus(); toast(`Fournisseur actif : ${PROVIDER_LABEL[el.dataset.arg] || el.dataset.arg}.`, 'i-plug'); } catch (e) { toast(`Impossible : ${(e && e.message) || e}`, 'i-alert'); } render(); },
  'ai-save': async (el) => {
    const id = el.dataset.arg; const body = { provider: id };
    const key = (($(`#ai-key-${id}`) || {}).value || '').trim(); if (key) body.api_key = key;
    const model = $(`#ai-model-${id}`); if (model) body.model = model.value.trim();
    const url = $(`#ai-url-${id}`); if (url) body.base_url = url.value.trim();
    try { S.server.ai = await Srv.req('PUT', '/v1/settings/ai', body); await Srv.loadStatus(); toast('Réglages IA enregistrés (clé chiffrée, jamais réaffichée).', 'i-check'); } catch (e) { toast(`Refusé : ${(e && e.message) || e}`, 'i-alert'); }
    render();
  },
  'ai-clear': async (el) => { try { S.server.ai = await Srv.req('PUT', '/v1/settings/ai', { provider: el.dataset.arg, clear_key: true }); await Srv.loadStatus(); toast('Clé effacée.', 'i-info'); } catch (e) { toast(`Refusé : ${(e && e.message) || e}`, 'i-alert'); } render(); },
  backup: async () => { await save(`pai_backup_${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify({ exported_at: nowIso(), versions: D.version, profile: S.profile, packs: S.packs, feedback: S.feedback, arena: S.arena, rules: S.rules, jobagent: S.jobagent, prefs: S.prefs }, null, 2)); },
  'pack-delete-ask': (el) => { S.confirmDel = el.dataset.arg; render(); },
  'pack-delete-cancel': () => { S.confirmDel = null; render(); },
  'pack-delete': async (el) => { const p = packById(el.dataset.arg); if (!p) return; S.confirmDel = null; await Store.savePack(Object.assign(clone(p), { deleted_at: nowIso() })); if (!Store.db) S.packs = S.packs.filter((x) => x.id !== p.id); toast('Pack supprimé.', 'i-info'); render(); },
};

// ─── Événements ──────────────────────────────────────────────────────────────
document.addEventListener('click', (ev) => {
  const el = ev.target.closest('[data-act]'); if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
  const fn = ACT[el.dataset.act]; if (!fn) return;
  ev.preventDefault();
  Promise.resolve(fn(el, ev)).catch((e) => { console.error(e); toast(`Action impossible : ${(e && e.message) || e}`, 'i-alert'); });
});
const setPath = (path, v) => { const ks = path.split('.'); let o = S; ks.slice(0, -1).forEach((k) => { o = o[k]; }); o[ks[ks.length - 1]] = v; };
function updateCmdChrome() {
  const t = $('#cmd-input'); if (!t) return; const raw = S.draft.input || ''; const isUrl = looksLikeUrl(raw);
  const tall = S.draft.textMode || (!isUrl && raw.includes('\n')); t.classList.toggle('tall', tall);
  const use = $('#command .lead-ico use'); if (use) use.setAttribute('href', `#${isUrl ? 'i-link' : tall ? 'i-text' : 'i-spark'}`);
  const h = $('#cmd-hint'); if (h) h.textContent = cmdHint(); autoGrow();
}
document.addEventListener('input', (ev) => {
  const t = ev.target; const b = t.dataset && t.dataset.bind;
  if (b) {
    setPath(b, t.value);
    if (b === 'draft.input') { if (!t.value.trim()) { S.draft.sourceType = 'text'; S.draft.fileName = ''; } S.draft.synthetic = false; if (S.draft.notice) { S.draft.notice = null; const n = $('#command .notice'); if (n) n.remove(); } updateCmdChrome(); }
    return;
  }
  if (t.dataset && t.dataset.change === 'photo-zoom' && S.photo) { S.photo.crop = Object.assign({}, S.photo.crop, { zoom: Number(t.value) }); const img = $('#photo-frame img'); if (img) img.setAttribute('style', Photo.frameStyle(S.photo, 150)); }
});
document.addEventListener('change', async (ev) => {
  const t = ev.target; const kind = t.dataset && t.dataset.change; if (!kind) return;
  try {
    if (kind === 'offer-pdf' && t.files[0]) { await readOfferPdf(t.files[0]); if (S.view === 'analyser' && !S.run) render(); }
    if (kind === 'profile-file' && t.files[0]) {
      const data = JSON.parse(await t.files[0].text());
      if (!data || !Array.isArray(data.facts)) throw new Error('Ce fichier n\'est pas un Master Profile PAI.');
      await Store.saveProfile(Object.assign({ review_queue: [], unknowns: [], history: [] }, data), 'import', t.files[0].name); toast(`Profil importé (${data.facts.length} faits).`, 'i-user');
    }
    if (kind === 'photo-file' && t.files[0]) await setPhotoFromFile(t.files[0]);
    if (kind === 'photo-zoom' && S.photo) await Store.savePhoto(Object.assign({}, S.photo, { crop: Object.assign({}, S.photo.crop, { zoom: Number(t.value) }), updated_at: nowIso() }));
    if (kind === 'doc-files' && t.files.length) {
      for (const f of [...t.files].slice(0, 6)) {
        const text = await PDF.offerTextFromFile(f); if (text.length < 40) { toast(`${f.name} : aucun texte lisible.`, 'i-alert'); continue; }
        const n = E.norm(text.slice(0, 1500)); const kindDoc = /madame|monsieur|objet :|lettre de motivation|cordialement/.test(n) ? 'letter' : 'cv';
        const doc = { id: uid('doc'), name: f.name.slice(0, 80), kind: kindDoc, hash: E.hash(text).slice(0, 7), chars: text.length, text: text.slice(0, 20000), created_at: nowIso() };
        await Store.addDoc('documents', doc); S.jobImport = Object.assign(parseJobAgent(doc.name, doc.text), { origin: 'document' });
      }
      toast('Documents importés : choisis les éléments à ajouter (en « À vérifier »).', 'i-file'); render();
    }
    if (kind === 'ja-file' && t.files[0]) { S.jobImport = Object.assign(parseJobAgent(t.files[0].name, await t.files[0].text()), { origin: 'jobagent' }); render(); }
    if (kind === 'ja-pick') S.jobImport.items[Number(t.dataset.arg)].pick = t.checked;
    if (kind === 'ja-kind') S.jobImport.items[Number(t.dataset.arg)].kind = t.value;
    if (kind === 'compare-a') { S.compareWith = Number(t.value); render(); }
    if (kind === 'compare-b') { S.cvIndex = Number(t.value); render(); }
    if (kind === 'studio-pack') { S.packId = t.value; lsSet('packId', t.value); S.cvIndex = null; S.studio = null; render(); }
    if (kind === 'lab-pack') { S.lab.packId = t.value; S.lab.rate = undefined; S.lab.reasons = []; render(); }
  } catch (e) { console.error(e); toast(`Import impossible : ${(e && e.message) || e}`, 'i-alert'); } finally { if (t.type === 'file') t.value = ''; }
});
document.addEventListener('toggle', (ev) => { const d = ev.target; if (d.dataset && d.dataset.toggle) S.draft[d.dataset.toggle] = d.open; }, true);
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && S.moreOpen) { setMore(false); return; }
  if (ev.target && ev.target.id === 'cmd-input' && ev.key === 'Enter') {
    const raw = ev.target.value.trim();
    if (ev.ctrlKey || ev.metaKey || (!ev.shiftKey && !S.draft.textMode && looksLikeUrl(raw))) { ev.preventDefault(); ACT.analyze(); }
  }
});

// Glisser-déposer : PDF d'offre sur le champ de commande, image sur la carte photo. Jamais de navigation vers le fichier.
const hasFiles = (ev) => ev.dataTransfer && [...(ev.dataTransfer.types || [])].includes('Files');
document.addEventListener('dragover', (ev) => {
  if (!hasFiles(ev)) return; ev.preventDefault();
  const cmd = ev.target.closest && ev.target.closest('#command'); const ph = ev.target.closest && ev.target.closest('#photo-card');
  $$('.command.drag, #photo-card.drag').forEach((x) => { if (x !== cmd && x !== ph) x.classList.remove('drag'); });
  if (cmd) cmd.classList.add('drag'); if (ph) ph.classList.add('drag');
  ev.dataTransfer.dropEffect = cmd || ph ? 'copy' : 'none';
});
document.addEventListener('dragleave', (ev) => { if (ev.target.closest && !ev.relatedTarget) $$('.command.drag, #photo-card.drag').forEach((x) => x.classList.remove('drag')); });
document.addEventListener('drop', async (ev) => {
  if (!hasFiles(ev)) return; ev.preventDefault();
  const cmd = ev.target.closest && ev.target.closest('#command'); const ph = ev.target.closest && ev.target.closest('#photo-card');
  $$('.command.drag, #photo-card.drag').forEach((x) => x.classList.remove('drag'));
  const f = ev.dataTransfer.files[0]; if (!f) return;
  try {
    if (ph && /^image\//.test(f.type)) await setPhotoFromFile(f);
    else if (cmd && /pdf$/i.test(f.type || f.name)) await readOfferPdf(f);
    else if (cmd) toast('Dépose un PDF (ou colle le texte / le lien).', 'i-info');
  } catch (e) { toast(`Import impossible : ${(e && e.message) || e}`, 'i-alert'); }
});

// Recadrage de la photo : glisser dans le cadre (souris, doigt ou stylet).
let drag = null;
document.addEventListener('pointerdown', (ev) => {
  const fr = ev.target.closest && ev.target.closest('#photo-frame'); if (!fr || !S.photo) return;
  ev.preventDefault(); fr.setPointerCapture(ev.pointerId);
  drag = { x: ev.clientX, y: ev.clientY, crop: Object.assign({}, S.photo.crop), side: Photo.rect(S.photo).side, fr };
  fr.classList.add('dragging');
});
document.addEventListener('pointermove', (ev) => {
  if (!drag || !S.photo) return; const k = 150 / drag.side;
  const p = S.photo; const nx = drag.crop.x - (ev.clientX - drag.x) / k / p.w; const ny = drag.crop.y - (ev.clientY - drag.y) / k / p.h;
  p.crop = Object.assign({}, p.crop, { x: Math.max(0, Math.min(1, nx)), y: Math.max(0, Math.min(1, ny)) });
  const r = Photo.rect(p); p.crop.x = (r.sx + r.side / 2) / p.w; p.crop.y = (r.sy + r.side / 2) / p.h;
  const img = $('img', drag.fr); if (img) img.setAttribute('style', Photo.frameStyle(p, 150));
});
const endDrag = async () => { if (!drag) return; const d = drag; drag = null; d.fr.classList.remove('dragging'); if (JSON.stringify(d.crop) !== JSON.stringify(S.photo.crop)) await Store.savePhoto(Object.assign({}, S.photo, { updated_at: nowIso() })); };
document.addEventListener('pointerup', endDrag); document.addEventListener('pointercancel', endDrag);

// Preuves : survoler une ligne affiche les faits qui la prouvent.
let pop = null;
document.addEventListener('mouseover', (ev) => {
  const el = ev.target.closest && ev.target.closest('.sheet [data-line]'); const p = curPack();
  if (!el || !p || !S.profile) { if (pop && !(ev.target.closest && ev.target.closest('.popover'))) { pop.remove(); pop = null; } return; }
  const docs = p.cvs.map((c) => c.doc).concat(p.letters.map((l) => l.doc));
  const line = docs.flatMap((d) => d.lines).find((l) => l.id === el.dataset.line); if (!line) return;
  const P = Pp(); const facts = (line.fact_ids || []).map((id) => P.fact(id)).filter(Boolean);
  if (!pop) { pop = document.createElement('div'); pop.className = 'popover'; document.body.appendChild(pop); }
  pop.innerHTML = `<div class="row between" style="margin-bottom:6px"><span class="fid">${esc(line.id)}</span>${chip(line.kind)}</div>${facts.length ? facts.map((f) => `<div class="ft"><div>${esc(f.text)}</div><div class="muted xs"><span class="fid">${esc(f.id)}</span> ${statusChip(f.status)}</div></div>`).join('') : `<div class="muted">${line.kind === 'offer_ref' ? `Citation de l'offre : « ${esc(line.offer_quote)} »` : line.kind === 'headline' ? 'Titre visé (intitulé de l\'offre), pas un poste occupé.' : line.kind === 'projection' || line.kind === 'closing' ? 'Phrase de projection : aucune affirmation de fait.' : 'Aucun fait lié.'}</div>`}`;
  const r = el.getBoundingClientRect(); const top = Math.min(window.innerHeight - pop.offsetHeight - 8, r.bottom + 6); const left = Math.min(window.innerWidth - pop.offsetWidth - 8, Math.max(8, r.left));
  pop.style.top = `${Math.max(8, top)}px`; pop.style.left = `${left}px`;
});
window.addEventListener('resize', () => { fitSheets(); });
window.addEventListener('scroll', () => { const tb = $('#topbar'); if (tb) tb.classList.toggle('scrolled', window.scrollY > 4); }, { passive: true });
window.addEventListener('hashchange', () => { const h = location.hash.slice(1); const v = ALIASES[h] || h; if (v && V[v]) { S.view = v; render(); } });
