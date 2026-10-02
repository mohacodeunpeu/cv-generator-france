// ─── État du système et utilisation de l'IA ──────────────────────────────────
// Serveur PAI : /api/system/status et /api/ai/usage. Dans claude.ai : ce que la page sait d'elle-même (rien d'inventé).
const SYS_ICON = { pai: 'i-spark', ats: 'i-target', api: 'i-plug', database: 'i-stack', ai: 'i-bolt', local_model: 'i-bolt', cache: 'i-history', cloudflare: 'i-shield', jobagent: 'i-link' };
const Sys = {
  async load() {
    if (!SERVER || S.server.sysBusy) return;
    S.server.sysBusy = true; render();
    try {
      const [st, us] = await Promise.all([Srv.req('GET', '/api/system/status'), Srv.req('GET', '/api/ai/usage?days=30')]);
      S.server.sys = st; S.server.usage = us; S.server.sysError = null;
    } catch (e) { S.server.sysError = (e && e.message) || String(e); }
    S.server.sysBusy = false; S.server.sysAt = nowIso(); render();
  },
};
function browserStatus() {
  const engineOk = (() => { try { return ATS.classifyRequirement('Anglais courant requis') === 'MUST'; } catch (e) { return false; } })();
  return { status: 'WARNING', items: [
    { id: 'pai', label: 'PAI', status: 'OK', detail: `moteur ${D.version.engine} (PAI Studio)` },
    { id: 'ats', label: 'Moteur ATS', status: engineOk ? 'OK' : 'ERROR', detail: engineOk ? 'règles chargées, contrôle de cohérence réussi' : 'contrôle échoué' },
    { id: 'database', label: 'Stockage', status: S.storage === 'db' ? 'OK' : 'WARNING', detail: S.storage === 'db' ? 'base privée de la page' : 'mémoire seulement : rien n\'est conservé' },
    { id: 'ai', label: 'IA', status: AI.ok() ? 'OK' : 'WARNING', detail: AI.ok() ? `${AI.label()} — optionnelle` : 'sans IA : tout fonctionne par les voies déterministes' },
    { id: 'pdf', label: 'Relecture PDF', status: window.pdfjsLib ? 'OK' : 'WARNING', detail: window.pdfjsLib ? 'pdf.js chargé : le PDF réel est relu' : 'pdf.js indisponible' },
    { id: 'api', label: 'Serveur PAI', status: 'WARNING', detail: 'non connecté ici : base PostgreSQL, IA locale, Cloudflare et JobAgent se lisent sur ton serveur PAI' },
  ] };
}
V.statut = () => {
  if (SERVER && !S.server.sys && !S.server.sysBusy && !S.server.sysError) Sys.load();
  const st = SERVER ? S.server.sys : browserStatus();
  const items = st ? st.items : [];
  const worst = st ? st.status : null;
  const head = `<div class="page-head"><div class="stack"><span class="kicker">PAI · ${SERVER ? 'serveur' : 'PAI Studio'}</span><h1 class="title">État du <em>système</em></h1>
    <p class="lede">Chaque brique, son état et la raison en une phrase. PAI reste utilisable sans IA, sans JobAgent et sans cache : seul un problème de base de données bloque.</p></div>
    ${SERVER ? `<button class="btn" data-act="sys-refresh" ${S.server.sysBusy ? 'disabled' : ''}>${icon('i-refresh')} ${S.server.sysBusy ? 'Vérification…' : 'Vérifier'}</button>` : ''}</div>`;
  if (SERVER && !st) return `<div class="page">${head}${S.server.sysError ? `<div class="notice bad">${icon('i-alert')}<span>État illisible : ${esc(S.server.sysError)}</span></div>` : '<p class="muted live-dots">Vérification</p>'}</div>`;
  const tiles = items.map((it, i) => `<div class="sys-item ${({ OK: 'good', WARNING: 'warn', ERROR: 'bad' })[it.status] || ''}" data-anim="${Math.min(5, i + 1)}">
      <span class="ic">${icon(SYS_ICON[it.id] || 'i-info')}</span><span class="stack tight grow"><span class="row between"><b>${esc(it.label)}</b>${stateChip(it.status)}</span><span class="small muted">${esc(it.detail)}</span></span></div>`).join('');
  return `<div class="page">${head}
    <div class="sys-sum">${stateChip(worst)}<span class="small">${worst === 'OK' ? 'Tout fonctionne.' : worst === 'ERROR' ? 'Au moins une brique est en erreur : voir ci-dessous.' : 'PAI fonctionne ; certaines briques optionnelles sont absentes ou à vérifier.'}</span>
      ${st && st.machine ? `<span class="hint">Machine : ${esc(st.machine.arch)}, ${esc(String(st.machine.cpus))} cœurs, ${esc(num(st.machine.ram_gb))} Go de RAM${st.machine.gpu ? ', GPU' : ', sans GPU'}</span>` : ''}</div>
    <div class="sys-grid">${tiles}</div>
    <section class="card" style="margin-top:8px"><div class="card-head"><h3 class="h3">Utilisation de l'IA</h3><span class="hint">${SERVER ? '30 derniers jours, serveur PAI' : 'cette session'}</span></div>${usageHtml()}</section></div>`;
};
function usageHtml() {
  if (!SERVER) {
    const calls = S.calls || [];
    if (!calls.length) return '<p class="muted small" style="margin:0">Aucun appel IA dans cette session : tout a été fait par les voies déterministes.</p>';
    const by = {}; calls.forEach((c) => { const k = c.task; by[k] = by[k] || { n: 0, ms: 0, ok: 0 }; by[k].n++; by[k].ms += c.ms; by[k].ok += c.ok ? 1 : 0; });
    return `<div class="table-wrap"><table class="t"><thead><tr><th>Tâche</th><th class="num">Appels</th><th class="num">Réussis</th><th class="num">Temps</th></tr></thead><tbody>${Object.entries(by).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v.n}</td><td class="num">${v.ok}</td><td class="num">${fmtMs(v.ms)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  const u = S.server.usage;
  if (!u) return '<p class="muted small" style="margin:0">Indisponible.</p>';
  if (!u.total_requests) return `<p class="small" style="margin:0">Aucun appel IA sur la période. ${esc(u.note)}</p>`;
  const tierL = { small: 'petit modèle local', large: 'grand modèle local', external: 'externe', '': '—' };
  return `<div class="grid g4 stats" style="margin-bottom:14px"><div class="stat"><span class="v">${u.total_requests}</span><span class="l">Appels</span></div><div class="stat"><span class="v">${u.cache_hit_rate === null ? '—' : `${u.cache_hit_rate}<small> %</small>`}</span><span class="l">Servis par le cache</span></div>
      <div class="stat"><span class="v">${u.cache_miss}</span><span class="l">Appels réels</span></div><div class="stat"><span class="v">${num(u.cost_eur)}<small> €</small></span><span class="l">Coût</span></div></div>
    <div class="table-wrap"><table class="t"><thead><tr><th>Fournisseur</th><th>Modèle</th><th>Niveau</th><th class="num">Appels</th><th class="num">Cache</th><th class="num">Jetons (entrée / sortie)</th><th class="num">Temps</th><th class="num">Coût</th></tr></thead><tbody>
    ${u.by_model.map((r) => `<tr><td>${esc(PROVIDER_LABEL[r.provider] || r.provider)}</td><td class="mono">${esc(r.model)}</td><td>${esc(tierL[r.tier] || r.tier)}</td><td class="num">${r.requests}</td><td class="num">${r.cache_hit}/${r.requests}</td><td class="num">${r.tokens_in.toLocaleString('fr-FR')} / ${r.tokens_out.toLocaleString('fr-FR')}</td><td class="num">${fmtMs(r.time_ms)}</td><td class="num">${num(r.cost_eur)} €</td></tr>`).join('')}
    </tbody></table></div><p class="hint" style="margin:10px 0 0">${esc(u.note)}</p>`;
}
