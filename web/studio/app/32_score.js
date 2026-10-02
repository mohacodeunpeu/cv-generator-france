// ─── Score PAI : pourcentages d'abord, critères à la demande ─────────────────
// Le calcul vient du moteur ATS (web/studio/ats.js, parité avec pai/ats) : aucun chiffre n'est inventé ici.
const ATS = E.ATS;
const ATS_STATE = { OK: ['OK', 'good'], WARNING: ['Attention', 'warn'], ERROR: ['Problème', 'bad'] };
const PROOF_UI = { 'PROUVÉ': ['Prouvé', 'good'], PLAUSIBLE: ['Correspondance possible', 'warn'], 'NON_PROUVÉ': ['Non prouvé', 'bad'] };
const CLASS_UI = { MUST: 'Obligatoire', IMPORTANT: 'Important', NICE_TO_HAVE: 'Un plus', CONTEXT: 'Contexte' };
const KIND_UI = { fait: ['Fait', ''], interpretation: ['Interprétation', 'accent'], suggestion: ['Suggestion', 'gold'] };
const stateChip = (st) => chip((ATS_STATE[st] || [st])[0], (ATS_STATE[st] || [])[1] || '');
const dimTone = (v) => (v === null || v === undefined ? '' : tone(v, 80, 60));

// Texte d'un fait (jamais son identifiant interne) : « Prospection B2B et cycle commercial complet ».
const factText = (id) => { const P = Pp(); const f = P && P.fact(id); const t = f ? String(f.text || '') : ''; return t.length > 90 ? `${t.slice(0, 88).trimEnd()}…` : t; };
const proofLine = (ids) => { const t = (ids || []).map(factText).filter(Boolean); return t.length ? `Preuve : « ${t[0]} »${t.length > 1 ? ` + ${nb(t.length - 1, 'autre fait', 'autres faits')}` : ''}` : ''; };

// Rapport ATS d'un pack (ou d'une version de CV) : recalculé à la demande, mis en cache par empreinte.
const ATS_CACHE = new Map();
function atsFor(p, entry, doc) {
  const P = Pp(); if (!P || !p || !p.analysis) return p && p.ats ? p.ats : null;
  const d = doc || (entry ? entry.doc : null);
  const key = E.hash([p.id, profileTag(S.profile), d ? d.lines : null, d ? d.experiences : null, d ? d.contact : null, entry && entry.report ? entry.report.factuality : null, entry && entry.scan ? entry.scan.score : null]);
  if (ATS_CACHE.has(key)) return ATS_CACHE.get(key);
  let r;
  try {
    r = ATS.matchReport(P, p.analysis, p.match, (p.offer && p.offer.text) || '', d ? { cv: d, validation: entry && entry.report && entry.report.total ? entry.report : null, scan: entry && entry.scan ? entry.scan : null } : {});
  } catch (e) { console.warn('score PAI', e); return p.ats || null; }
  if (ATS_CACHE.size > 40) ATS_CACHE.delete(ATS_CACHE.keys().next().value);
  ATS_CACHE.set(key, r);
  return r;
}

