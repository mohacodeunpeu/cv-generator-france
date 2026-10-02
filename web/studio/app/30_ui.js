// ─── Composants partagés ─────────────────────────────────────────────────────
const icon = (id, cls) => `<svg class="ico${cls ? ` ${cls}` : ''}" aria-hidden="true"><use href="#${id}"/></svg>`;
const chip = (text, t = '') => `<span class="chip ${t}">${esc(text)}</span>`;
const SEVERITY_LABEL = { high: 'Bloquant', medium: 'À revoir', low: 'Mineur', warning: 'À vérifier', warn: 'À vérifier', info: 'Info', conflict: 'Conflit' };
const statusChip = (s) => `<span class="chip ${STATUS_TONE[s] || ''}"><span class="dot"></span>${esc(STATUS_LABEL[s] || s)}</span>`;
const fids = (ids) => (ids || []).map((id) => `<span class="fid" data-fact="${esc(id)}">${esc(id)}</span>`).join(' ');
const CIRC = 2 * Math.PI * 15.5;
function ring(v, t, opts = {}) {
  const val = v === null || v === undefined || Number.isNaN(Number(v)) ? null : clamp(v);
  const off = val === null ? CIRC : CIRC * (1 - val / 100);
  return `<div class="ring ${t || ''} ${opts.size || ''}" role="img" aria-label="${esc(opts.label || '')} ${val === null ? 'non mesuré' : `${Math.round(val)} sur 100`}">
    <svg viewBox="0 0 36 36" aria-hidden="true"><circle class="trk" cx="18" cy="18" r="15.5"/><circle class="val" cx="18" cy="18" r="15.5" style="--circ:${CIRC.toFixed(1)};stroke-dasharray:${CIRC.toFixed(1)};stroke-dashoffset:${off.toFixed(1)}"/></svg>
    <span class="n">${val === null ? '—' : Math.round(val)}</span></div>`;
}
const bar = (v, t) => `<div class="bar ${t || tone(v)}"><i style="width:${clamp(v)}%"></i></div>`;
const packById = (id) => S.packs.find((p) => p.id === id) || null;
const curPack = () => packById(S.packId) || null;
const cvIdx = (p) => (S.cvIndex !== null && p.cvs[S.cvIndex] ? S.cvIndex : p.cv_index);
const fmtMs = (ms) => (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0).replace('.', ',')} s`);
const REASONS = ['Titre', 'Accroche', 'Expérience', 'Compétence', 'Design', 'Couleur', 'Photo', 'ATS', 'Personnalisation', 'Autre'];
const RATE = [[1, '👍', 'Bien'], [0, '😐', 'Moyen'], [-1, '👎', 'Pas bien']];
const rateIcon = (r) => (r === 1 ? '👍' : r === -1 ? '👎' : '😐');
const paletteLabel = (k) => (DS.PALETTES[k] ? DS.PALETTES[k].label : k);

// Brouillon de présentation (design, palette, densité, photo) : aperçu immédiat, enregistré en nouvelle version sur demande.
const studioDraft = (p, idx) => (S.studio && S.studio.packId === p.id && S.studio.index === idx ? S.studio.changes : null);
function viewDoc(p, idx) {
  const e = p.cvs[idx]; const ch = studioDraft(p, idx);
  return ch && Object.keys(ch).length ? Object.assign({}, e.doc, ch) : e.doc;
}

// ── Scores d'une version du CV : le Score PAI et ses six dimensions (moteur ATS, aucun chiffre inventé) ──
function cvScores(p, e, doc) {
  const r = atsFor(p, e, doc || e.doc); if (!r) return [];
  return [{ k: 'Score PAI', v: r.score.value }].concat(r.dimensions.filter((d) => r.main.includes(d.id)).map((d) => ({ k: d.label, v: d.value })));
}

// ── Pourquoi ce CV ? (tout vient des données du pack : rien d'inventé) ──
function whyThisCv(p, doc) {
  const s = p.strategy.best; const m = p.match; const P = Pp(); const out = [];
  out.push(`Titre «\u00a0${(E.sectionLines(doc, 'headline')[0] || {}).text || s.title}\u00a0» : aligné sur l'intitulé de l'offre (${p.analysis.job_title}).`);
  const up = (s.experiences_up || []).map((id) => P && P.fact(id)).filter(Boolean);
  if (up.length) out.push(`Mis en avant : ${up.map((f) => `${f.data.title || f.text} chez ${f.data.company || '—'}`).join(' puis ')}, parce que ces expériences prouvent le plus d'exigences.`);
  const r = atsFor(p, p.cvs[p.cv_index], doc);
  const req = r ? r.requirements.proven.filter((x) => x.class === 'MUST' && ['keyword', 'language'].includes(x.kind)) : [];
  if (req.length) out.push(`Exigences obligatoires prouvées et reprises : ${req.slice(0, 6).map((x) => x.text).join(', ')}.`);
  if (r) out.push(`Variante « ${r.variant.label} » : ${r.variant.angle.replace(/\.$/, '')} (${r.variant.why}).`);
  if (s.hook) {
    const hf = P && s.hook_fact_ids && s.hook_fact_ids[0] ? P.fact(s.hook_fact_ids[0]) : null; const ht = hf ? String(hf.text || '').trim() : '';
    out.push(`Accroche : ta preuve la plus forte pour cette offre${ht ? ` («\u00a0${ht.length > 80 ? `${ht.slice(0, 78).trimEnd()}…` : ht}\u00a0»)` : ''}.`);
  }
  const miss = r ? r.requirements.unproven.filter((x) => x.class === 'MUST').map((x) => x.text) : m.missing.filter((x) => x.priority === 'MUST').map((x) => x.requirement);
  if (miss.length) out.push(`Non écrit car non prouvé : ${miss.slice(0, 4).join(', ')} (à préparer pour l'entretien).`);
  out.push(`Angle ${s.ats_mode === 'ATS_FIRST' ? 'ATS d\'abord' : s.ats_mode === 'HUMAN_FIRST' ? 'recruteur d\'abord' : 'hybride'} : ${s.why || p.strategy.comparison || 'choix du profil secteur'}.`);
  return out;
}

