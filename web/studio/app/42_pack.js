// ─── Application Packs, CV Studio, Letter Studio, versions ───────────────────
V.packs = () => {
  const packs = S.packs;
  return `<div class="page"><div class="page-head"><div class="stack"><span class="kicker">Application Packs</span><h1 class="title">Tes <em>candidatures</em></h1>
    <p class="lede">Chaque pack fige l'offre, l'analyse, la stratégie, le CV, la lettre et les réponses, avec toutes leurs versions. PAI ne postule jamais à ta place.</p></div>
    <button class="btn primary" data-act="go" data-arg="accueil">${icon('i-plus')} Nouvelle offre</button></div>
    ${packs.length ? `<div class="covers">${packs.map(packCover).join('')}</div>` : emptyState('i-stack', 'Aucun pack pour l\'instant', 'Colle une vraie offre : le pack (CV, lettre, réponses, versions) apparaîtra ici.', ['go', 'accueil', 'Analyser une offre'])}</div>`;
};

const PACK_TABS = [['overview', 'Aperçu'], ['offer', 'Offre'], ['strategy', 'Stratégie'], ['cv', 'CV'], ['letter', 'Lettre'], ['questions', 'Questions'], ['risks', 'Risques'], ['versions', 'Versions']];
V.pack = () => {
  const p = curPack(); if (!p) return `<div class="page">${emptyState('i-stack', 'Pack introuvable', 'Il a peut-être été supprimé.', ['go', 'packs', 'Voir les packs'])}</div>`;
  const a = p.analysis; const hasDocs = p.cvs.length > 0;
  const tab = hasDocs || ['overview', 'offer', 'strategy', 'risks'].includes(S.packTab) ? S.packTab : 'overview';
  const body = ({ overview: packOverview, offer: packOffer, strategy: packStrategy, cv: (x) => studio(x), letter: letterStudio, questions: packQuestions, risks: packRisks, versions: packVersions })[tab] || packOverview;
  const mono = ((disp(a.company, 'company') || '?').match(/[A-Za-zÀ-ÿ0-9]/g) || ['?']).slice(0, 2).join('').toUpperCase();
  return `<div class="page"><header class="cover-head">
      <span class="monogram" aria-hidden="true">${esc(mono)}</span>
      <div class="stack tight"><button class="linkish back" data-act="go" data-arg="packs">${icon('i-back')} Application Packs</button>
        <h1 class="title">${esc(a.job_title)}</h1>
        <div class="meta-row"><span>${esc(disp(a.company, 'company'))}</span><span class="sep">·</span><span>${esc(disp(a.location, 'location'))}</span><span class="sep">·</span><span>${esc(disp(a.contract, 'contract'))}</span><span class="sep">·</span><span>${esc(E.sector(a.sector_id).name || a.sector_id)}</span>
          ${chip(p.status, p.status === 'FINAL' ? 'good' : 'warn')}${p.offer.synthetic ? '<span class="tag-ds synthetic">SYNTHETIC</span>' : ''}</div></div>
      <div class="row">${hasDocs ? `<button class="btn primary" data-act="dl-zip">${icon('i-download')} Télécharger le pack</button><button class="btn" data-act="dl-cv">CV</button><button class="btn" data-act="dl-letter">Lettre</button>` : `<button class="btn primary" data-act="rerun-standard">${icon('i-spark')} Générer CV et lettre</button>`}
        <button class="btn ghost" data-act="pack-tab" data-arg="offer">${icon('i-eye')} Voir l'offre</button>${p.cvs.length > 1 ? `<button class="btn ghost" data-act="pack-tab" data-arg="versions">${icon('i-compare')} Voir les changements</button>` : ''}</div></header>
    <div class="tabs" role="tablist">${PACK_TABS.map(([k, l]) => `<button role="tab" aria-selected="${tab === k}" data-act="pack-tab" data-arg="${k}" ${!hasDocs && ['cv', 'letter', 'questions', 'versions'].includes(k) ? 'disabled' : ''}>${l}</button>`).join('')}</div>
    <div class="tab-body">${body(p)}</div></div>`;
};