// Grand chiffre + les six dimensions principales ; « Voir les détails » ouvre les critères internes.
function scorePanel(r, opts = {}) {
  if (!r) return '';
  const sc = r.score; const main = r.dimensions.filter((d) => r.main.includes(d.id)); const extra = r.dimensions.filter((d) => !r.main.includes(d.id));
  const open = S.atsOpen || null; const id = opts.id || 'ps';
  const t = dimTone(sc.value);
  const tile = (d) => `<button class="ps-dim ${d.available ? dimTone(d.value) : 'na'}" data-act="ats-dim" data-arg="${d.id}" aria-expanded="${open === d.id || open === 'all'}" title="${esc(d.help)}">
      <span class="k">${esc(d.label)}</span><span class="v">${d.available ? `${d.value}<small> %</small>` : '—'}</span>
      ${d.available ? bar(d.value, dimTone(d.value)) : '<div class="bar"><i style="width:0"></i></div>'}<span class="s">${esc(d.available ? d.summary : `Non mesuré : ${d.summary}`)}</span></button>`;
  const status = sc.complete ? '' : `<span class="chip warn">Provisoire</span>`;
  const detailDims = open === 'all' ? r.dimensions : r.dimensions.filter((d) => d.id === open);
  return `<section class="ps${opts.compact ? ' compact' : ''}" id="${id}" aria-label="Score PAI">
    <div class="ps-hero">
      ${ring(sc.value, t, { size: opts.compact ? 'lg pct' : 'xl pct', label: 'Score PAI' })}
      <div class="stack tight"><span class="kicker">Score PAI ${status}</span>
        <p class="ps-lede">${sc.value === null ? 'Pas encore mesurable.' : `${esc(scoreSentence(r))}`}</p>
        <span class="hint">${esc(sc.disclaimer)}</span></div></div>
    <div class="ps-dims">${main.map(tile).join('')}</div>
    <div class="row between ps-foot">${extra.length ? `<span class="hint">${extra.map((d) => `${esc(d.label)} ${d.available ? `${d.value} %` : '—'}`).join(' · ')}</span>` : '<span></span>'}
      <button class="linkish ps-more" data-act="ats-dim" data-arg="all" aria-expanded="${open === 'all'}">${open === 'all' ? 'Masquer les détails' : 'Voir les détails →'}</button></div>
    ${detailDims.length ? `<div class="ps-detail">${detailDims.map(dimDetail).join('')}<p class="hint" style="margin:0">Calcul : ${esc(sc.formula)}.</p></div>` : ''}
  </section>`;
}
function scoreSentence(r) {
  const req = r.requirements; const must = [].concat(req.proven, req.plausible, req.unproven).filter((x) => x.class === 'MUST');
  const mustOk = must.filter((x) => x.proof.status === 'PROUVÉ').length;
  const parts = [];
  if (must.length) parts.push(`${mustOk}/${must.length} exigences obligatoires prouvées`);
  parts.push(`${nb(req.proven.length, 'exigence prouvée', 'exigences prouvées')} au total`);
  if (!r.score.complete) parts.push(`${r.score.missing.join(', ')} : mesuré après le PDF`);
  return `${parts.join(' · ')}.`;
}
function dimDetail(d) {
  return `<div class="ps-d"><div class="row between"><b>${esc(d.label)}</b><span class="v ${d.available ? dimTone(d.value) : ''}">${d.available ? `${d.value} %` : 'non mesuré'}</span></div>
    <p class="hint" style="margin:2px 0 8px">${esc(d.help)}</p>
    ${d.details.length ? `<ul class="crit">${d.details.map((c) => `<li>${stateChip(c.status)}<span class="grow"><span class="t">${esc(c.label)}</span>${c.detail ? `<span class="s">${esc(c.detail)}</span>` : ''}</span>${c.value !== undefined ? `<span class="n">${c.value} %</span>` : ''}</li>`).join('')}</ul>` : `<p class="muted small" style="margin:0">${esc(d.summary)}</p>`}</div>`;
}

// Points forts / à améliorer, chaque phrase typée : fait, interprétation, suggestion.
function strengthsPanel(r) {
  const li = (x) => `<li><span>${chip(KIND_UI[x.kind] ? KIND_UI[x.kind][0] : x.kind, KIND_UI[x.kind] ? KIND_UI[x.kind][1] : '')} ${esc(x.text)}${x.note ? `<span class="s">${esc(x.note)}</span>` : ''}</span></li>`;
  return `<div class="grid g2 sg">
    <section class="card"><h3 class="h3">Points forts</h3>${r.strengths.length ? `<ul class="why-list">${r.strengths.map(li).join('')}</ul>` : '<p class="muted small">Aucun point fort prouvé pour cette offre.</p>'}</section>
    <section class="card"><h3 class="h3">À améliorer</h3>${r.improvements.length ? `<ul class="why-list">${r.improvements.map(li).join('')}</ul>` : '<p class="muted small">Rien de bloquant.</p>'}</section></div>`;
}