// ── Qu'est-ce qui a changé ? (entre deux versions, ou depuis le profil pour V1) ──
function compareDocs(A, B) {
  const out = [];
  const head = (d) => (E.sectionLines(d, 'headline')[0] || {}).text || '';
  if (head(A) !== head(B)) out.push({ cls: 'mod', area: 'Titre', t: `« ${head(A)} » → « ${head(B)} »` });
  const sum = (d) => E.sectionLines(d, 'summary').map((l) => l.text).join(' ');
  if (sum(A) !== sum(B)) out.push({ cls: 'mod', area: 'Accroche', t: 'Résumé réécrit', a: sum(A), b: sum(B) });
  const ord = (d) => d.experiences.map((b) => b.experience_id).join('|');
  if (ord(A) !== ord(B)) out.push({ cls: 'lay', area: 'Ordre', t: `Expériences : ${B.experiences.map((b) => b.company || b.title).join(' → ')}` });
  const ex = (d) => new Map(E.sectionLines(d, 'experience').map((l) => [l.id, l.text]));
  const ea = ex(A); const eb = ex(B);
  const added = [...eb.keys()].filter((k) => !ea.has(k)).length; const removed = [...ea.keys()].filter((k) => !eb.has(k)).length;
  const modified = [...eb.keys()].filter((k) => ea.has(k) && ea.get(k) !== eb.get(k)).length;
  if (added) out.push({ cls: 'add', area: 'Expériences', t: nb(added, 'puce ajoutée', 'puces ajoutées') });
  if (removed) out.push({ cls: 'del', area: 'Expériences', t: nb(removed, 'puce retirée', 'puces retirées') });
  if (modified) out.push({ cls: 'mod', area: 'Expériences', t: nb(modified, 'puce reformulée', 'puces reformulées') });
  const sk = (d) => new Set(E.sectionLines(d, 'skills').map((l) => E.norm(l.text)));
  const sa = sk(A); const sb = sk(B);
  const skAdd = E.sectionLines(B, 'skills').filter((l) => !sa.has(E.norm(l.text))).map((l) => l.text);
  const skDel = E.sectionLines(A, 'skills').filter((l) => !sb.has(E.norm(l.text))).map((l) => l.text);
  if (skAdd.length) out.push({ cls: 'add', area: 'Compétences', t: `+ ${skAdd.slice(0, 5).join(', ')}` });
  if (skDel.length) out.push({ cls: 'del', area: 'Compétences', t: `− ${skDel.slice(0, 5).join(', ')}` });
  if (DS.familyOf(A.design_profile) !== DS.familyOf(B.design_profile)) out.push({ cls: 'lay', area: 'Design', t: `${DESIGN_NAME(A.design_profile)} → ${DESIGN_NAME(B.design_profile)}` });
  const col = (d) => `${d.palette || ''}${d.colors && d.colors.accent ? `/${d.colors.accent}` : ''}`;
  if (col(A) !== col(B)) out.push({ cls: 'lay', area: 'Couleurs', t: `${paletteLabel(A.palette || 'défaut')} → ${paletteLabel(B.palette || 'défaut')}${B.colors && B.colors.accent ? ` (accent ${B.colors.accent})` : ''}` });
  if ((A.density || 'balanced') !== (B.density || 'balanced')) out.push({ cls: 'lay', area: 'Densité', t: `${DENSITY_LABEL[A.density || 'balanced']} → ${DENSITY_LABEL[B.density || 'balanced']}` });
  if ((A.photo_mode || 'OFF') !== (B.photo_mode || 'OFF')) out.push({ cls: 'lay', area: 'Photo', t: `${PHOTO_LABEL[A.photo_mode || 'OFF']} → ${PHOTO_LABEL[B.photo_mode || 'OFF']}` });
  return out;
}
const DENSITY_LABEL = { airy: 'Aérée', balanced: 'Équilibrée', compact: 'Compacte' };
const PHOTO_LABEL = { OFF: 'sans photo', HEADER: 'photo en en-tête', SIDEBAR: 'photo en colonne', AUTO: 'auto' };
function changesSinceProfile(p, doc) {
  const P = Pp(); if (!P) return [];
  const used = new Set(doc.lines.flatMap((l) => l.fact_ids || []));
  const usable = P.usableFacts().filter((f) => !['identity', 'contact', 'preference', 'media'].includes(f.kind));
  const out = [{ cls: 'add', area: 'Sélection', t: `${usable.filter((f) => used.has(f.id)).length} faits retenus sur ${usable.length} utilisables, choisis pour cette offre` }];
  if ((doc.removed_lines || []).length) out.push({ cls: 'del', area: 'Vérité', t: `${nb(doc.removed_lines.length, 'ligne retirée : non prouvée', 'lignes retirées : non prouvées')} ou manque de place` });
  out.push({ cls: 'lay', area: 'Design', t: `${DESIGN_NAME(doc.design_profile)} · ${paletteLabel(doc.palette || 'petrol')} · ${DENSITY_LABEL[doc.density || 'balanced']} · ${PHOTO_LABEL[doc.photo_mode || 'OFF']}` });
  return out;
}
const changeList = (items) => (items.length ? `<ul class="why-list changes">${items.map((c) => `<li class="${c.cls}"><span><b>${esc(c.area)}</b> · ${esc(c.t)}</span></li>`).join('')}</ul>` : '<p class="muted small" style="margin:0">Aucune différence de contenu ni de présentation.</p>');

