// ─── Vues ────────────────────────────────────────────────────────────────────
const V = {};

// Champ de commande « Analyser une offre » : lien, texte collé ou PDF (bouton ou glisser-déposer).
function commandBox(opts = {}) {
  const d = S.draft; const raw = d.input || ''; const isUrl = looksLikeUrl(raw);
  const textMode = d.textMode || (!isUrl && raw.includes('\n'));
  const running = S.run && S.run.status === 'running';
  return `<div class="command${opts.compact ? ' compact' : ''}" id="command" data-drop="Dépose le PDF de l'offre">
    <div class="box">${icon(isUrl ? 'i-link' : textMode ? 'i-text' : 'i-spark', 'lead-ico')}
      <textarea id="cmd-input" class="${textMode ? 'tall' : ''}" rows="${textMode ? 8 : 1}" data-bind="draft.input" spellcheck="false" aria-label="Lien ou texte de l'offre"
        placeholder="${textMode ? 'Colle le texte complet de l\'offre ici…' : 'Colle l\'URL de l\'offre ici...'}">${esc(raw)}</textarea>
      ${raw ? `<button class="btn icon sm ghost" data-act="cmd-clear" aria-label="Effacer">${icon('i-x')}</button>` : ''}</div>
    ${d.notice ? `<div class="notice ${d.notice.tone || 'warn'}">${icon('i-alert')}<div class="stack tight"><span>${esc(d.notice.text)}</span>
      ${d.notice.fallback ? `<div class="row"><button class="btn sm" data-act="cmd-text">${icon('i-text')} Coller le texte</button><label class="btn sm" for="f-offer-pdf">${icon('i-file')} Importer le PDF</label></div>` : ''}</div></div>` : ''}
    <div class="foot">
      <div class="row">
        <button class="tool" data-act="cmd-text" aria-pressed="${!!textMode}">${icon('i-text')} Texte</button>
        <label class="tool" for="f-offer-pdf">${icon('i-file')} PDF</label><input id="f-offer-pdf" type="file" accept="application/pdf" class="sr" data-change="offer-pdf">
        <div class="seg" role="group" aria-label="Profondeur de l'analyse">${Object.entries(MODE_INFO).map(([k, [l]]) => `<button data-act="mode" data-arg="${k}" aria-pressed="${d.mode === k}" title="${esc(MODE_INFO[k][1])}">${l}</button>`).join('')}</div>
      </div>
      <button class="cta go" data-act="analyze" ${running ? 'disabled' : ''}>${running ? '<span class="live-dots">Analyse en cours</span>' : `Analyser ${icon('i-arrow')}`}</button>
      <span class="hint" id="cmd-hint">${esc(cmdHint())}</span>
    </div>
    <details class="more-opts" ${d.showMore ? 'open' : ''} data-toggle="showMore"><summary>${icon('i-sliders')} Intitulé, entreprise, questions du formulaire</summary>
      <div class="grid g2" style="margin-top:14px;gap:14px"><div class="field"><label for="f-title">Intitulé (facultatif)</label><input id="f-title" class="input" data-bind="draft.title" value="${esc(d.title)}"></div>
        <div class="field"><label for="f-company">Entreprise (facultatif)</label><input id="f-company" class="input" data-bind="draft.company" value="${esc(d.company)}"></div></div>
      <div class="field" style="margin-top:14px"><label for="f-questions">Questions du formulaire (une par ligne)</label><textarea id="f-questions" class="textarea" style="min-height:84px" data-bind="draft.questions" placeholder="Quelles sont vos prétentions salariales ?">${esc(d.questions)}</textarea></div>
      <p class="hint" style="margin:12px 0 4px">${esc(MODE_INFO[d.mode][1])} ${AI.ok() ? `IA : ${esc(AI.label())}.` : 'Sans IA : chaque étape suit sa voie déterministe (même vérité, moins de rédaction).'}
        <button class="linkish" data-act="example">Essayer avec une offre fictive</button></p>
    </details>
  </div>`;
}
function cmdHint() {
  const d = S.draft; const raw = d.input || ''; const isUrl = looksLikeUrl(raw); const textMode = d.textMode || (!isUrl && raw.includes('\n'));
  if (!raw.trim()) return textMode ? 'Intitulé, entreprise, missions, profil recherché : colle tout, PAI fait le tri.' : 'Un lien, un texte ou un PDF glissé ici · Ctrl + Entrée pour lancer';
  if (isUrl) return SERVER ? `Lien détecté · ${hostOf(raw)} · lecture sécurisée par ton serveur PAI` : 'Lien détecté · dans claude.ai, PAI ne peut pas ouvrir de lien : colle le texte ou importe le PDF';
  const n = raw.trim().length;
  return `${d.sourceType === 'pdf' ? `PDF « ${d.fileName || 'offre'} » · ` : ''}${n.toLocaleString('fr-FR')} caractères${n < 80 ? ' · trop court (80 minimum)' : ' · prêt à analyser'}`;
}

