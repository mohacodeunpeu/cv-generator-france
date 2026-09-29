// ─── Profil : statuts, conflits (Source A / Source B), faits, photo, préférences ──
const PROFILE_FILTERS = [['validated', 'Validé'], ['imported', 'Importé'], ['verify', 'À vérifier'], ['unknown', 'Inconnu'], ['all', 'Tous']];
function factBucket(f, p) {
  if (f.status === 'FORBIDDEN') return 'forbidden';
  const inReview = (p.review_queue || []).some((r) => r.fact_id === f.id && r.severity !== 'info');
  if (f.needs_confirmation || inReview || f.status === 'UNVERIFIED' || f.status === 'INFERRED') return 'verify';
  if (f.status === 'IMPORTED') return 'imported';
  return 'validated';
}
function conflictPair(r, p) {
  const P = E.P(p); const A = P.fact(r.fact_id);
  const quotes = [...String(r.reason || '').matchAll(/«\s*([^»]+?)\s*»/g)].map((m) => m[1]);
  let B = r.counterpart ? P.fact(r.counterpart) : null;
  if (!B && A) {
    const toks = (t) => new Set(E.norm(t).split(/[^a-z0-9+]+/).filter((w) => w.length > 2));
    const ta = toks(A.text); let best = null; let bs = 0;
    for (const f of p.facts) {
      if (f.id === A.id || f.kind !== A.kind || f.status === 'FORBIDDEN') continue;
      const tb = toks(f.text); const inter = [...tb].filter((w) => ta.has(w)).length; const s = inter / Math.max(1, Math.min(ta.size, tb.size));
      if (s > bs || (s === bs && best && f.status === 'CONFIRMED' && best.status !== 'CONFIRMED')) { bs = s; best = f; }
    }
    if (best && bs >= 0.2) B = best;
  }
  const other = !B ? quotes.find((q) => !A || E.norm(q) !== E.norm(A.text)) || '' : '';
  return { A, B, other };
}
function conflictCard(r, i, p) {
  const { A, B, other } = conflictPair(r, p);
  const side = (label, f, text, act) => `<div class="side"><span class="eyebrow">${label}${f ? ` · ${esc(f.source || '')}` : ' · cité dans le motif'}</span><b>${esc(f ? f.text : text)}</b>
    <span class="row" style="gap:6px">${f ? `${statusChip(f.status)}<span class="fid">${esc(f.id)}</span>` : chip('Texte seul', '')}</span>
    <button class="btn sm primary" data-act="conflict-pick" data-arg="${i}:${act}">Choisir ${act}</button></div>`;
  const editing = S.conflictEdit === i;
  return `<div class="card stack conflict-card"><div class="card-head"><h3 class="h3">Conflit ${i + 1}</h3>${chip('À trancher par toi', 'bad')}</div>
    <p class="small" style="margin:0">${esc(r.reason)}</p>
    <div class="conflict">${side('Source A', A, '', 'A')}<span class="vs">ou</span>${side('Source B', B, other, 'B')}</div>
    ${editing ? `<div class="field"><label for="cf-text">Énoncé exact (remplace les deux)</label><textarea id="cf-text" class="textarea" style="min-height:70px">${esc((B || A || {}).text || other)}</textarea>
      <div class="row"><button class="btn sm primary" data-act="conflict-edit-save" data-arg="${i}">Enregistrer</button><button class="btn sm ghost" data-act="conflict-edit-cancel">Annuler</button></div></div>`
    : `<div class="row"><button class="btn sm" data-act="conflict-edit" data-arg="${i}">${icon('i-wand')} Modifier</button>${A && B ? `<button class="btn sm ghost" data-act="conflict-pick" data-arg="${i}:BOTH">Les deux sont vrais</button>` : ''}</div>`}
    <span class="hint">PAI ne tranche jamais à ta place : tant que ce conflit est ouvert, le profil ne peut pas être validé.</span></div>`;
}