// ── Vue « preuves » : le texte du document, chaque ligne survolable (faits qui la prouvent) ──
function sheetHTML(cv, opts = {}) {
  const pal = DS.palette(cv.palette || (D.designs[DS.familyOf(cv.design_profile)] || {}).palette_default || 'petrol', cv.colors && cv.colors.accent);
  const rej = new Set(opts.rejected || []);
  const L = (l, tag = 'span') => `<${tag} data-line="${esc(l.id)}" class="${rej.has(l.id) ? 'rej' : ''}">${esc(l.text)}</${tag}>`;
  const vars = `--cv-accent:${pal.accent};--cv-accent2:${pal.gold};--cv-ink:#16191C;--cv-muted:#5D656B;--cv-rule:#D9DCDF;--cv-band:${pal.tint}`;
  const head = `<div class="band"><div class="nm">${esc(cv.name)}</div>${E.sectionLines(cv, 'headline').map((l) => `<div class="hl">${L(l)}</div>`).join('')}
    <div class="ct">${cv.contact.map(esc).join(' · ')}</div>${E.sectionLines(cv, 'extras').map((l) => `<div class="xt">${L(l)}</div>`).join('')}</div>`;
  const sec = (key, inner) => (inner ? `<div class="sec"><h4>${esc(cv.section_titles[key] || key)}</h4>${inner}</div>` : '');
  const summary = E.sectionLines(cv, 'summary').map((l) => L(l)).join(' ');
  const exps = cv.experiences.map((b) => `<div class="ex"><div class="eh"><span class="et">${esc(b.title)}</span><span class="ep">${esc(b.period)}</span></div>
    <div class="em"><b>${esc(b.company)}</b>${b.city ? ` · ${esc(b.city)}` : ''}</div><ul>${b.bullet_ids.map((id) => E.lineById(cv, id)).filter(Boolean).map((l) => L(l, 'li')).join('')}</ul></div>`).join('');
  const groups = {}; E.sectionLines(cv, 'skills').forEach((l) => (groups[l.group || ''] = groups[l.group || ''] || []).push(l));
  const skills = Object.entries(groups).map(([g, ls]) => `<div class="kr"><b>${esc(g)}</b><span>${ls.map((l) => L(l)).join(', ')}</span></div>`).join('');
  const simple = (k) => E.sectionLines(cv, k).map((l) => `<div>${L(l)}</div>`).join('');
  const body = sec('summary', summary ? `<p style="margin:0">${summary}</p>` : '') + sec('experience', exps) + sec('skills', skills) + sec('education', simple('education')) + sec('certifications', simple('certifications')) + sec('languages', simple('languages'));
  return `<div class="sheet-wrap"><div class="sheet" style="${vars}">${cv.draft ? `<div class="stamp">${cv.language === 'en' ? 'DRAFT — PROFILE NOT VALIDATED' : 'BROUILLON — PROFIL NON VALIDÉ'}</div>` : ''}${head}<div class="body">${body}</div></div></div>`;
}
function letterSheetHTML(letter, name, contact, opts = {}) {
  const rej = new Set(opts.rejected || []);
  const paras = letter.paragraph_order.map((r) => letter.lines.filter((l) => l.section === r)).filter((ls) => ls.length)
    .map((ls) => `<p>${ls.map((l) => `<span data-line="${esc(l.id)}" class="${rej.has(l.id) ? 'rej' : ''}${l.kind === 'offer_ref' ? ' ref' : ''}">${esc(l.text)}</span>`).join(' ')}</p>`).join('');
  return `<div class="sheet-wrap"><div class="sheet">${letter.draft ? `<div class="stamp">${letter.language === 'en' ? 'DRAFT — PROFILE NOT VALIDATED' : 'BROUILLON — PROFIL NON VALIDÉ'}</div>` : ''}
    <div class="lt"><div style="font-size:19px;font-weight:600">${esc(name)}</div><div style="font-size:11.5px;color:#55606B;margin-top:2px">${contact.map(esc).join(' · ')}</div>
    <div style="width:62px;height:2px;background:#1D6E82;margin:18px 0 22px"></div>
    <div style="display:flex;justify-content:space-between;gap:12px;font-size:12.6px;margin-bottom:22px"><span>${esc(letter.recipient)}</span><span style="color:#55606B">${esc(letter.place_date)}</span></div>
    <p style="font-weight:600">${esc(letter.subject)}</p>${letter.salutation ? `<p>${esc(letter.salutation)}</p>` : ''}${paras}<p style="font-weight:600;margin-top:18px">${esc(letter.signature)}</p></div></div></div>`;
}
function fitSheets() {
  $$('.sheet-wrap').forEach((w) => { const s = $('.sheet', w); if (!s) return; const scale = w.clientWidth / 794; s.style.transform = `scale(${scale})`; });
}