function packOverview(p) {
  const e = p.cvs.length ? p.cvs[p.cv_index] : null; const L = p.letters.length ? p.letters[p.letter_index] : null; const m = p.match;
  const fam = e ? e.doc.design_profile : p.design ? p.design.design : 'ats_hybrid';
  const glance = [['Correspondance', m.match, ''], ['Mots-clés prouvés', m.quality, ''], ['Risque de rejet', m.risk, ''], ['Factualité', e ? p.scores.factuality_cv : null, ' %']];
  return `<div class="overview">
    <div class="stack loose">${e ? `<div class="desk" style="padding:52px 40px 60px"><div class="doc-stack"><div class="front">${cvPaper(e.doc, { width: 680 })}</div>${L ? `<div class="back">${letterPaper(L.doc, e.doc, { width: 560 })}</div>` : ''}</div></div>
      <div class="row"><button class="cta" data-act="pack-tab" data-arg="cv">${icon('i-layout')} Ouvrir dans CV Studio</button><button class="btn lg" data-act="pack-tab" data-arg="letter">Letter Studio</button><button class="btn lg ghost" data-act="open-lab" data-arg="${esc(p.id)}">${icon('i-flask')} Donner mon avis</button></div>`
    : `<div class="desk" style="padding:60px 40px;text-align:center"><div class="stack" style="align-items:center"><h2 class="h2">Analyse seule</h2><p class="lede">L'offre est analysée et la stratégie choisie. Lance la génération complète pour obtenir le CV, la lettre et le contrôle du PDF.</p><button class="cta" data-act="rerun-standard">${icon('i-spark')} Générer CV et lettre</button></div></div>`}</div>
    <div class="stack loose">
      <div class="glance">${glance.map(([l, v, u]) => `<div><div class="v">${v === null || v === undefined ? '—' : `${pct(v)}${u ? `<small>${u}</small>` : ''}`}</div><div class="l">${l}</div></div>`).join('')}</div>
      <div class="nba" style="width:100%">${icon('i-bolt')}<div class="t"><span class="kicker">Prochaine action</span>${esc(p.next_action)}</div></div>
      <section class="card">${companyCardHtml(p.company || E.companyCard(p.analysis, p.offer))}</section>
      ${p.design ? `<section class="card stack"><div class="card-head" style="margin:0"><h3 class="h3">Design</h3>${chip(DESIGN_NAME(fam), 'gold')}</div><div class="design-decision">${designMini(DS.familyOf(fam), e ? e.doc.palette : p.design.palette)}<span class="small muted">${esc((D.designs[DS.familyOf(fam)] || {}).pitch || '')}</span></div>${whyDesign(p.design)}</section>` : ''}
      <section class="card"><dl class="kv"><dt>Créé</dt><dd>${fmtTime(p.created_at)}</dd><dt>Mode</dt><dd>${esc(MODE_INFO[p.mode] ? MODE_INFO[p.mode][0] : p.mode)}</dd><dt>IA</dt><dd>${esc(p.provider)}</dd><dt>Versions du CV</dt><dd>${p.cvs.length}</dd><dt>Source</dt><dd>${esc(({ url: 'lien', pdf: 'PDF', text: 'texte collé' })[p.offer.source_type] || p.offer.source_type)}</dd></dl></section>
    </div></div>`;
}

function packOffer(p) {
  const a = p.analysis; const m = p.match; const o = p.offer;
  const cov = m.coverage.map((c) => `<span class="chip ${c.covered ? 'good' : c.priority === 'REQUIRED' ? 'bad' : 'warn'}" title="${esc(c.covered ? `Prouvé par ${c.fact_ids.join(', ')} (${c.via})` : 'Aucun fait ne le prouve')}">${c.covered ? '✓' : '✗'} ${esc(c.term)} <span class="mono">${esc(c.priority[0])}</span></span>`).join(' ');
  const list = (items, key = 'text') => (items && items.length ? `<ul class="why-list">${items.map((x) => `<li><span>${esc(typeof x === 'string' ? x : x[key] || x.requirement || '')}${x.fact_ids && x.fact_ids.length ? ` ${fids(x.fact_ids)}` : ''}</span></li>`).join('')}</ul>` : '<p class="muted small" style="margin:0">—</p>');
  return `<div class="split"><div class="card stack"><div class="card-head"><h3 class="h3">Texte de l'offre</h3><div class="row">${o.source_url ? `<a class="btn sm" href="${esc(o.source_url)}" target="_blank" rel="noopener noreferrer">${icon('i-link')} Ouvrir l'annonce</a>` : ''}${chip(({ url: 'Lien', pdf: 'PDF', text: 'Texte collé' })[o.source_type] || o.source_type)}</div></div>
      <div class="offer-text">${esc(o.text)}</div><p class="hint" style="margin:0">Empreinte ${esc(o.text_hash)} · lue le ${fmtTime(o.fetched_at)}${o.source_url ? ` · ${esc(hostOf(o.source_url))}` : ''}</p></div>
    <div class="stack"><div class="card"><h3 class="h3">Ce que PAI a compris</h3><dl class="kv" style="margin-top:12px"><dt>Poste</dt><dd>${esc(a.job_title)}</dd><dt>Entreprise</dt><dd>${esc(disp(a.company, 'company'))}</dd><dt>Lieu</dt><dd>${esc(disp(a.location, 'location'))}</dd><dt>Contrat</dt><dd>${esc(disp(a.contract, 'contract'))}</dd><dt>Secteur</dt><dd>${esc(E.sector(a.sector_id).name || a.sector_id)}</dd><dt>Niveau</dt><dd>${esc(a.seniority || '—')}</dd><dt>Langue</dt><dd>${esc(a.language_of_offer || 'fr')}</dd><dt>Analyse</dt><dd>${a.source === 'deterministic' ? 'déterministe (sans IA)' : 'IA + contrôle déterministe'}</dd></dl></div>
      <div class="card"><h3 class="h3">Mots-clés (✓ prouvés par tes faits)</h3><div class="row" style="gap:6px;margin-top:12px">${cov || '<span class="muted">Aucun mot-clé détecté.</span>'}</div></div>
      <div class="card"><h3 class="h3">Ce que le recruteur veut vraiment</h3><div class="grid g2" style="margin-top:12px"><div><b class="small">Explicite</b>${list((a.recruiter_wants || {}).explicit)}</div><div><b class="small">Déduit</b>${list((a.recruiter_wants || {}).inferred)}</div></div></div></div></div>`;
}

