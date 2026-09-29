// ─── Benchmark et arène à l'aveugle : chaque donnée porte son étiquette REAL / LEGACY / SYNTHETIC ──
const dsTag = (k) => `<span class="tag-ds ${k.toLowerCase()}">${k}</span>`;
V.benchmark = () => {
  const pair = S.arenaPair; const votes = S.arena; const judged = votes.filter((v) => v.judge && v.choice);
  const agree = judged.filter((v) => v.judge.winner === v.choice).length; const b = S.bench; const src = arenaSources();
  const realPacks = S.packs.filter((p) => p.offer && !p.offer.synthetic).length;
  return `<div class="page"><div class="page-head"><div class="stack"><span class="eyebrow">Benchmark</span><h1 class="title">Mesurer, <em>sans se raconter d'histoires</em></h1>
    <p class="lede">Deux CV pour la même offre, sans étiquette : tu choisis, tu dis pourquoi, puis l'origine est révélée. Chaque donnée est étiquetée ${dsTag('REAL')} ${dsTag('LEGACY')} ${dsTag('SYNTHETIC')}.</p></div></div>
    <div class="notice">${icon('i-shield')}<span><b>Règle de preuve :</b> les offres ${dsTag('SYNTHETIC')} testent la robustesse du moteur ; elles ne prouvent jamais une performance réelle. Seuls les packs ${dsTag('REAL')} (offres réelles) et tes votes comptent comme preuve.</span></div>
    <div class="grid g4 stats"><div class="stat"><span class="v">${realPacks}</span><span class="l">Packs sur offres réelles ${dsTag('REAL')}</span></div><div class="stat"><span class="v">${votes.length}</span><span class="l">Votes à l'aveugle</span></div>
      <div class="stat"><span class="v">${judged.length ? `${Math.round((100 * agree) / judged.length)}<small> %</small>` : '—'}</span><span class="l">Accord juge IA ↔ toi (${judged.length})</span></div>
      <div class="stat"><span class="v">${b ? pct(b.new_avg) : '—'}</span><span class="l">Score moteur ${b ? esc(b.engine_v) : ''} ${b ? dsTag(b.synthetic ? 'SYNTHETIC' : 'REAL') : ''}</span></div></div>
    <div class="card stack">${pair ? arenaPairHtml(pair) : `<div class="row between"><span class="muted">${nb(src.length, 'paire', 'paires')} : versions d'un même pack ${dsTag('REAL')} et ancien générateur ${dsTag('LEGACY')} ↔ PAI sur offres ${dsTag('SYNTHETIC')}.</span><button class="btn primary" data-act="arena-new" ${src.length ? '' : 'disabled'}>${icon('i-compare')} Nouvelle paire</button></div>`}</div>
    ${b ? benchTable(b) : '<div class="card muted">Aucun résultat de benchmark importé.</div>'}
    ${votes.length ? `<div class="card"><h3 class="h3">Historique des votes</h3><div class="list">${votes.slice(0, 20).map((v) => `<div class="item"><span class="grow"><span class="t">${esc(v.title || '')} ${dsTag(v.kind === 'legacy' ? 'LEGACY' : v.synthetic ? 'SYNTHETIC' : 'REAL')}</span><span class="s">Choix : ${esc(v.choice_label || v.choice)} · ${esc(v.reason || '')}${v.judge ? ` · juge : ${esc(v.judge.winner_label || v.judge.winner)}` : ''}</span></span><span class="s">${fmtDate(v.created_at)}</span></div>`).join('')}</div></div>` : ''}</div>`;
};
function arenaSources() {
  const out = [];
  for (const p of S.packs) if (p.cvs && p.cvs.length > 1) for (let i = 1; i < p.cvs.length; i++) out.push({ kind: 'versions', synthetic: !!(p.offer && p.offer.synthetic), id: `${p.id}:0:${i}`, title: `${p.analysis.job_title} · ${disp(p.analysis.company, 'company')}`, offer: p.analysis.job_title,
    a: { label: p.cvs[0].label || 'V1', text: E.cvPlainText(p.cvs[0].doc).replace(/\[[^\]]+\] /g, '') }, b: { label: p.cvs[i].label || `V${i + 1}`, text: E.cvPlainText(p.cvs[i].doc).replace(/\[[^\]]+\] /g, '') } });
  for (const bp of S.benchPairs || []) out.push({ kind: 'legacy', synthetic: true, id: bp.id, title: bp.title, offer: bp.title, a: { label: 'Ancien générateur (LEGACY)', text: bp.legacy_text }, b: { label: 'PAI (moteur déterministe)', text: bp.pai_text } });
  return out;
}
function arenaPairHtml(pair) {
  const X = pair.flip ? pair.b : pair.a; const Y = pair.flip ? pair.a : pair.b;
  const box = (k, d) => `<div class="card flat stack tight"><h3 class="h3">CV « ${k} »</h3><pre class="arena-text">${esc(d.text)}</pre></div>`;
  return `<div class="row between"><b>${esc(pair.title)} ${dsTag(pair.kind === 'legacy' ? 'LEGACY' : pair.synthetic ? 'SYNTHETIC' : 'REAL')}</b>${pair.revealed ? chip(`X = ${X.label} · Y = ${Y.label}`, 'accent') : chip('À l\'aveugle')}</div>
    <div class="grid g2">${box('X', X)}${box('Y', Y)}</div>
    ${pair.revealed ? `<div class="row"><button class="btn" data-act="arena-judge" ${AI.ok() ? '' : 'disabled'}>Avis du juge IA (dans les 2 ordres)</button><button class="btn primary" data-act="arena-new">Paire suivante</button>${pair.judge ? chip(`Juge : ${pair.judge.winner_label}`, 'accent') : ''}</div>`
    : `<div class="field"><label for="arena-reason">Pourquoi ?</label><input id="arena-reason" class="input" placeholder="Plus clair, plus concret, mieux ciblé…"></div>
      <div class="row"><button class="btn primary" data-act="arena-vote" data-arg="X">X est meilleur</button><button class="btn primary" data-act="arena-vote" data-arg="Y">Y est meilleur</button><button class="btn" data-act="arena-vote" data-arg="TIE">Égalité</button></div>`}`;
}
function benchTable(b) {
  return `<div class="card"><div class="card-head"><h3 class="h3">Benchmark déterministe · ${esc(b.n)} offres · ${fmtDate(b.created_at)}</h3><span>${dsTag(b.synthetic ? 'SYNTHETIC' : 'REAL')} ${dsTag('LEGACY')}</span></div>
    <div class="table-wrap"><table class="t"><thead><tr><th>Offre</th><th class="num">Ancien</th><th class="num">PAI</th><th>Factualité (ancien / PAI)</th><th>Mots-clés couverts (ancien / PAI)</th></tr></thead><tbody>
    ${(b.rows || []).map((r) => `<tr><td>${esc(r.title)}</td><td class="num">${pct(r.legacy_score)}</td><td class="num"><b>${pct(r.pai_score)}</b></td><td>${pct(r.legacy_factuality)} / ${pct(r.pai_factuality)} %${r.legacy_forbidden ? ` · <span style="color:var(--bad)">${nb(r.legacy_forbidden, 'fait interdit', 'faits interdits')} chez l'ancien</span>` : ''}</td><td>${pct(r.legacy_kw)} / ${pct(r.pai_kw)} %</td></tr>`).join('')}</tbody></table></div>
    <p class="hint" style="margin:10px 0 0">${esc(b.conclusion || '')} ${b.synthetic ? 'Offres fictives : indication de robustesse, pas une preuve de performance réelle.' : ''}</p></div>`;
}