// Exigences : Prouvé / Correspondance possible / Non prouvé (+ contexte, jamais compté).
function requirementsPanel(r) {
  const col = (key, title, t, empty) => {
    const items = r.requirements[key];
    return `<section class="req-col ${t}"><h3 class="h3"><span class="dot"></span>${title} <span class="count">${items.length}</span></h3>${items.length ? `<ul>${items.map((x) => `<li>
      <span class="t">${esc(x.text)}</span><span class="row" style="gap:6px">${chip(CLASS_UI[x.class] || x.class, x.class === 'MUST' ? 'accent' : '')}${x.proof.match && key !== 'unproven' ? `<span class="m">${esc(({ EXACT: 'exact', SYNONYME: 'synonyme', 'SÉMANTIQUE': 'proche' })[x.proof.match] || '')}</span>` : ''}</span>
      ${x.proof.via ? `<span class="s">${esc(x.proof.via)}</span>` : ''}${x.proof.fact_ids && x.proof.fact_ids.length ? `<span class="s proof">${esc(proofLine(x.proof.fact_ids))}</span>` : ''}${x.proof.note ? `<span class="s note">${esc(x.proof.note)}</span>` : ''}</li>`).join('')}</ul>` : `<p class="muted small" style="margin:8px 0 0">${empty}</p>`}</section>`;
  };
  return `<div class="req-cols">${col('proven', 'Prouvé', 'good', 'Aucune exigence prouvée.')}${col('plausible', 'Correspondance possible', 'warn', 'Aucune.')}${col('unproven', 'Non prouvé', 'bad', 'Tout est couvert.')}</div>
    ${r.requirements.context.length ? `<details class="more"><summary>Contexte du poste (${r.requirements.context.length}, jamais compté comme exigence)</summary><ul class="why-list">${r.requirements.context.map((x) => `<li><span>${esc(x.text)}</span></li>`).join('')}</ul></details>` : ''}
    <p class="hint" style="margin:10px 0 0">Une correspondance possible ou une exigence non prouvée n'est jamais écrite dans le CV pour monter le score : elle se prépare pour l'entretien.</p>`;
}

// Mots-clés : statut, présence dans le CV, et pourquoi (présent / pas ajouté).
function keywordsPanel(r) {
  if (!r.keywords.length) return '<p class="muted small">Aucun mot-clé extrait.</p>';
  return `<div class="kw-list">${r.keywords.map((k) => { const [l, t] = PROOF_UI[k.status] || [k.status, '']; return `<span class="kw ${t}" title="${esc(k.why)}">${k.in_cv ? icon('i-check') : ''}${esc(ATS.displayTerm(k.term))}<small>${esc(l)}</small></span>`; }).join('')}</div>
    <details class="more"><summary>Pourquoi chaque mot-clé est présent ou absent</summary><ul class="why-list">${r.keywords.map((k) => `<li><span><b>${esc(ATS.displayTerm(k.term))}</b> · ${esc(k.why)}${k.fact_ids && k.fact_ids.length ? ` <span class="muted">${esc(proofLine(k.fact_ids))}</span>` : ''}</span></li>`).join('')}</ul></details>`;
}