function packStrategy(p) {
  const s = p.strategy; const m = p.match; const P = Pp();
  const subs = Object.entries(m.scores).map(([k, v]) => `<div class="sub"><span class="muted">${esc(k)}</span>${bar(v)}<span class="v">${pct(v)}</span></div>`).join('');
  const opts = (s.options || []).map((o) => `<div class="card flat stack tight"><div class="row between"><b>${esc(o.key)} · ${esc(o.angle || '')}</b>${o.key === s.chosen ? chip('Choisi', 'good') : ''}</div>
    <span class="small">${esc(o.title || '')}</span><span class="muted small">${esc(o.hook || '')}</span></div>`).join('');
  const expName = (id) => { const f = P && P.fact(id); return f ? `${f.data.title || f.text} · ${f.data.company || ''}` : id; };
  return `<div class="split"><div class="stack">
      <div class="card stack"><div class="card-head"><h3 class="h3">Angle retenu</h3>${chip(s.best.ats_mode, 'accent')}</div><h2 class="h2">« ${esc(s.best.title)} »</h2><p style="margin:0">${esc(s.best.hook || '')}</p><p class="muted small" style="margin:0">${esc(s.best.why || s.comparison || '')}</p></div>
      <div class="card"><h3 class="h3">Options comparées</h3><div class="grid g3" style="margin-top:12px">${opts || '<p class="muted small">—</p>'}</div></div>
      <div class="card"><h3 class="h3">Expériences</h3><div class="grid g2" style="margin-top:12px"><div><b class="small">Mises en avant</b><ul class="why-list">${(s.best.experiences_up || []).map((id) => `<li><span>${esc(expName(id))}</span></li>`).join('') || '<li><span>—</span></li>'}</ul></div>
        <div><b class="small">En retrait</b><ul class="why-list">${(s.best.experiences_down || []).map((id) => `<li><span>${esc(expName(id))}</span></li>`).join('') || '<li><span>—</span></li>'}</ul></div></div></div>
    </div><div class="stack">
      ${p.design ? `<div class="card stack"><div class="card-head"><h3 class="h3">Design automatique</h3>${chip(DESIGN_NAME(p.design.design), 'gold')}</div><div class="design-decision">${designMini(p.design.design, p.design.palette)}<span class="small">${esc(paletteLabel(p.design.palette))} · ${esc(DENSITY_LABEL[p.design.density] || '')} · ${esc(PHOTO_LABEL[p.design.photo_mode])}</span></div>
        <ul class="why-list">${p.design.why.map((w) => `<li><span><b>${esc(w.k)}</b> · ${esc(w.t)}</span></li>`).join('')}</ul></div>` : ''}
      <div class="card"><h3 class="h3">Sous-scores</h3><div class="stack" style="gap:8px;margin-top:12px">${subs}</div></div>
      <div class="card"><h3 class="h3">Pourquoi ça colle</h3>${m.why_fit && m.why_fit.length ? `<ul class="why-list" style="margin-top:10px">${m.why_fit.map((x) => `<li><span>${esc(typeof x === 'string' ? x : x.text || '')}</span></li>`).join('')}</ul>` : '<p class="muted small">—</p>'}</div></div></div>`;
}

