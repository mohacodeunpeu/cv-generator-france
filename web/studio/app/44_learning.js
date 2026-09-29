// ─── Learning : OBSERVE → ANALYZE → PROPOSE RULE → BENCHMARK → ACCEPT → VERSION ──
// Rien n'est appliqué automatiquement : chaque règle est proposée avec sa taille d'échantillon, puis validée (ou refusée) par toi.
const LEARN_FLOW = ['Observe', 'Analyze', 'Propose rule', 'Benchmark', 'Accept', 'Version'];
function learningPatterns() {
  const fb = S.feedback; const min = ((D.scoring || {}).learning || {}).min_feedback_for_trend || 5;
  const byReason = {};
  fb.forEach((f) => (f.reasons && f.reasons.length ? f.reasons : [f.element || 'Autre']).forEach((r) => {
    const k = `${(f.context || {}).sector || '—'}|${r}`; const o = byReason[k] = byReason[k] || { sector: (f.context || {}).sector || '—', reason: r, n: 0, pos: 0, neg: 0, comments: [] };
    o.n++; if (f.rating === 1) o.pos++; if (f.rating === -1) o.neg++; if (f.comment) o.comments.push(f.comment);
  }));
  return { min, rows: Object.values(byReason).sort((x, y) => y.n - x.n) };
}
// Propositions déterministes : un motif négatif répété (≥ seuil) devient une règle candidate, formulée sans rien supposer de plus.
function deterministicProposals() {
  const { min, rows } = learningPatterns(); const out = [];
  const TXT = { Titre: 'Reprendre l\'intitulé exact de l\'offre comme titre du CV', Design: 'Proposer un autre design que celui choisi automatiquement', Couleur: 'Proposer une autre palette par défaut',
    Photo: 'Revoir l\'usage de la photo (mode par défaut)', ATS: 'Privilégier la mise en page ATS Hybrid', Accroche: 'Ouvrir l\'accroche par la preuve chiffrée la plus forte',
    Expérience: 'Revoir l\'ordre des expériences mises en avant', Compétence: 'Placer d\'abord les compétences demandées par l\'offre', Personnalisation: 'Reprendre davantage de termes prouvés de l\'offre' };
  for (const r of rows) if (r.neg >= min && TXT[r.reason]) out.push({ rule_text: `${TXT[r.reason]} (secteur ${E.sector(r.sector).name || r.sector}).`, sector: r.sector, context: r.reason, n_cases: r.n, confidence: r.neg / r.n >= 0.8 ? 'MEDIUM' : 'LOW', source: 'déterministe' });
  return out;
}
V.learning = () => {
  const fb = S.feedback; const { min, rows } = learningPatterns();
  const props = (S.rules.proposals || []).filter((r) => r.status === 'proposed'); const acc = S.rules.accepted || [];
  const stage = acc.length ? 5 : props.length ? 2 : rows.length ? 1 : fb.length ? 0 : -1;
  const imp = S.jobImport;
  return `<div class="page"><div class="page-head"><div class="stack"><span class="eyebrow">Learning</span><h1 class="title">PAI apprend, <em>tu décides</em></h1>
    <p class="lede">Tes avis deviennent des règles candidates. Chaque règle montre sa taille d'échantillon ; aucune n'est appliquée sans ton accord, et chaque acceptation crée une nouvelle version des règles.</p></div></div>
    <div class="flow">${LEARN_FLOW.map((f, i) => `${i ? '<i></i>' : ''}<span class="${i <= stage ? 'on' : ''}">${f}</span>`).join('')}</div>
    <div class="grid g4 stats"><div class="stat"><span class="v">${fb.length}</span><span class="l">Avis observés</span></div><div class="stat"><span class="v">${rows.filter((r) => r.n >= min).length}</span><span class="l">Motifs au-dessus du seuil (${min})</span></div>
      <div class="stat"><span class="v">${props.length}</span><span class="l">Règles proposées</span></div><div class="stat"><span class="v">v${S.rules.rules_version || 0}</span><span class="l">Version des règles · ${nb(acc.length, 'acceptée', 'acceptées')}</span></div></div>
    <div class="split"><div class="stack">
      <div class="card"><h3 class="h3">Observe · Analyze</h3>${rows.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Secteur</th><th>Raison</th><th class="num">n</th><th class="num">👍</th><th class="num">👎</th><th>Statut</th></tr></thead><tbody>
        ${rows.slice(0, 14).map((r) => `<tr><td>${esc(E.sector(r.sector).name || r.sector)}</td><td>${esc(r.reason)}</td><td class="num">${r.n}</td><td class="num">${r.pos}</td><td class="num">${r.neg}</td><td>${r.n >= min ? chip('OBSERVED', 'accent') : chip('INSUFFICIENT DATA', 'warn')}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted small" style="margin:12px 0 0">Aucun avis pour l\'instant : donne ton verdict dans le Training Lab.</p>'}
        <p class="hint" style="margin:10px 0 0">Corrélation ≠ causalité. Conclure sur de vrais résultats (entretiens obtenus) demande au moins ${((D.scoring || {}).learning || {}).min_comparable_applications_for_conclusion || 20} candidatures comparables.</p></div>
      <div class="card stack"><div class="card-head"><h3 class="h3">Propose rule</h3><div class="row"><button class="btn sm" data-act="propose-det" ${rows.length ? '' : 'disabled'}>Motifs répétés</button><button class="btn sm primary" data-act="propose-rules" ${AI.ok() && fb.length ? '' : 'disabled'}>${icon('i-spark')} Analyse IA</button></div></div>
        ${props.length ? props.map((r) => `<div class="card flat stack tight"><b>${esc(r.rule_text)}</b><span class="muted small">${esc([E.sector(r.sector).name || r.sector, r.context].filter(Boolean).join(' · '))} · n = ${esc(r.n_cases)} · confiance ${esc(r.confidence)} · ${esc(r.source || 'IA')}</span>
          <span class="small"><b>Benchmark :</b> ${Number(r.n_cases) >= 20 ? 'échantillon suffisant pour un test A/B en arène' : `non mesurable (n = ${esc(r.n_cases)} < 20) : la règle reste une hypothèse`}</span>
          <div class="row"><button class="btn sm primary" data-act="rule-accept" data-arg="${esc(r.id)}">${icon('i-check')} Accepter</button><button class="btn sm" data-act="rule-refuse" data-arg="${esc(r.id)}">Refuser</button></div></div>`).join('') : '<p class="muted small" style="margin:0">Aucune proposition en attente.</p>'}</div>
    </div><div class="stack">
      <div class="card"><h3 class="h3">Règles acceptées · v${S.rules.rules_version || 0}</h3>${acc.length ? `<div class="list">${acc.map((r) => `<div class="item"><span class="grow small">${esc(r.rule_text)}<span class="s">acceptée le ${fmtDate(r.accepted_at || r.created_at)}</span></span><button class="btn sm ghost danger" data-act="rule-remove" data-arg="${esc(r.id)}">Retirer</button></div>`).join('')}</div>` : '<p class="muted small" style="margin:12px 0 0">Aucune : PAI suit ses règles de base.</p>'}</div>
      <div class="card stack"><div class="card-head"><h3 class="h3">Learn from JobAgent</h3><span class="chip">lecture seule</span></div>
        <p class="small" style="margin:0">Importe un export (JSON, TXT, MD) de ton JobAgent. PAI le lit dans ton navigateur, ne modifie jamais JobAgent et n'accède ni à sa base ni à ses ports. Chaque élément choisi entre dans ton profil en « À vérifier ».</p>
        <div class="row"><label class="btn" for="f-ja">${icon('i-upload')} Importer un export</label><input id="f-ja" type="file" accept=".json,.txt,.md,application/json,text/plain" class="sr" data-change="ja-file"></div>
        ${imp ? `<div class="stack"><b class="small">${esc(imp.name)} · ${nb(imp.items.length, 'élément', 'éléments')}</b><div class="list ja-list">${imp.items.map((it, i) => `<div class="item" style="align-items:flex-start"><input type="checkbox" id="ja-${i}" ${it.pick ? 'checked' : ''} data-change="ja-pick" data-arg="${i}" aria-label="Sélectionner">
          <span class="grow"><span class="small">${esc(it.text)}</span><span class="s mono">${esc(it.path)}</span></span>
          <select class="select" style="width:auto" data-change="ja-kind" data-arg="${i}" aria-label="Type">${KIND_ORDER.filter((k) => !['identity', 'contact'].includes(k)).map((k) => `<option value="${k}" ${it.kind === k ? 'selected' : ''}>${KIND_LABEL[k]}</option>`).join('')}</select></div>`).join('')}</div>
          <div class="row"><button class="btn primary" data-act="ja-accept">Ajouter la sélection (À vérifier)</button><button class="btn" data-act="ja-cancel">Annuler</button></div></div>` : ''}
        ${S.jobagent.length ? `<div class="list">${S.jobagent.slice(0, 5).map((j) => `<div class="item"><span class="grow"><span class="t">${esc(j.name)}</span><span class="s">${nb(j.accepted, 'accepté', 'acceptés')} sur ${j.total} · empreinte ${esc(j.hash)}</span></span><span class="s">${fmtDate(j.created_at)}</span></div>`).join('')}</div>` : ''}</div>
    </div></div></div>`;
};

function parseJobAgent(name, text) {
  const items = [];
  const push = (path, val) => { const t = String(val).trim(); if (t.length >= 3 && t.length <= 300 && !/^https?:\/\//.test(t) && !/^[\d\s.:-]+$/.test(t)) items.push({ path, text: t, kind: guessKind(`${path} ${t}`), pick: false }); };
  try {
    const walk = (v, path) => { if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${path}[${i}]`)); else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => walk(x, path ? `${path}.${k}` : k)); else if (typeof v === 'string') push(path, v); };
    walk(JSON.parse(text), '');
  } catch (e) { text.split('\n').map((l) => l.replace(/^[\s\-*#•]+/, '').trim()).forEach((l, i) => push(`ligne ${i + 1}`, l)); }
  return { name, hash: E.hash(text).slice(0, 7), items: items.slice(0, 300) };
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
