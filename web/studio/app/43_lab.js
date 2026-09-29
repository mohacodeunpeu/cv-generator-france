// ─── Training Lab : offre → V1 → 👍😐👎 → raisons → V2 → comparaison visuelle ──
V.lab = () => {
  const packs = S.packs.filter((p) => p.cvs && p.cvs.length);
  if (!packs.length) return `<div class="page">${labHead()}${emptyState('i-flask', 'Rien à entraîner pour l\'instant', 'Analyse une première offre : sa V1 arrivera ici pour ton avis.', ['go', 'accueil', 'Analyser une offre'])}</div>`;
  const p = packById(S.lab.packId) || packs[0]; S.lab.packId = p.id;
  const n = p.cvs.length; const v1 = p.cvs[0]; const last = p.cvs[n - 1];
  const fb = S.feedback.filter((f) => f.pack_id === p.id && f.doc === 'cv');
  const step = n > 1 ? 4 : fb.length ? 3 : S.lab.rate !== undefined ? 2 : 1;
  const flow = ['Offre', 'V1', 'Avis', 'V2', 'Comparaison'];
  return `<div class="page">${labHead()}
    <div class="row between"><div class="flow">${flow.map((f, i) => `${i ? '<i></i>' : ''}<span class="${i <= step ? 'on' : ''}">${f}</span>`).join('')}</div>
      <select class="select" style="width:auto" data-change="lab-pack" aria-label="Pack">${packs.map((x) => `<option value="${esc(x.id)}" ${x.id === p.id ? 'selected' : ''}>${esc(x.analysis.job_title)} · ${esc(disp(x.analysis.company, 'company'))}</option>`).join('')}</select></div>
    ${n > 1 ? compareView(p, 0, n - 1) : ''}
    <div class="split"><div class="desk" style="padding:40px 32px 48px"><div class="stack" style="align-items:center"><span class="kicker">${n > 1 ? `Dernière version · ${esc(last.label || `V${last.v}`)}` : 'V1'} · ${esc(DESIGN_NAME(last.doc.design_profile))}</span>
        <div class="lab-paper">${cvPaper(last.doc, { width: 700 })}</div></div></div>
    <div class="stack loose">
      <div class="stack"><h3 class="h3">1 · Ton verdict</h3>
        <div class="rate big" role="group" aria-label="Note">${RATE.map(([v, e, l]) => `<button data-act="lab-rate" data-arg="${v}" aria-pressed="${S.lab.rate === v}" aria-label="${l}">${e}<span>${l}</span></button>`).join('')}</div>
        <h3 class="h3">2 · Pourquoi ?</h3>
        <div class="reasons" role="group" aria-label="Raisons">${REASONS.map((r) => `<button data-act="lab-reason" data-arg="${esc(r)}" aria-pressed="${S.lab.reasons.includes(r)}">${esc(r)}</button>`).join('')}</div>
        <textarea id="lab-comment" class="textarea" style="min-height:72px" data-bind="lab.comment" placeholder="Précise si tu veux (ex. « titre trop long », « mettre Printemps en premier »)…">${esc(S.lab.comment || '')}</textarea>
        <h3 class="h3">3 · Nouvelle version</h3>
        <button class="cta" data-act="lab-generate" data-arg="${esc(p.id)}" ${S.lab.busy ? 'disabled' : ''}>${S.lab.busy ? '<span class="live-dots">Génération de la V2</span>' : `${icon('i-refresh')} Générer V${n + 1}`}</button>
        <p class="hint" style="margin:0">${AI.ok() ? `${esc(AI.short())} réécrit en tenant compte de ton avis ; le validateur contrôle chaque ligne.` : 'Sans IA : PAI applique des ajustements déterministes (design, couleur, photo, ordre, titre exact de l\'offre, ATS).'} Ton avis est enregistré et nourrit l'apprentissage.</p>
      </div>
      ${fb.length ? `<div class="card"><h3 class="h3">Avis sur ce pack (${fb.length})</h3><div class="list">${fb.slice(0, 6).map((f) => `<div class="item"><span class="grow small">${rateIcon(f.rating)} ${esc((f.reasons || [f.element]).join(', '))}${f.comment ? ` · ${esc(f.comment)}` : ''}</span><span class="s">V${esc(f.version + 1)}</span></div>`).join('')}</div></div>` : ''}
      <div class="card"><h3 class="h3">Historique</h3><div class="list">${packs.slice(0, 8).map((x) => `<button class="item" data-act="lab-open" data-arg="${esc(x.id)}"><span class="grow"><span class="t">${esc(x.analysis.job_title)}</span><span class="s">${nb(x.cvs.length, 'version', 'versions')} · ${S.feedback.filter((f) => f.pack_id === x.id).length} avis · ${fmtDate(x.created_at)}</span></span>${x.id === p.id ? chip('Ouvert', 'accent') : ''}</button>`).join('')}</div></div>
    </div></div></div>`;
};
const labHead = () => `<div class="page-head"><div class="stack"><span class="eyebrow">Training Lab</span><h1 class="title">Entraîne PAI à <em>ton goût</em></h1>
  <p class="lede">Offre → V1 → ton verdict → tes raisons → V2 → comparaison. Chaque avis devient une donnée d'apprentissage ; aucune règle n'est appliquée sans ta validation.</p></div></div>`;