function packRisks(p) {
  const m = p.match;
  return `<div class="grid g2">
    <div class="card"><h3 class="h3">Risques</h3><ul class="why-list" style="margin-top:12px">${p.risks.map((r) => `<li><span>${esc(r)}</span></li>`).join('') || '<li><span>Aucun risque majeur détecté.</span></li>'}</ul></div>
    <div class="card"><h3 class="h3">Manques : jamais écrits, à préparer pour l'entretien</h3><ul class="why-list" style="margin-top:12px">${m.missing.map((x) => `<li><span><b>${esc(x.requirement)}</b> ${chip(x.priority, x.priority === 'MUST' ? 'bad' : 'warn')}${x.note ? ` · ${esc(x.note)}` : ''}</span></li>`).join('') || '<li><span>Aucun manque.</span></li>'}</ul></div>
    <div class="card"><h3 class="h3">Données de profil manquantes</h3><ul class="why-list" style="margin-top:12px">${(p.missing_profile_data || []).slice(0, 12).map((x) => `<li><span>${esc(x)}</span></li>`).join('') || '<li><span>—</span></li>'}</ul></div>
    <div class="card"><h3 class="h3">Lignes retirées (non prouvées)</h3>${p.cvs.length && (p.cvs[p.cv_index].doc.removed_lines || []).length ? `<div class="list">${p.cvs[p.cv_index].doc.removed_lines.map((r) => `<div class="item"><span class="grow"><span class="t" style="white-space:normal">${esc(r.text)}</span><span class="s">${esc((r.reasons || []).join(' ; '))}</span></span></div>`).join('')}</div>` : '<p class="muted small" style="margin:12px 0 0">Aucune.</p>'}</div></div>`;
}

function packQuestions(p) {
  if (!p.answers.length) return emptyState('i-text', 'Aucune question pour ce pack', 'Ajoute les questions du formulaire dans les options de l\'analyse (« Questions du formulaire »).');
  const toneOf = { HIGH: 'good', MEDIUM: 'accent', LOW: 'warn', BLOCKED: 'bad' };
  return `<div class="card"><div class="list">${p.answers.map((x, i) => `<div class="item" style="align-items:flex-start"><span class="grow stack tight"><span class="t" style="white-space:normal">${esc(x.question)}</span>
    <span class="row" style="gap:6px">${chip(x.type)}${chip(x.confidence, toneOf[x.confidence])}${fids(x.fact_ids)}</span>
    ${x.confidence === 'BLOCKED' ? `<span class="s">${esc(x.ask_user)}</span><div class="row"><input class="input" id="ans-${i}" placeholder="Ta réponse" value="${esc(x.user_answer || '')}" style="flex:1"><button class="btn sm" data-act="answer-save" data-arg="${i}">Enregistrer</button></div>` : `<span>${esc(x.answer)}</span>`}</span></div>`).join('')}</div></div>`;
}

// ── CV Studio : l'A4 réel au centre, la stratégie à gauche, la qualité à droite ──
V.studio = () => {
  let p = curPack();
  if (!p || !p.cvs.length) p = S.packs.find((x) => x.cvs && x.cvs.length) || null;
  if (!p) return `<div class="page">${emptyState('i-layout', 'CV Studio', 'Analyse une offre : ton CV sur mesure s\'ouvrira ici, avec son aperçu A4 réel, ses scores et ses preuves.', ['go', 'accueil', 'Analyser une offre'])}</div>`;
  if (p.id !== S.packId) { S.packId = p.id; lsSet('packId', p.id); }
  const others = S.packs.filter((x) => x.cvs && x.cvs.length);
  return `<div class="page"><header class="studio-head"><div class="stack tight"><span class="kicker">CV Studio · ${esc(disp(p.analysis.company, 'company'))}</span><h1 class="title">${esc(p.analysis.job_title)}</h1></div>
    <div class="row">${others.length > 1 ? `<select class="select" style="width:auto;min-width:260px" data-change="studio-pack" aria-label="Changer de pack">${others.map((x) => `<option value="${esc(x.id)}" ${x.id === p.id ? 'selected' : ''}>${esc(x.analysis.job_title)} · ${esc(disp(x.analysis.company, 'company'))}</option>`).join('')}</select>` : ''}
      <button class="btn" data-act="open-pack" data-arg="${esc(p.id)}">${icon('i-stack')} Pack complet</button><button class="btn primary" data-act="dl-cv">${icon('i-download')} Télécharger le PDF</button></div></header>${studio(p)}</div>`;
};