// ── Miniature de design (maquette CSS, instantanée) ──
function designMini(fam, palName) {
  const p = DS.palette(palName || (D.designs[fam] || {}).palette_default || 'petrol');
  const L = (x, y, w, h, c, r) => `<i style="left:${x}%;top:${y}%;width:${w}%;height:${h}%;background:${c};${r ? `border-radius:${r}` : ''}"></i>`;
  const lines = (x, y0, w, n, step, c) => Array.from({ length: n }, (_, i) => L(x, y0 + i * step, w * (i % 3 === 2 ? 0.7 : 1), 1.6, c || '#C9CED2')).join('');
  const body = {
    premium_corporate: L(0, 0, 100, 17, p.deep) + L(0, 17, 100, 1.2, p.gold) + L(8, 5, 46, 3.4, p.onDeep) + L(8, 10, 30, 2, p.goldLight) + L(76, 3.5, 13, 10, p.onDeepMuted, '50%') + L(8, 23, 22, 2.2, p.deep) + L(8, 26, 8, 0.9, p.gold) + lines(8, 30, 84, 6, 3.4) + L(8, 52, 22, 2.2, p.deep) + lines(8, 57, 84, 7, 3.4),
    modern_commercial: L(0, 0, 3, 100, p.accent) + L(3, 0, 0.8, 100, p.gold) + L(10, 5, 50, 3.8, '#16191C') + L(10, 11, 34, 2.2, p.accent) + L(10, 18, 24, 7, p.soft) + L(37, 18, 24, 7, p.soft) + L(64, 18, 24, 7, p.soft) + lines(10, 30, 52, 11, 3.4) + L(68, 30, 24, 56, p.tint) + lines(71, 34, 18, 9, 4.2),
    minimal_executive: L(12, 7, 50, 4, '#16191C') + L(12, 13, 34, 2, p.gold) + L(12, 20, 76, 0.4, '#D9DCDF') + L(12, 25, 12, 1.4, '#9AA2A7') + lines(30, 25, 58, 5, 3.4) + L(12, 45, 12, 1.4, '#9AA2A7') + lines(30, 45, 58, 8, 3.4),
    digital_creative: L(0, 0, 32, 100, p.deep) + L(32, 0, 0.8, 100, p.gold) + L(8, 5, 16, 11.5, p.onDeepMuted, '50%') + L(6, 20, 21, 2.6, p.onDeep) + L(6, 25, 16, 1.6, p.goldLight) + lines(6, 32, 20, 8, 3.6, p.tag) + L(38, 6, 8, 1.8, p.accent) + lines(38, 11, 54, 9, 3.6) + L(38, 46, 8, 1.8, p.accent) + lines(38, 51, 54, 8, 3.6),
    ats_hybrid: L(8, 5, 44, 3.6, '#16191C') + L(8, 11, 32, 2.2, p.accent) + L(8, 17, 84, 0.7, p.accent) + L(8, 21, 20, 1.6, p.accent) + lines(8, 25, 84, 6, 3.4) + L(8, 47, 20, 1.6, p.accent) + lines(8, 51, 84, 9, 3.4),
  }[fam] || '';
  return `<span class="mini" aria-hidden="true">${body}</span>`;
}
const DESIGN_SHORT = { premium_corporate: 'Premium', modern_commercial: 'Modern', minimal_executive: 'Minimal', digital_creative: 'Digital', ats_hybrid: 'ATS' };
function designPicker(current, palName, act = 'set-design', opts = {}) {
  return `<div class="design-pick" role="group" aria-label="Design du CV">${DS.FAMILIES.map((f) => `<button data-act="${act}" data-arg="${f}" aria-pressed="${DS.familyOf(current) === f}" title="${esc((D.designs[f] || {}).pitch || '')}">
    ${designMini(f, (D.designs[f] || {}).palettes && (D.designs[f].palettes || []).includes(palName) ? palName : (D.designs[f] || {}).palette_default)}<span>${esc(DESIGN_SHORT[f] || DESIGN_NAME(f))}</span>${opts.auto === f ? '<em class="auto-tag">auto</em>' : ''}</button>`).join('')}</div>`;
}
function whyDesign(auto) {
  if (!auto || !auto.why) return '';
  return `<details class="more why-design"><summary>${icon('i-wand')} Pourquoi ce design ?</summary><ul class="why-list">${auto.why.map((w) => `<li><span><b>${esc(w.k)}</b> · ${esc(w.t)}</span></li>`).join('')}</ul></details>`;
}

