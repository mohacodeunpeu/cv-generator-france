// ─── Démarrage ───────────────────────────────────────────────────────────────
async function boot() {
  applyTheme(); renderShell(); PDF.init();
  const h = location.hash.slice(1); const v = ALIASES[h] || h; if (v && V[v]) S.view = v;
  render();
  const use = (n) => (window.claude && typeof window.claude.use === 'function' ? window.claude.use(n).catch(() => null) : Promise.resolve(null));
  const [db, sample, downloads, user] = await Promise.all([use('db'), use('sample'), use('downloads'), use('user')]);
  S.caps = { db, sample, downloads, user };
  S.ai = sample ? 'ready' : 'off';
  if (sample && sample.limits) sample.limits().then((l) => { S.aiLimits = l; render(); }).catch(() => {});
  if (db) Store.subscribe(db); else Store.memory();
  if (SERVER) { Srv.loadStatus(); setInterval(() => { if (document.visibilityState === 'visible') Srv.loadStatus(); }, 60000); }
  S.ready = true; render();
}
window.__PAI_DEBUG__ = { PDF, E, S, DS, Photo };
boot();