// Le même document rendu dans chacun des 5 designs (aperçus réels, mis en cache).
function familyDoc(doc, f) {
  const dd = D.designs[f] || {}; const pal = (dd.palettes || []).includes(doc.palette) ? doc.palette : dd.palette_default || 'petrol';
  const mode = doc.photo_mode === 'SIDEBAR' && f !== 'digital_creative' ? 'HEADER' : doc.photo_mode === 'HEADER' && f === 'digital_creative' ? 'SIDEBAR' : doc.photo_mode;
  return Object.assign({}, doc, { design_profile: f, palette: pal, photo_mode: mode, colors: pal === doc.palette ? doc.colors : undefined });
}
function studio(p) {
  const idx = cvIdx(p); const e = p.cvs[idx]; const doc = viewDoc(p, idx); const draft = studioDraft(p, idx);
  const pending = draft && Object.keys(draft).filter((k) => !['design_why', 'density_locked'].includes(k)).length; const prev = idx > 0 ? p.cvs[idx - 1] : null;
  const changes = prev ? compareDocs(prev.doc, e.doc) : changesSinceProfile(p, e.doc);
  const scores = cvScores(p, e, doc); const fam = DS.familyOf(doc.design_profile); const dd = D.designs[fam] || {};
  const pal = doc.palette || dd.palette_default || 'petrol'; const qa = e.qa || {};
  const photoOk = !!S.photoAssets; const mode = doc.photo_mode || 'OFF'; const open = !!S.galleryOpen;
  const gallery = open ? `<div class="gallery"><div class="row between"><span class="kicker quiet">Ton CV dans les 5 designs · aperçus réels</span><button class="tb-btn" data-act="design-auto">${icon('i-wand')} Choix automatique</button></div>
    <div class="designs">${DS.FAMILIES.map((f) => `<button data-act="set-design" data-arg="${f}" aria-pressed="${fam === f}" title="${esc((D.designs[f] || {}).pitch || '')}">${paper('cv', familyDoc(doc, f), () => PDF.cvDef(familyDoc(doc, f)), { width: 300, label: `Aperçu ${DESIGN_NAME(f)}` })}<span>${esc(DESIGN_NAME(f))}</span>${p.design && p.design.design === f ? '<em class="auto-tag">Auto</em>' : ''}</button>`).join('')}</div>
    <div class="opts"><div class="field"><span class="label">Densité</span><div class="seg" role="group" aria-label="Densité">${DS.DENSITY_ORDER.map((k) => `<button data-act="set-density" data-arg="${k}" aria-pressed="${(doc.density || 'balanced') === k}">${DENSITY_LABEL[k]}</button>`).join('')}</div></div>
      <div class="field"><span class="label">Photo</span><div class="seg" role="group" aria-label="Photo sur ce CV">${[['OFF', 'Sans'], ['HEADER', 'En-tête'], ['SIDEBAR', 'Colonne']].map(([k, l]) => `<button data-act="set-photo" data-arg="${k}" aria-pressed="${mode === k}" ${!photoOk && k !== 'OFF' ? 'disabled' : ''}>${l}</button>`).join('')}</div></div>
      <div class="opt-note"><span class="hint">${photoOk ? `${S.photoAssets.lowRes ? 'Photo en basse résolution · ' : ''}<button class="linkish" data-act="go" data-arg="profil-photo">Recadrer ou remplacer la photo</button>` : '<button class="linkish" data-act="go" data-arg="profil-photo">Ajouter ta photo professionnelle</button>'}</span>${whyDesign(p.design)}</div></div></div>` : '';
  return `<div class="studio">
    <aside class="col left panel">
      <section><h3 class="h3">Pourquoi ce CV ?</h3><ul class="why-list">${whyThisCv(p, e.doc).map((t) => `<li><span>${esc(t)}</span></li>`).join('')}</ul></section>
      <section><h3 class="h3">Ce qui a changé</h3><span class="hint">${prev ? `${esc(prev.label || `V${prev.v}`)} → ${esc(e.label || `V${e.v}`)}` : 'Depuis ton Master Profile'}</span>${changeList(changes)}</section>
      <section><h3 class="h3">Retouches</h3>
        <div class="field"><label for="f-headline">Titre du CV</label><div class="row" style="flex-wrap:nowrap"><input id="f-headline" class="input grow" value="${esc((E.sectionLines(e.doc, 'headline')[0] || {}).text || '')}"><button class="btn sm" data-act="set-headline">OK</button></div></div>
        <div class="field"><span class="label">Ordre des expériences</span><div>${e.doc.experiences.map((b, i) => `<div class="exp-row"><span>${esc(b.title)} · <span class="muted">${esc(b.company)}</span></span><span class="row" style="gap:2px;flex-wrap:nowrap"><button class="btn icon sm ghost" data-act="exp-up" data-arg="${i}" ${i === 0 ? 'disabled' : ''} aria-label="Monter">↑</button><button class="btn icon sm ghost" data-act="exp-down" data-arg="${i}" ${i === e.doc.experiences.length - 1 ? 'disabled' : ''} aria-label="Descendre">↓</button></span></div>`).join('')}</div></div>
        <div class="row"><button class="btn sm" data-act="rewrite-summary" ${AI.ok() ? '' : 'disabled title="IA indisponible"'}>${icon('i-wand')} Réécrire l'accroche</button><button class="btn sm" data-act="lab-v2" data-arg="${esc(p.id)}">${icon('i-refresh')} V2 avec mes avis</button></div></section>
    </aside>
    <section class="col center"><div class="desk desk-stage">
      <div class="toolbar">
        <div class="grp"><div class="version-pills" role="group" aria-label="Versions">${p.cvs.map((x, i) => `<button data-act="cv-version" data-arg="${i}" aria-pressed="${i === idx}" title="${esc(x.change || '')}">${esc(x.label && x.label.length < 5 ? x.label : `V${x.v}`)}</button>`).join('')}</div><span class="sep"></span>
          <button class="tb-btn" data-act="toggle-gallery" aria-expanded="${open}">${icon('i-palette')} <b>${esc(DESIGN_NAME(fam))}</b></button>
          <span class="tb-dots" role="group" aria-label="Couleurs">${(dd.palettes || Object.keys(DS.PALETTES)).map((k) => `<button class="swatch" data-act="set-palette" data-arg="${k}" aria-pressed="${pal === k}" aria-label="${esc(paletteLabel(k))}" title="${esc(paletteLabel(k))}" style="background:linear-gradient(135deg, ${DS.PALETTES[k].deep} 0 55%, ${DS.PALETTES[k].gold} 55%)"></button>`).join('')}</span></div>
        <div class="grp"><div class="seg" role="group" aria-label="Affichage"><button data-act="preview-mode" data-arg="pdf" aria-pressed="${S.previewMode === 'pdf'}">PDF réel</button><button data-act="preview-mode" data-arg="proof" aria-pressed="${S.previewMode === 'proof'}">Preuves</button></div></div>
      </div>
      ${gallery}
      <div class="canvas-wrap">${S.previewMode === 'proof' ? sheetHTML(doc, { rejected: e.report.rejected_ids || [] }) : cvPaper(doc, { width: 900 })}</div>
      <p class="desk-note">${S.previewMode === 'proof' ? 'Survole une ligne : les faits qui la prouvent s\'affichent.' : `Vrai PDF, texte sélectionnable · ${qa.pages ? `${qa.pages} page · police min. ${qa.min_font_pt || '—'} pt · mots-clés REQUIRED ${qa.required_found}` : 'contrôle à la prochaine version'}${pending ? ' · aperçu non enregistré' : ''}`}</p>
      ${pending ? `<div class="draft-pill">${icon('i-palette')}<span>${esc(Object.keys(draft).filter((k) => !['design_why', 'density_locked', 'colors'].includes(k)).map((k) => ({ design_profile: DESIGN_NAME(draft.design_profile), palette: paletteLabel(draft.palette), density: DENSITY_LABEL[draft.density], photo_mode: PHOTO_LABEL[draft.photo_mode] })[k] || k).join(' · '))}</span>
        <button class="btn sm primary" data-act="studio-save">Enregistrer en V${Math.max(...p.cvs.map((x) => x.v || 0)) + 1}</button><button class="btn sm ghost" data-act="studio-reset">Annuler</button></div>` : ''}
    </div></section>
    <aside class="col right panel">
      <section><div class="card-head" style="margin:0"><h3 class="h3">Qualité</h3><span class="chip">${e.critique && e.critique.ai ? 'Jury IA + calcul' : 'Calcul déterministe'}</span></div><div class="score-list">${scores.map(scoreCard).join('')}</div></section>
      <section>${feedbackBox(p, 'cv', idx, { regen: true })}</section>
      ${(e.doc.removed_lines || []).length ? `<section><details class="more"><summary>Lignes retirées faute de preuve (${e.doc.removed_lines.length})</summary><div class="list">${e.doc.removed_lines.map((r) => `<div class="item"><span class="grow"><span class="small">${esc(r.text)}</span><span class="s">${esc((r.reasons || []).join(' ; '))}</span></span></div>`).join('')}</div></details></section>` : ''}
    </aside>
  </div>`;
}