// ── Fiche entreprise (uniquement l'annonce ; logo jamais utilisé sans vérification) ──
function companyCardHtml(c, opts = {}) {
  if (!c) return '';
  const name = c.name || 'Entreprise non nommée';
  const mono = (name.match(/[A-Za-zÀ-ÿ0-9]/g) || ['?']).slice(0, 2).join('').toUpperCase();
  return `<div class="company">${`<span class="monogram" aria-hidden="true">${esc(mono)}</span>`}<div class="stack tight">
    <div class="row between"><b style="font-size:16px">${esc(name)}</b>${chip('Source : l\'annonce', 'accent')}</div>
    <span class="muted small">${esc([c.sector, disp(c.location, 'location'), disp(c.contract, 'contract')].filter(Boolean).join(' · '))}</span>
    ${c.about && c.about.length ? `<p class="small" style="margin:4px 0 0">${esc(c.about[0])}.</p>` : ''}
    ${c.figures && c.figures.length ? `<div class="row" style="gap:6px;margin-top:4px">${c.figures.map((f) => chip(f, 'gold')).join('')}</div>` : ''}
    ${opts.full && c.wants && c.wants.length ? `<div class="small" style="margin-top:6px"><b>Ce qu'ils cherchent</b><ul class="why-list" style="margin-top:6px">${c.wants.map((w) => `<li><span>${esc(typeof w === 'string' ? w : w.text || w.requirement || '')}</span></li>`).join('')}</ul></div>` : ''}
    <span class="hint">Logo : ${c.logo && c.logo.used ? 'vérifié' : 'non vérifié → non utilisé'}${c.website ? ` · <a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer">site cité</a>` : ''}</span></div></div>`;
}
function whyCompany(p) {
  const L = p.letters[p.letter_index]; if (!L) return [];
  return L.doc.lines.filter((l) => l.section === 'WHY_COMPANY' && l.kind !== 'offer_ref').map((l) => l.text);
}

// ── Pipeline (liste des étapes) ──
const stageSig = (s) => E.hash([s.state, s.detail, s.note, s.ms]);
function stageLi(s, i, mode) {
  const st = STAGES.find((x) => x[0] === s.key);
  return `<li class="stage ${s.state}" data-k="${s.key}" data-sig="${stageSig(s)}"><span class="node">${s.state === 'done' ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>' : s.state === 'fail' ? '!' : String(i + 1).padStart(2, '0')}</span>
    <div class="body"><div class="name"><b>${esc(st[1])}</b><span>${esc(s.state === 'skip' ? `${st[2]} · non inclus en mode ${MODE_INFO[mode][0]}` : s.detail || st[2])}</span>${s.ms ? `<em class="ms">${fmtMs(s.ms)}</em>` : ''}</div>
    ${s.note ? `<div class="note">${icon('i-info')} ${esc(s.note)}</div>` : ''}</div></li>`;
}
function stageList(run) {
  const mode = run ? run.mode : S.draft.mode;
  const steps = run ? run.steps : STAGES.map(([k]) => ({ key: k, state: MODE_SKIP[mode].includes(k) ? 'skip' : 'todo', detail: '' }));
  return `<ol class="pipeline"${run ? ' data-run="1"' : ''}>${steps.map((s, i) => stageLi(s, i, mode)).join('')}</ol>`;
}

// ── Avis (👍 😐 👎 + raisons) ──
function feedbackBox(p, doc, idx, opts = {}) {
  const mine = S.feedback.filter((f) => f.pack_id === p.id && f.doc === doc);
  return `<div class="card stack" id="fb-box">
    <div class="card-head"><h3 class="h3">${esc(opts.title || 'Ton avis')}</h3>${mine.length ? chip(`${mine.length} avis`, '') : ''}</div>
    <div class="rate" role="group" aria-label="Note">${RATE.map(([v, e, l]) => `<button data-act="fb-rate" data-arg="${v}" aria-pressed="${S.fbRate === v}" aria-label="${l}" title="${l}">${e}</button>`).join('')}</div>
    <div class="reasons" role="group" aria-label="Raisons">${REASONS.map((r) => `<button data-act="fb-reason" data-arg="${esc(r)}" aria-pressed="${S.fbReasons.includes(r)}">${esc(r)}</button>`).join('')}</div>
    <textarea id="fb-comment" class="textarea" style="min-height:64px" data-bind="fbComment" placeholder="Ce qui marche, ce qui ne marche pas… (facultatif)">${esc(S.fbComment || '')}</textarea>
    <div class="row"><button class="btn sm primary" data-act="fb-save" data-arg="${doc}:${idx}">${icon('i-check')} Enregistrer l'avis</button>${opts.regen ? `<button class="btn sm" data-act="lab-v2" data-arg="${esc(p.id)}">${icon('i-refresh')} Générer V2 avec cet avis</button>` : ''}</div>
    ${mine.slice(0, 3).map((f) => `<div class="muted small">${rateIcon(f.rating)} ${esc((f.reasons || [f.element]).join(', '))}${f.comment ? ` · ${esc(f.comment)}` : ''}</div>`).join('')}</div>`;
}

// ── Prochaine meilleure action ──
function nextAction() {
  const p = S.profile;
  if (!p) return { t: 'Importe ton Master Profile pour commencer : PAI ne peut rien écrire sans tes faits.', act: 'go', arg: 'onboarding', cta: 'Configurer PAI' };
  if (conflicts(p).length) return { t: `Tranche ${nb(conflicts(p).length, 'conflit', 'conflits')} dans ton profil : PAI ne choisit jamais à ta place.`, act: 'go', arg: 'profil', cta: 'Résoudre' };
  if (!p.validated) return { t: 'Valide ton profil : tes documents passeront de BROUILLON à FINAL.', act: 'go', arg: 'onboarding', cta: 'Valider' };
  if (!S.packs.length) return { t: 'Colle ta première vraie offre ci-dessus : PAI prépare CV, lettre et réponses en quelques minutes.', act: 'focus-cmd', arg: '', cta: 'Coller une offre' };
  const last = S.packs[0];
  if (last && last.cvs && last.cvs.length && !S.feedback.some((f) => f.pack_id === last.id)) return { t: `Donne ton avis sur le CV « ${last.analysis.job_title} » : c'est ce qui fait progresser PAI.`, act: 'open-lab', arg: last.id, cta: 'Donner mon avis' };
  if (last && last.status === 'DRAFT' && last.cvs && last.cvs.length) return { t: `Le pack « ${last.analysis.job_title} » est en brouillon : ${last.next_action}`, act: 'open-pack', arg: last.id, cta: 'Ouvrir' };
  return { t: 'Analyse une nouvelle offre, ou relis ton dernier pack avant de postuler.', act: 'focus-cmd', arg: '', cta: 'Nouvelle offre' };
}

function packCover(p, i = 0) {
  const a = p.analysis || {}; const e = p.cvs && p.cvs.length ? p.cvs[p.cv_index] : null;
  return `<button class="cover" data-act="open-pack" data-arg="${esc(p.id)}" data-anim="${Math.min(5, i + 1)}">
    ${e ? cvPaper(e.doc, { width: 380, label: `CV ${a.job_title}` }) : `<div class="paper empty-paper">${icon('i-spark')}<em>Analyse seule</em></div>`}
    <span class="stack tight"><span class="t">${esc(a.job_title || '—')}</span><span class="s">${esc(disp(a.company, 'company'))} · ${fmtDate(p.created_at)}</span>
    <span class="row" style="gap:6px">${packChip(p.status)}${p.offer && p.offer.synthetic ? '<span class="tag-ds synthetic">SYNTHETIC</span>' : ''}</span></span></button>`;
}
function packRow(p) {
  const a = p.analysis || {};
  return `<button class="item" data-act="open-pack" data-arg="${esc(p.id)}"><span class="grow"><span class="t">${esc(a.job_title || '—')} · ${esc(disp(a.company, 'company'))}</span>
    <span class="s">${fmtDate(p.created_at)} · ${esc(MODE_INFO[p.mode] ? MODE_INFO[p.mode][0] : p.mode)} · Score PAI ${p.ats && p.ats.score && p.ats.score.value !== null ? `${p.ats.score.value}\u00a0%` : '—'}${p.offer && p.offer.synthetic ? ' · SYNTHETIC' : ''}</span></span>${packChip(p.status)}</button>`;
}
function emptyState(ic, title, text, cta) {
  return `<div class="card empty">${icon(ic)}<b style="color:var(--ink)">${esc(title)}</b><span>${esc(text)}</span>${cta ? `<button class="btn primary" data-act="${cta[0]}" data-arg="${esc(cta[1] || '')}">${esc(cta[2])}</button>` : ''}</div>`;
}