V.accueil = () => {
  const P = Pp(); const packs = S.packs; const na = nextAction(); const name = P ? firstName(P.value('id.name', '')) : '';
  const withCv = packs.filter((p) => p.cvs && p.cvs.length);
  const fact = withCv.length ? withCv.reduce((n, p) => n + (p.scores.factuality_cv || 0), 0) / withCv.length : null;
  return `<div class="page home">
    <section class="hero">
      <div class="aurora" aria-hidden="true"></div>
      ${name ? `<span class="kicker">Bonjour ${esc(name)}</span>` : ''}
      <h1 class="wordmark hero-mark">PA<em>I</em></h1>
      <p class="subbrand">Personal Application Intelligence</p>
      <p class="tagline hero-lede">Transforme n'importe quelle offre en <em>candidature personnalisée</em>.</p>
      ${commandBox()}
    </section>
    <section class="nba">${icon('i-bolt')}<div class="t"><span class="kicker">Next best action</span>${esc(na.t)}</div>
      <button class="btn gold sm" data-act="${na.act}" data-arg="${esc(na.arg)}">${esc(na.cta)} ${icon('i-arrow')}</button></section>
    ${S.ai === 'denied' ? `<div class="notice warn" style="width:min(880px,100%);margin:0 auto">${icon('i-info')}<span>L'IA n'est pas autorisée pour cette page : PAI fonctionne sans IA (CV et lettre tirés de tes faits, sans rédaction).</span></div>` : ''}
    ${packs.length ? `<section class="shelf"><div class="shelf-head"><h2 class="h2">Reprendre</h2><button class="btn sm ghost" data-act="go" data-arg="packs">Tous les packs ${icon('i-arrow')}</button></div>
      <div class="covers">${packs.slice(0, 5).map(packCover).join('')}</div></section>` : ''}
    ${packs.length ? `<p class="quiet"><b>${packs.length}</b> pack${packs.length > 1 ? 's' : ''} · factualité moyenne <b>${fact === null ? '—' : `${Math.round(fact)}\u00a0%`}</b> · <b>${S.feedback.length}</b> avis · <b>${(S.rules.accepted || []).length}</b> ${(S.rules.accepted || []).length > 1 ? 'règles apprises' : 'règle apprise'} · rien n'est jamais envoyé à ta place</p>` : '<p class="quiet">Rien n\'est jamais inventé ni envoyé à ta place : chaque ligne est prouvée par tes faits.</p>'}
  </div>`;
};

// ── Analyser : la génération en direct, étape par étape ──
V.analyser = () => {
  const r = S.run;
  if (!r) {
    return `<div class="page"><div class="page-head"><div class="stack"><span class="kicker">Analyser</span><h1 class="title">De l'offre au <em>pack</em>, en neuf étapes</h1>
      <p class="lede">Lecture, compréhension, entreprise, correspondance, stratégie, CV, lettre, pack, contrôle du PDF : chaque étape s'affiche en direct. Sans IA, chacune suit sa voie déterministe.</p></div></div>
      <div class="split"><div class="stack">${commandBox({ compact: true })}</div><div id="run-panel">${stageList(null)}</div></div></div>`;
  }
  return `<div class="page run">
    <div class="run-grid"><section class="run-left"><div class="head" id="run-head">${runHead()}</div><div id="run-panel">${runPanel()}</div></section>
      <section class="run-canvas desk" id="run-side">${runSideItems().map(([k, h]) => sideItem(k, h, false)).join('')}</section></div></div>`;
};
function runHead() {
  const r = S.run; const a = r.results.analysis;
  return `<span class="kicker">Analyse ${esc(MODE_INFO[r.mode][0].toLowerCase())}${r.meta && r.meta.url ? ` · ${esc(hostOf(r.meta.url))}` : r.meta && r.meta.file ? ` · ${esc(r.meta.file)}` : ''}</span>
    <h1 class="title">${a ? esc(a.job_title) : r.status === 'failed' ? 'Analyse interrompue' : r.status === 'cancelled' ? 'Analyse arrêtée' : '<span class="live-dots">Lecture de l\'offre</span>'}</h1>
    ${a ? `<p class="meta">${esc(disp(a.company, 'company'))} · ${esc(disp(a.location, 'location'))} · ${esc(disp(a.contract, 'contract'))}</p>` : ''}
    <div class="row" style="margin-top:6px">${r.status === 'running' ? `<button class="btn sm" data-act="cancel">${icon('i-x')} Arrêter</button>` : `<button class="btn sm" data-act="new-analysis">${icon('i-plus')} Nouvelle analyse</button>`}</div>`;
}
function runPanel() {
  const r = S.run; if (!r) return stageList(null);
  return `<div class="card-head" id="run-chip">${runChip()}</div>${stageList(r)}<div id="run-foot">${runFoot()}</div>`;
}
const runPct = () => { const r = S.run; if (!r) return 0; const total = r.steps.filter((s) => s.state !== 'skip').length; return Math.round((100 * r.steps.filter((s) => s.state === 'done').length) / Math.max(1, total)); };
function runChip() {
  const r = S.run; const done = r.steps.filter((s) => s.state === 'done').length; const total = r.steps.filter((s) => s.state !== 'skip').length;
  return `<span class="kicker quiet">Progression</span><span class="chip ${r.status === 'running' ? 'accent live' : r.status === 'done' ? 'good' : 'bad'}"><span class="dot"></span>${r.status === 'running' ? `${done}/${total} étapes` : r.status === 'done' ? `Terminé${r.ms ? ` en ${fmtMs(r.ms)}` : ''}` : r.status === 'cancelled' ? 'Arrêté' : 'Échec'}</span>`;
}
function runFoot() {
  const r = S.run;
  return `${r.error ? `<div class="notice ${r.fallback ? 'warn' : 'bad'}">${icon('i-alert')}<div class="stack tight"><span>${esc(r.error)}</span>${r.fallback ? `<div class="row"><button class="btn sm" data-act="cmd-text-go">${icon('i-text')} Coller le texte</button><label class="btn sm" for="f-offer-pdf2">${icon('i-file')} Importer le PDF</label><input id="f-offer-pdf2" type="file" accept="application/pdf" class="sr" data-change="offer-pdf"></div>` : ''}</div></div>` : ''}
    ${r.status === 'done' ? `<p class="hint" style="margin:6px 0 0">${r.calls.length ? `${nb(r.calls.length, 'appel', 'appels')} à ${esc(AI.short())}` : 'Aucun appel IA'} · rien n'est envoyé à ta place.</p>` : ''}`;
}
function runSideItems() {
  const r = S.run; if (!r) return [];
  const R = r.results; const out = [];
  if (R.company) {
    const c = R.company;
    out.push(['company', `<div class="note-card"><span class="kicker">Entreprise</span><div class="note-title">${esc(c.name || 'Non nommée')}</div>
      <div class="small muted">${esc(disp(c.location, 'location'))} · ${esc(disp(c.contract, 'contract'))}</div><div class="xs faint" style="margin-top:8px">D'après l'annonce · logo ${c.logo && c.logo.used ? 'vérifié' : 'non utilisé (non vérifié)'}</div></div>`]);
  }
  if (R.match) {
    const m = R.match; const cov = m.coverage.filter((c) => c.covered).length;
    out.push(['match', `<div class="note-card"><span class="kicker">Correspondance</span><div class="big">${pct(m.match)}<small>/ 100</small></div>
      ${bar(m.match)}<div class="xs muted" style="margin-top:8px">${cov}/${m.coverage.length} mots-clés prouvés · risque ${pct(m.risk)}</div></div>`]);
  }
  if (R.strategy && R.design) {
    const s = R.strategy.best; const au = R.design;
    out.push(['strategy', `<div class="note-card"><span class="kicker">Design choisi</span><div class="note-title">${esc(DESIGN_NAME(au.design))}</div>
      <div class="small muted">${esc(paletteLabel(au.palette))} · ${esc(PHOTO_LABEL[au.photo_mode])}</div><div class="xs faint" style="margin-top:8px">${esc((au.why.find((w) => w.k === 'secteur') || au.why[0] || {}).t || '')}</div></div>`]);
  }
  const p = r.packId ? packById(r.packId) : null;
  if (p && p.cvs.length) {
    const e = p.cvs[p.cv_index];
    out.push(['doc', `<div class="stack loose" style="align-items:center"><div class="doc-stack"><div class="front">${cvPaper(e.doc, { width: 640 })}</div>${p.letters.length ? `<div class="back">${letterPaper(p.letters[p.letter_index].doc, e.doc, { width: 520 })}</div>` : ''}</div>
      <div class="row" style="justify-content:center"><button class="cta" data-act="open-studio" data-arg="${esc(p.id)}">${icon('i-layout')} Ouvrir dans CV Studio</button><button class="btn lg" data-act="open-pack" data-arg="${esc(p.id)}">Ouvrir le pack</button></div>
      <p class="hint" style="margin:0;text-align:center;max-width:52ch">${chip(p.status, p.status === 'FINAL' ? 'good' : 'warn')} ${esc(p.next_action)}</p></div>`]);
  } else if (p) {
    out.push(['doc', `<div class="stack" style="align-items:center;text-align:center"><h2 class="h2">Analyse enregistrée</h2><p class="lede">${esc(p.next_action)}</p><button class="cta" data-act="open-pack" data-arg="${esc(p.id)}">Ouvrir le pack ${icon('i-arrow')}</button></div>`]);
  } else if (r.status === 'running' && r.mode !== 'QUICK') {
    out.push(['wait', `<div class="stack loose" style="align-items:center"><div class="doc-stack"><div class="front"><div class="paper waiting"><div class="skeleton" aria-hidden="true"><i class="h"></i><i class="m"></i><i class="s"></i><i></i><i class="m"></i><i></i><i class="s"></i><i class="m"></i><i></i><i class="m"></i><i></i><i class="s"></i></div></div></div></div>
      <p class="hint" style="margin:0">Ton CV prend forme : le vrai PDF apparaît ici après le contrôle qualité.</p></div>`]);
  }
  return out;
}
const sideItem = (k, h, enter) => `<div class="side-item${enter ? ' enter' : ''}${['doc', 'wait'].includes(k) ? ' wide' : ''}" data-key="${k}" data-h="${E.hash(h)}">${h}</div>`;

// Mise à jour ciblée pendant l'analyse : seules les étapes et cartes qui changent sont remplacées (pas de clignotement).
function renderRun() {
  if (S.view === 'analyser' && S.run) {
    const head = $('#run-head'); if (head) { const h = runHead(); const hh = E.hash(h); if (head.dataset.h !== hh) { head.innerHTML = h; head.dataset.h = hh; } }
    const panel = $('#run-panel');
    if (panel) {
      const ol = $('ol.pipeline[data-run]', panel);
      if (!ol) panel.innerHTML = runPanel();
      else {
        $('#run-chip', panel).innerHTML = runChip();
        S.run.steps.forEach((s, i) => { const li = $(`li[data-k="${s.key}"]`, ol); if (li && li.dataset.sig !== stageSig(s)) li.outerHTML = stageLi(s, i, S.run.mode); });
        $('#run-foot', panel).innerHTML = runFoot();
      }
    }
    const side = $('#run-side');
    if (side) {
      const items = runSideItems(); const keep = new Set(items.map((x) => x[0]));
      [...side.children].forEach((ch) => { if (!keep.has(ch.dataset.key)) ch.remove(); });
      items.forEach(([k, h], i) => {
        const cur = side.querySelector(`[data-key="${k}"]`); const hh = E.hash(h);
        if (cur && cur.dataset.h === hh) { if (side.children[i] !== cur) side.insertBefore(cur, side.children[i] || null); return; }
        const tmp = document.createElement('div'); tmp.innerHTML = sideItem(k, h, !cur); const node = tmp.firstElementChild;
        if (cur) cur.replaceWith(node); else side.insertBefore(node, side.children[i] || null);
      });
      PDF.hydrate(side);
    }
  }
  renderTop();
}