// ── Letter Studio : même atelier, même identité que le CV ──
function letterStudio(p) {
  const L = p.letters[p.letter_index]; const P = Pp(); const cvE = p.cvs[p.cv_index]; if (!L || !P) return emptyState('i-text', 'Pas de lettre', 'Lance la génération complète.');
  const layout = L.doc.layout || cvE.doc.design_profile; const refs = L.doc.lines.filter((l) => l.kind === 'offer_ref');
  const checks = L.checks || []; const open = !!S.galleryOpen; const fam = DS.familyOf(layout);
  const t = tone(L.report.factuality, 99.5, 95);
  const gallery = open ? `<div class="gallery"><span class="kicker quiet">La lettre dans les 5 mises en page · aperçus réels</span>
    <div class="designs">${DS.FAMILIES.map((f) => `<button data-act="set-letter-layout" data-arg="${f}" aria-pressed="${fam === f}">${letterPaper(Object.assign({}, L.doc, { layout: f }), cvE.doc, { width: 300, layout: f })}<span>${esc(DESIGN_NAME(f))}</span>${f === DS.familyOf(cvE.doc.design_profile) ? '<em class="auto-tag">Assortie</em>' : ''}</button>`).join('')}</div></div>` : '';
  return `<div class="studio letter">
    <aside class="col left panel">
      <section><h3 class="h3">Éléments propres à l'annonce</h3>${refs.length ? `<ul class="why-list">${refs.map((l) => `<li><span>« ${esc(l.offer_quote || l.text)} »</span></li>`).join('')}</ul>` : '<p class="muted small" style="margin:0">Aucun.</p>'}
        <span><span class="chip ${refs.length >= 2 ? 'good' : 'warn'}">${refs.length}/2 minimum</span></span></section>
      <section><h3 class="h3">Pourquoi cette entreprise ?</h3>${companyCardHtml(p.company || E.companyCard(p.analysis, p.offer))}
        ${whyCompany(p).length ? `<ul class="why-list">${whyCompany(p).slice(0, 3).map((x) => `<li><span>${esc(x)}</span></li>`).join('')}</ul>` : ''}</section>
    </aside>
    <section class="col center"><div class="desk desk-stage">
      <div class="toolbar"><div class="grp"><button class="tb-btn" data-act="toggle-gallery" aria-expanded="${open}">${icon('i-palette')} Mise en page <b>${esc(DESIGN_NAME(fam))}</b></button>${fam === DS.familyOf(cvE.doc.design_profile) ? '<span class="chip good">Assortie au CV</span>' : '<span class="chip accent">Personnalisée</span>'}</div>
        <div class="grp"><div class="seg" role="group" aria-label="Affichage"><button data-act="letter-mode" data-arg="pdf" aria-pressed="${S.letterMode === 'pdf'}">PDF réel</button><button data-act="letter-mode" data-arg="proof" aria-pressed="${S.letterMode === 'proof'}">Preuves</button></div></div></div>
      ${gallery}
      <div class="canvas-wrap">${S.letterMode === 'proof' ? letterSheetHTML(L.doc, P.value('id.name'), E.contactLines(P), { rejected: L.report.rejected_ids }) : letterPaper(L.doc, cvE.doc, { width: 900, layout })}</div>
      <p class="desk-note">Même palette, mêmes polices, même en-tête que le CV : une seule candidature, deux documents.</p>
    </div></section>
    <aside class="col right panel">
      <section><div class="score" style="border:0;padding:0"><span class="nb ${t}">${pct(L.report.factuality)}</span><div class="stack tight"><span class="k">Factualité</span>${bar(L.report.factuality, t)}<span class="why">${L.report.traced}/${L.report.total} phrases tracées vers tes faits ou citées de l'annonce</span></div></div></section>
      <section><h3 class="h3">Contrôles</h3>${checks.length ? `<div class="list">${checks.map((c) => `<div class="item"><span class="grow small">${esc(c.detail)}</span>${chip(c.severity, c.severity === 'high' ? 'bad' : c.severity === 'medium' ? 'warn' : '')}</div>`).join('')}</div>` : `<p class="small" style="margin:0">${icon('i-check')} Entreprise et intitulé présents, au moins 2 éléments propres à l'annonce, aucune phrase creuse.</p>`}</section>
      <section><details class="more"><summary>Phrases et preuves (${L.doc.lines.length})</summary><div class="list">${L.doc.lines.map((l) => `<div class="item" style="align-items:flex-start"><span class="grow small">${esc(l.text)}</span><span class="row" style="gap:4px">${chip(l.kind)}${fids(l.fact_ids)}</span></div>`).join('')}</div></details></section>
      <section>${feedbackBox(p, 'letter', p.letter_index)}</section>
    </aside></div>`;
}

// ── Versions et comparaison V1 / V2 ──
function packVersions(p) {
  const v = p.versions; const n = p.cvs.length;
  const A = S.compareWith !== null && p.cvs[S.compareWith] ? S.compareWith : Math.max(0, n - 2); const B = cvIdx(p) !== A ? cvIdx(p) : n - 1;
  return `<div class="stack">
    ${n > 1 ? compareView(p, A, B) : `<div class="card"><p style="margin:0">Une seule version pour l'instant. Donne ton avis puis génère une V2 : la comparaison visuelle apparaîtra ici.</p></div>`}
    <div class="split"><div class="card"><h3 class="h3">Versions du CV</h3><div class="list">${p.cvs.map((x, i) => `<div class="item"><span class="grow"><span class="t">${esc(x.label || `V${x.v}`)}${i === p.cv_index ? ' · retenue' : ''}</span><span class="s">${fmtTime(x.created_at)} · ${esc(DESIGN_NAME(x.doc.design_profile))} · factualité ${pct(x.report.factuality)} %${x.change ? ` · ${esc(x.change)}` : ''}</span></span>
      <span class="row" style="gap:4px">${i !== p.cv_index ? `<button class="btn sm" data-act="cv-keep" data-arg="${i}">Retenir</button>` : chip('Retenue', 'good')}<button class="btn sm ghost" data-act="cv-version-open" data-arg="${i}">Ouvrir</button></span></div>`).join('')}</div></div>
    <div class="card"><h3 class="h3">Empreintes figées</h3><div class="table-wrap"><table class="t"><tbody>${Object.entries(v).map(([k, x]) => `<tr><th>${esc(k)}</th><td class="mono">${esc(x || '—')}</td></tr>`).join('')}<tr><th>created_at</th><td class="mono">${esc(p.created_at)}</td></tr><tr><th>IA</th><td>${esc(p.provider)} · ${(p.calls || []).length} appel(s)</td></tr></tbody></table></div></div></div></div>`;
}
function compareView(p, ia, ib) {
  const A = p.cvs[ia]; const B = p.cvs[ib]; const ch = compareDocs(A.doc, B.doc);
  const areas = ['Titre', 'Accroche', 'Expériences', 'Compétences', 'Ordre', 'Design', 'Couleurs', 'Photo', 'Densité'];
  const la = p.letters.length > 1 ? p.letters[p.letters.length - 2] : null; const lb = p.letters.length > 1 ? p.letters[p.letters.length - 1] : null;
  const letterDiff = la && lb ? (E.letterParagraphs(la.doc).join('\n') === E.letterParagraphs(lb.doc).join('\n') ? 'identique' : `${lb.label || 'V2'} réécrite (${E.letterParagraphs(lb.doc).length} paragraphes)`) : 'une seule version';
  const sA = cvScores(p, A); const sB = cvScores(p, B);
  const sel = (name, cur) => `<select class="select" style="width:auto" data-change="${name}" aria-label="Version">${p.cvs.map((x, i) => `<option value="${i}" ${i === cur ? 'selected' : ''}>${esc(x.label || `V${x.v}`)}</option>`).join('')}</select>`;
  return `<div class="stack loose"><div class="card-head" style="margin:0"><h2 class="h2">Comparaison visuelle</h2><div class="row">${sel('compare-a', ia)}<span class="muted">→</span>${sel('compare-b', ib)}</div></div>
    <div class="desk" style="padding:34px 30px 40px"><div class="compare"><div class="stack"><span class="kicker">${esc(A.label || `V${A.v}`)} · ${esc(DESIGN_NAME(A.doc.design_profile))}</span>${cvPaper(A.doc, { width: 560 })}</div><div class="stack"><span class="kicker">${esc(B.label || `V${B.v}`)} · ${esc(DESIGN_NAME(B.doc.design_profile))}</span>${cvPaper(B.doc, { width: 560 })}</div></div></div>
    <div class="table-wrap"><table class="t cmp"><thead><tr><th>Élément</th><th>Changement</th></tr></thead><tbody>
      ${areas.map((ar) => { const it = ch.filter((c) => c.area === ar); return `<tr><th>${ar}</th><td>${it.length ? it.map((c) => `<span class="chg ${c.cls}">${esc(c.t)}</span>`).join('<br>') : '<span class="muted">identique</span>'}</td></tr>`; }).join('')}
      <tr><th>Lettre</th><td>${esc(letterDiff)}</td></tr></tbody></table></div>
    <div class="table-wrap"><table class="t"><thead><tr><th>Score</th><th class="num">${esc(A.label || 'A')}</th><th class="num">${esc(B.label || 'B')}</th><th class="num">Écart</th></tr></thead><tbody>
      ${sA.map((s, i) => { const d = Math.round(sB[i].v) - Math.round(s.v); return `<tr><td>${esc(s.k)}</td><td class="num">${pct(s.v)}</td><td class="num">${pct(sB[i].v)}</td><td class="num ${d > 0 ? 'up' : d < 0 ? 'down' : ''}">${d > 0 ? '+' : ''}${d}</td></tr>`; }).join('')}</tbody></table></div></div>`;
}