// Ajustements de V2 sans IA : uniquement de la présentation ou des éléments déjà prouvés (jamais de contenu inventé).
function deterministicV2(p, doc, reasons) {
  const d = clone(doc); const notes = [];
  const fam = DS.familyOf(d.design_profile);
  if (reasons.includes('ATS') && fam !== 'ats_hybrid') { d.design_profile = 'ats_hybrid'; d.photo_mode = 'OFF'; notes.push('design ATS Hybrid, sans photo'); }
  else if (reasons.includes('Design')) { const order = DS.FAMILIES.filter((f) => f !== fam && !(p.strategy.best.ats_mode === 'ATS_FIRST' && (D.designs[f] || {}).ats_level === 'low')); d.design_profile = order[0]; notes.push(`design ${DESIGN_NAME(order[0])}`); }
  if (reasons.includes('Couleur')) { const pals = (D.designs[DS.familyOf(d.design_profile)] || {}).palettes || Object.keys(DS.PALETTES); const i = pals.indexOf(d.palette); d.palette = pals[(i + 1) % pals.length]; delete d.colors; notes.push(`palette ${paletteLabel(d.palette)}`); }
  if (reasons.includes('Photo') && S.photoAssets) { d.photo_mode = d.photo_mode && d.photo_mode !== 'OFF' ? 'OFF' : DS.familyOf(d.design_profile) === 'digital_creative' ? 'SIDEBAR' : 'HEADER'; notes.push(d.photo_mode === 'OFF' ? 'sans photo' : 'avec photo'); }
  if (reasons.includes('Titre')) { const h = E.sectionLines(d, 'headline')[0]; const exact = E.cleanTitle(p.analysis.job_title); if (h && exact && h.text !== exact) { h.text = exact; notes.push('titre = intitulé exact de l\'offre'); } }
  if (reasons.includes('Expérience') && d.experiences.length > 1) { const x = d.experiences.splice(1, 1)[0]; d.experiences.unshift(x); notes.push(`${x.company || x.title} en premier`); }
  if (reasons.includes('Accroche')) { const s = E.sectionLines(d, 'summary'); if (s.length > 1) { const ids = new Set(s.map((l) => l.id)); const rest = d.lines.filter((l) => !ids.has(l.id)); d.lines = s.slice().reverse().concat(rest); notes.push('accroche : preuve chiffrée en premier'); } }
  if (reasons.includes('Compétence') || reasons.includes('Personnalisation')) {
    const cov = new Set(p.match.coverage.filter((c) => c.covered).map((c) => E.norm(c.term)));
    const sk = E.sectionLines(d, 'skills'); const score = (l) => ([...cov].some((t) => E.norm(l.text).includes(t)) ? 0 : 1);
    const ids = new Set(sk.map((l) => l.id)); d.lines = d.lines.filter((l) => !ids.has(l.id)).concat(sk.slice().sort((x, y) => score(x) - score(y)));
    notes.push('compétences demandées par l\'offre en premier');
  }
  return { doc: d, notes };
}