V.profil = () => {
  const p = S.profile;
  if (!p) return `<div class="page"><div class="page-head"><div class="stack"><span class="eyebrow">Profil</span><h1 class="title">Ton <em>Master Profile</em></h1></div></div>
    <div class="card stack"><p style="margin:0">Aucun profil dans cette page. Importe un export JSON (depuis PAI ou le serveur PAI : <span class="mono">python -m pai export-profile</span>) ou suis la configuration guidée.</p>
    <div class="row"><button class="btn primary" data-act="go" data-arg="onboarding">Configuration guidée</button><label class="btn" for="f-prof">${icon('i-upload')} Importer un profil JSON</label><input id="f-prof" type="file" accept="application/json,.json" class="sr" data-change="profile-file"></div></div>${photoManager()}</div>`;
  const P = Pp(); const buckets = { validated: [], imported: [], verify: [], forbidden: [] };
  p.facts.forEach((f) => buckets[factBucket(f, p)].push(f));
  const counts = { validated: buckets.validated.length, imported: buckets.imported.length, verify: buckets.verify.length, unknown: (p.unknowns || []).length, all: p.facts.length };
  const filter = S.profileFilter; const shown = filter === 'all' ? p.facts.filter((f) => f.status !== 'FORBIDDEN') : buckets[filter] || [];
  const groups = {}; shown.forEach((f) => (groups[f.kind] = groups[f.kind] || []).push(f));
  const cfs = conflicts(p); const warnings = (p.review_queue || []).map((r, i) => [r, i]).filter(([r]) => r.severity !== 'conflict');
  const row = (f) => S.editFact === f.id
    ? `<div class="item" style="align-items:flex-start"><span class="grow stack tight"><textarea id="ef-text" class="textarea" style="min-height:60px">${esc(f.text)}</textarea>
        <div class="row"><select id="ef-status" class="select" style="width:auto">${['CONFIRMED', 'IMPORTED', 'INFERRED', 'UNVERIFIED', 'FORBIDDEN'].map((s) => `<option value="${s}" ${f.status === s ? 'selected' : ''}>${STATUS_LABEL[s]}</option>`).join('')}</select>
        <button class="btn sm primary" data-act="fact-save" data-arg="${esc(f.id)}">Enregistrer</button><button class="btn sm ghost" data-act="fact-cancel">Annuler</button></div></span></div>`
    : `<div class="item" style="align-items:flex-start"><span class="grow"><span>${esc(f.text)}</span><span class="s"><span class="fid">${esc(f.id)}</span> · ${esc(f.source)}${f.note ? ` · ${esc(f.note)}` : ''}</span></span>
      <span class="row" style="gap:6px">${f.needs_confirmation ? chip('chiffre à confirmer', 'warn') : ''}${statusChip(f.status)}${factBucket(f, p) === 'verify' && f.status !== 'FORBIDDEN' ? `<button class="btn sm" data-act="fact-confirm" data-arg="${esc(f.id)}">Confirmer</button>` : ''}<button class="btn sm ghost" data-act="fact-edit" data-arg="${esc(f.id)}" aria-label="Modifier ${esc(f.id)}">Modifier</button></span></div>`;
  return `<div class="page"><div class="page-head"><div class="stack"><span class="eyebrow">Profil</span><h1 class="title">${esc(P.value('id.name', 'Master Profile'))}</h1>
      <div class="row" style="gap:6px">${chip(`v${p.version}`, 'accent')}${p.validated ? chip(`Validé le ${fmtDate(p.validated_at)}`, 'good') : chip('Non validé : documents en brouillon', 'warn')}${chip(`${P.usableFacts().length} faits utilisables`)}<span class="mono muted">${esc(profileTag(p))}</span></div></div>
    <div class="row"><button class="btn primary" data-act="profile-validate" ${p.validated || cfs.length ? 'disabled' : ''}>${icon('i-shield')} Valider le profil v${p.version}</button><button class="btn" data-act="go" data-arg="onboarding">Configuration guidée</button></div></div>
    <div class="status-tabs" role="group" aria-label="Filtrer par statut">${PROFILE_FILTERS.map(([k, l]) => `<button data-act="profile-filter" data-arg="${k}" aria-pressed="${filter === k}"><span class="v">${counts[k]}</span><span class="l">${l}</span></button>`).join('')}</div>
    ${cfs.length ? `<div class="stack">${cfs.map((r) => conflictCard(r, (p.review_queue || []).indexOf(r), p)).join('')}</div>` : ''}
    <div class="split"><div class="stack">
      ${filter === 'unknown' ? `<div class="card"><h3 class="h3">Données inconnues</h3><p class="hint" style="margin:8px 0 0">PAI n'écrit jamais ce qu'il ne sait pas. Complète ce qui compte pour toi.</p><div class="list">${(p.unknowns || []).map((u) => `<div class="item"><span class="grow small">${esc(u)}</span><button class="btn sm" data-act="unknown-fill" data-arg="${esc(u.slice(0, 120))}">Renseigner</button></div>`).join('') || '<p class="muted small">Rien.</p>'}</div></div>`
    : KIND_ORDER.filter((k) => groups[k]).map((k) => `<div class="card"><div class="card-head"><h3 class="h3">${KIND_LABEL[k]}</h3>${chip(String(groups[k].length))}</div><div class="list">${groups[k].map(row).join('')}</div></div>`).join('') || '<div class="card muted">Aucun fait dans cette catégorie.</div>'}
      ${warnings.length ? `<div class="card"><h3 class="h3">À vérifier (${warnings.length})</h3><div class="list">${warnings.map(([r, i]) => { const f = P.fact(r.fact_id); return `<div class="item" style="align-items:flex-start"><span class="grow"><span class="small">${esc(r.reason)}</span><span class="s"><span class="fid">${esc(r.fact_id)}</span>${f ? ` · ${esc(f.text)}` : ''}</span></span>
        <span class="row" style="gap:6px">${chip(r.severity, r.severity === 'warning' ? 'warn' : '')}${f && f.status !== 'FORBIDDEN' ? `<button class="btn sm" data-act="review-confirm" data-arg="${i}">Confirmer</button><button class="btn sm ghost" data-act="review-reject" data-arg="${i}">Écarter</button>` : `<button class="btn sm ghost" data-act="review-dismiss" data-arg="${i}">Compris</button>`}</span></div>`; }).join('')}</div></div>` : ''}
    </div><div class="stack">
      ${photoManager()}
      <div class="card stack" id="add-fact"><h3 class="h3">Ajouter un fait (validé)</h3><div class="field"><label for="nf-kind">Type</label><select id="nf-kind" class="select">${KIND_ORDER.map((k) => `<option value="${k}">${KIND_LABEL[k]}</option>`).join('')}</select></div>
        <div class="field"><label for="nf-parent">Rattaché à (facultatif)</label><select id="nf-parent" class="select"><option value="">—</option>${P.experiences().map((e) => `<option value="${esc(e.id)}">${esc(e.data.title)} · ${esc(e.data.company)}</option>`).join('')}</select></div>
        <div class="field"><label for="nf-text">Énoncé exact</label><textarea id="nf-text" class="textarea" style="min-height:70px" data-bind="newFactText" placeholder="Ex. Bachelor REM — École X (2021-2024)">${esc(S.newFactText || '')}</textarea></div><button class="btn primary" data-act="fact-add">${icon('i-plus')} Ajouter</button></div>
      ${buckets.forbidden.length ? `<div class="card"><h3 class="h3">Jamais écrits (interdits)</h3><div class="list">${buckets.forbidden.map((f) => `<div class="item"><span class="grow small">${esc(f.text)}<span class="s">${esc(f.note || 'Bloqué par le validateur')}</span></span>${statusChip('FORBIDDEN')}</div>`).join('')}</div></div>` : ''}
      <div class="card stack"><h3 class="h3">Exporter / importer</h3><div class="row"><button class="btn sm" data-act="profile-export" data-arg="json">JSON</button><button class="btn sm" data-act="profile-export" data-arg="csv">CSV</button><button class="btn sm" data-act="profile-export" data-arg="md">MD</button>
        <label class="btn sm" for="f-prof">${icon('i-upload')} Importer</label><input id="f-prof" type="file" accept="application/json,.json" class="sr" data-change="profile-file"></div></div>
      <div class="card"><h3 class="h3">Historique</h3><div class="list">${(p.history || []).slice(-8).reverse().map((h) => `<div class="item"><span class="grow small">${esc(h.action)} · ${esc(h.detail)}</span><span class="s">${fmtTime(h.at)}</span></div>`).join('')}</div></div>
    </div></div></div>`;
};