// Changements : AVANT / APRÈS / RAISON / PREUVE (CV original importé, sinon faits du profil).
function originalCvText() { const d = (S.documents || []).find((x) => x.kind !== 'letter' && x.text); return d ? d.text : ''; }
function changesTable(doc) {
  const P = Pp(); if (!P) return '';
  const orig = originalCvText(); const ch = ATS.changes(doc, P, orig);
  if (!ch.changes.length) return `<p class="muted small" style="margin:0">Aucune ligne modifiée par rapport ${orig ? 'au CV original' : 'aux faits du profil'}.</p>`;
  const beforeLabel = orig ? 'CV original' : 'Fait du profil';
  return `<p class="hint" style="margin:0 0 12px">Avant : ${orig ? 'ton CV original (Documents)' : 'le fait du profil, tel qu\'il est écrit'} · ${nb(ch.unchanged, 'ligne reprise telle quelle', 'lignes reprises telles quelles')}.</p>
    <ol class="chg-list">${ch.changes.map((c) => {
      const proofs = c.proof.map((f) => f.text).filter((t) => E.norm(t) !== E.norm(c.before));
      return `<li><span class="kicker quiet">${esc(c.section)}</span>
        <div class="ba"><p class="before" title="${esc(beforeLabel)}">${c.before ? esc(c.before) : '<span class="faint">— (nouvelle ligne)</span>'}</p><span class="arrow" aria-hidden="true">→</span><p class="after">${esc(c.after)}</p></div>
        <div class="meta"><span><b>Raison</b>${esc(c.reason)}</span>${proofs.length ? `<span><b>Preuve</b>« ${esc(proofs.slice(0, 2).join(' » · « '))} »</span>` : c.proof.length ? '' : '<span><b>Preuve</b>titre du poste visé (rôle déclaré dans le profil)</span>'}</div></li>`;
    }).join('')}</ol>${ch.dropped.length ? `<p class="hint" style="margin:12px 0 0">Non reprises ici (restent dans le CV maître) : ${esc(ch.dropped.map((x) => `${x.experience} (${x.count})`).join(', '))}.</p>` : ''}`;
}

// ── Relecture du PDF par un « ATS » : le serveur PAI (scanner complet), sinon le navigateur (pdf.js) ──
const ATS_LABELS = ['Contact', 'E-mail', 'Email', 'Téléphone', 'Ville', 'Site', 'Web', 'Phone', 'Location', 'BROUILLON — PROFIL NON VALIDÉ', 'DRAFT — PROFILE NOT VALIDATED'];
const cvLabels = (doc) => [doc.name, ...(doc.contact || []), ...Object.values(doc.section_titles || {}), ...new Set(doc.lines.map((l) => l.group).filter(Boolean)),
  ...doc.experiences.flatMap((b) => [b.title, b.company, b.city, b.period]), ...ATS_LABELS].filter(Boolean);