// ── Onboarding en 5 étapes : Profil · Documents · Photo · Préférences · Validation ──
const OB_STEPS = [['profil', 'Profil', 'Qui tu es'], ['documents', 'Documents', 'Anciens CV, lettres'], ['photo', 'Photo', 'Optionnelle'], ['preferences', 'Préférences', 'Design, couleurs'], ['validation', 'Validation', 'Tout vérifier']];
const obDone = () => ((S.prefs && S.prefs.onboarding && S.prefs.onboarding.done) || {});
V.onboarding = () => {
  const done = obDone(); const p = S.profile;
  if (S.onboard === null || S.onboard === undefined) S.onboard = Math.max(0, OB_STEPS.findIndex(([k]) => !done[k]));
  const i = S.onboard; const [key] = OB_STEPS[i];
  const finished = p && p.validated && OB_STEPS.every(([k]) => done[k]);
  return `<div class="page"><div class="page-head"><div class="stack"><span class="eyebrow">Configuration · ${Object.keys(done).filter((k) => done[k]).length}/5</span><h1 class="title">${finished ? 'Votre profil est prêt.' : 'Prépare PAI <em>en 5 étapes</em>'}</h1>
      <p class="lede">${finished ? 'Colle une offre : PAI s\'occupe du reste, en ne disant que ce qui est vrai.' : 'Tes faits, tes documents, ta photo et tes goûts : PAI n\'écrira que ce que tu as validé.'}</p></div>
      ${finished ? `<button class="btn primary lg" data-act="go" data-arg="accueil">Analyser une offre ${icon('i-arrow')}</button>` : ''}</div>
    <div class="wizard" role="list">${OB_STEPS.map(([k, l, s], j) => `<button role="listitem" class="${done[k] ? 'done' : ''}" ${j === i ? 'aria-current="step"' : ''} data-act="ob-step" data-arg="${j}"><b>${l}</b><span>${s}</span></button>`).join('')}</div>
    <div data-anim>${({ profil: obProfil, documents: obDocuments, photo: obPhoto, preferences: obPrefs, validation: obValidation })[key]()}</div></div>`;
};
const obNext = (k, label) => `<div class="row end"><button class="btn primary" data-act="ob-done" data-arg="${k}">${esc(label || 'Continuer')} ${icon('i-arrow')}</button></div>`;
function obProfil() {
  const p = S.profile;
  if (!p) return `<div class="card stack"><h2 class="h2">Importe ton Master Profile</h2><p style="margin:0">Le profil contient tes faits (expériences, résultats, formation, langues), chacun avec son statut. Sur ton serveur : <span class="mono">python -m pai export-profile</span>.</p>
    <div class="row"><label class="btn primary" for="f-prof">${icon('i-upload')} Importer un profil JSON</label><input id="f-prof" type="file" accept="application/json,.json" class="sr" data-change="profile-file"></div></div>`;
  const P = Pp(); const roles = (P.fact('target.roles') || {}).data || {};
  return `<div class="card stack"><h2 class="h2">C'est bien toi ?</h2><dl class="kv"><dt>Nom</dt><dd>${esc(P.value('id.name', '—'))}</dd><dt>Contact</dt><dd>${esc(E.contactLines(P).join(' · ') || '—')}</dd>
    <dt>Postes visés</dt><dd>${esc((roles.roles || []).join(', ') || P.value('target.roles', '—'))}</dd><dt>Expériences</dt><dd>${P.experiences().length}</dd><dt>Faits utilisables</dt><dd>${P.usableFacts().length}</dd><dt>Version</dt><dd>v${p.version} · ${p.validated ? 'validée' : 'non validée'}</dd></dl>
    <p class="hint" style="margin:0">Un détail faux ? Corrige-le dans Profil : PAI ne réécrit jamais ton identité.</p>${obNext('profil', 'Oui, continuer')}</div>`;
}
function obDocuments() {
  const imp = S.jobImport && S.jobImport.origin === 'document' ? S.jobImport : null;
  return `<div class="card stack"><h2 class="h2">Tes anciens CV et lettres</h2><p style="margin:0">Importe-les en PDF : PAI lit le texte dans ton navigateur, le garde en privé pour le benchmark « ancien vs nouveau », et te propose d'ajouter des éléments au profil (en « À vérifier », jamais validés d'office).</p>
    <div class="row"><label class="btn primary" for="f-doc">${icon('i-upload')} Importer des PDF</label><input id="f-doc" type="file" accept="application/pdf" multiple class="sr" data-change="doc-files"></div>
    ${S.documents.length ? `<div class="list">${S.documents.map((d) => `<div class="item"><span class="grow"><span class="t">${esc(d.name)}</span><span class="s">${esc(d.kind === 'letter' ? 'Lettre' : 'CV')} · ${Number(d.chars || 0).toLocaleString('fr-FR')} caractères · empreinte ${esc(d.hash)}</span></span><button class="btn sm ghost" data-act="doc-review" data-arg="${esc(d.id)}">Extraire des faits</button></div>`).join('')}</div>` : ''}
    ${imp ? `<div class="stack"><b class="small">${esc(imp.name)} · ${imp.items.length} ligne(s)</b><div class="list ja-list">${imp.items.map((it, j) => `<div class="item" style="align-items:flex-start"><input type="checkbox" ${it.pick ? 'checked' : ''} data-change="ja-pick" data-arg="${j}" aria-label="Sélectionner"><span class="grow small">${esc(it.text)}</span>
      <select class="select" style="width:auto" data-change="ja-kind" data-arg="${j}" aria-label="Type">${KIND_ORDER.filter((k) => !['identity', 'contact'].includes(k)).map((k) => `<option value="${k}" ${it.kind === k ? 'selected' : ''}>${KIND_LABEL[k]}</option>`).join('')}</select></div>`).join('')}</div>
      <div class="row"><button class="btn primary" data-act="ja-accept">Ajouter la sélection (À vérifier)</button><button class="btn" data-act="ja-cancel">Fermer</button></div></div>` : ''}
    ${obNext('documents', S.documents.length ? 'Continuer' : 'Passer cette étape')}</div>`;
}
function obPhoto() {
  return `<div class="stack">${photoManager()}<div class="card stack"><p style="margin:0">La photo est optionnelle : en France elle est d'usage, mais PAI la retire automatiquement quand l'ATS est prioritaire ou quand le pays la déconseille. Tu peux aussi choisir « Sans photo ».</p>${obNext('photo', S.photo ? 'Continuer' : 'Continuer sans photo')}</div></div>`;
}
function obPrefs() {
  const pr = S.prefs || {}; const d = pr.design || 'auto'; const pal = pr.palette || 'auto';
  return `<div class="card stack"><h2 class="h2">Tes goûts</h2>
    <div class="field"><span class="label">Design préféré</span><div class="design-pick six"><button data-act="pref-design" data-arg="auto" aria-pressed="${d === 'auto'}"><span class="mini auto-mini">${icon('i-wand')}</span><span>Auto</span></button>${DS.FAMILIES.map((f) => `<button data-act="pref-design" data-arg="${f}" aria-pressed="${d === f}" title="${esc((D.designs[f] || {}).pitch || '')}">${designMini(f)}<span>${esc(DESIGN_NAME(f))}</span></button>`).join('')}</div>
      <span class="hint">${d === 'auto' ? 'Auto : PAI choisit selon le secteur, le pays, le niveau et l\'ATS de l\'annonce, et t\'explique pourquoi.' : esc((D.designs[d] || {}).pitch || '')}</span></div>
    <div class="field"><span class="label">Couleurs préférées</span><div class="row" style="gap:8px"><button class="btn sm ${pal === 'auto' ? 'primary' : ''}" data-act="pref-palette" data-arg="auto">Auto</button>${Object.entries(DS.PALETTES).map(([k, v]) => `<button class="swatch" data-act="pref-palette" data-arg="${k}" aria-pressed="${pal === k}" aria-label="${esc(v.label)}" title="${esc(v.label)}" style="background:linear-gradient(135deg, ${v.deep} 0 55%, ${v.gold} 55%)"></button>`).join('')}</div></div>
    <div class="field"><span class="label">Profondeur d'analyse par défaut</span><div class="seg">${Object.entries(MODE_INFO).map(([k, [l]]) => `<button data-act="mode" data-arg="${k}" aria-pressed="${S.draft.mode === k}">${l}</button>`).join('')}</div><span class="hint">${esc(MODE_INFO[S.draft.mode][1])}</span></div>
    ${obNext('preferences')}</div>`;
}
function obValidation() {
  const p = S.profile; if (!p) return `<div class="card">${emptyState('i-user', 'Pas encore de profil', 'Commence par l\'étape Profil.')}</div>`;
  const P = Pp(); const cfs = conflicts(p); const toConfirm = p.facts.filter((f) => f.needs_confirmation && E.usable(f));
  const checks = [[!cfs.length, cfs.length ? `${cfs.length} conflit(s) à trancher` : 'Aucun conflit ouvert'], [!toConfirm.length, toConfirm.length ? `${toConfirm.length} chiffre(s) importé(s) à confirmer (utilisables, marqués « à confirmer »)` : 'Tous les chiffres sont confirmés'],
    [P.experiences().length > 0, `${P.experiences().length} expérience(s)`], [!!S.photo || Photo.mode() === 'OFF', S.photo ? 'Photo prête' : 'Sans photo (choix possible à tout moment)'], [!!p.validated, p.validated ? `Profil v${p.version} validé` : `Profil v${p.version} à valider`]];
  return `<div class="card stack"><h2 class="h2">Dernière vérification</h2><ul class="checklist">${checks.map(([ok, t]) => `<li class="${ok ? 'ok' : 'todo'}">${icon(ok ? 'i-check' : 'i-alert')}<span>${esc(t)}</span></li>`).join('')}</ul>
    ${cfs.length ? `<div class="row"><button class="btn" data-act="go" data-arg="profil">${icon('i-user')} Trancher les conflits</button></div>` : ''}
    ${p.validated ? `<div class="notice good">${icon('i-check')}<span>Votre profil est prêt.</span></div>${obNext('validation', 'Terminer')}` : `<div class="row"><button class="btn primary lg" data-act="profile-validate" ${cfs.length ? 'disabled' : ''}>${icon('i-shield')} Valider le profil v${p.version}</button></div>`}</div>`;
}