const toB64 = (bytes) => { let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)); return btoa(bin); };
async function scanCv(doc, bytes, info, qa, maxPages) {
  if (SERVER) {
    try {
      const r = await Srv.req('POST', '/api/cv/validate', { cv_file_b64: toB64(bytes), cv_filename: 'cv.pdf', max_pages: String(maxPages),
        source_text: doc.lines.map((l) => l.text).join('\n'), allowed_text: cvLabels(doc).join('\n') });
      const rep = r.report;
      return { score: rep.score, status: rep.status, checks: rep.checks.map((c) => ({ id: c.id, label: c.label, status: c.status, detail: c.detail })), source: 'serveur' };
    } catch (e) { console.warn('relecture serveur indisponible : relecture dans le navigateur', e); }
  }
  return browserScan(doc, info, qa, maxPages);
}
function browserScan(doc, info, qa, maxPages) {
  const text = info.text || ''; const checks = [];
  const add = (id, label, status, detail) => checks.push({ id, label, status, detail });
  const chars = text.trim().length;
  add('text', 'Texte extractible', chars >= 300 ? 'OK' : 'ERROR', chars >= 300 ? `${chars.toLocaleString('fr-FR')} caractères lus` : 'Peu ou pas de texte lisible : un ATS ne lira rien.');
  const bad = (text.match(/�/g) || []).length;
  add('encoding', 'Encodage des caractères', bad ? 'ERROR' : 'OK', bad ? nb(bad, 'caractère illisible', 'caractères illisibles') : 'Caractères correctement encodés');
  const odd = (text.match(/[-ﬀ-ﬆ]|\p{Extended_Pictographic}/gu) || []).length;
  add('characters', 'Caractères spéciaux', odd ? 'WARNING' : 'OK', odd ? nb(odd, 'caractère à risque', 'caractères à risque') : 'Aucun caractère à risque');
  add('pages', 'Pagination', qa.pages <= maxPages ? 'OK' : qa.pages === maxPages + 1 ? 'WARNING' : 'ERROR', `${nb(qa.pages, 'page', 'pages')} (maximum conseillé : ${maxPages})`);
  add('overflow', 'Débordement', info.overflow ? 'ERROR' : 'OK', info.overflow ? `${nb(info.overflow, 'segment', 'segments')} hors de la page` : 'Tout le texte tient dans la page');
  const two = (D.designs[DS.familyOf(doc.design_profile)] || {}).layout === 'two_column';
  add('columns', 'Colonnes', two ? 'WARNING' : 'OK', two ? "Deux colonnes : certains ATS mélangent l'ordre de lecture" : 'Une seule colonne de lecture');
  const disorder = (qa.issues || []).some((i) => i.check === 'ordre_lecture');
  add('reading', 'Ordre de lecture', disorder ? 'ERROR' : 'OK', disorder ? 'Ordre de lecture incohérent' : 'Nom, expérience puis formation, dans l\'ordre');
  add('fonts', 'Polices', qa.min_font_pt && qa.min_font_pt < 7.5 ? 'WARNING' : 'OK', `Taille minimale ${num(qa.min_font_pt)} pt`);
  const mail = /[\w.+-]+@[\w-]+\.[\w.-]+/.test(text); const phone = /(?:(?:\+|00)\d{2,3}[\s.-]?(?:\(0\)[\s.-]?)?\d|\b0\d)(?:[\s.-]?\d{2}){4}/.test(text);
  add('contact', 'Coordonnées', mail && phone ? 'OK' : !mail ? 'ERROR' : 'WARNING', mail && phone ? 'E-mail et téléphone lus' : !mail ? 'E-mail introuvable' : 'Téléphone introuvable');
  const tn = E.norm(text.replace(/-\n(?=[a-zà-ÿ])/g, ''));
  const missing = ['experience', 'education', 'skills'].map((k) => (doc.section_titles || {})[k]).filter(Boolean).filter((t) => !tn.includes(E.norm(t)));
  add('sections', 'Sections reconnues', missing.length ? 'ERROR' : 'OK', missing.length ? `Introuvables : ${missing.join(', ')}` : 'Expérience, formation et compétences lues');
  const toks = (s) => s.match(/[a-z0-9][a-z0-9'+#.-]*/g) || [];
  const flat = new Set(toks(tn));
  const lost = doc.lines.filter((l) => { const n = E.norm(l.text); if (!n || tn.includes(n)) return false; const t = toks(n); return t.length && t.filter((x) => flat.has(x)).length / t.length < 0.9; });
  add('lost', 'Rien de perdu', lost.length ? 'ERROR' : 'OK', lost.length ? `${nb(lost.length, 'ligne du CV introuvable', 'lignes du CV introuvables')} dans le PDF` : 'Toutes les lignes du CV sont relues dans le PDF');
  const source = E.norm(doc.lines.map((l) => l.text).concat(cvLabels(doc)).join(' '));
  const ph = [...new Set((tn.match(/\b(undefined|null|nan|none|lorem ipsum|\[object object\]|todo|xxx)\b|\{\{|\}\}/g) || []).filter((x) => !source.includes(x)))];
  add('added', "Rien d'ajouté", ph.length ? 'ERROR' : 'OK', ph.length ? `Texte de gabarit dans le PDF : ${ph.join(', ')}` : 'Aucun texte sans origine');
  const score = Math.max(0, 100 - checks.reduce((n, c) => n + ({ OK: 0, WARNING: 8, ERROR: 25 })[c.status], 0));
  return { score, status: checks.some((c) => c.status === 'ERROR') ? 'ERROR' : checks.some((c) => c.status === 'WARNING') ? 'WARNING' : 'OK', checks, source: 'navigateur' };
}
// Résumé compact (liste des packs, comparaison) : le chiffre et les six dimensions, sans les détails.
const atsSlim = (r) => (r ? { score: { value: r.score.value, complete: r.score.complete, missing: r.score.missing }, dims: r.dimensions.map((d) => ({ id: d.id, label: d.label, value: d.value })), variant: r.variant && r.variant.id } : null);
