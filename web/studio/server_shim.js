/* Mode serveur de PAI Studio : `window.claude.use()` implémenté sur l'API du serveur PAI.
 * db → /v1/store (PostgreSQL), sample → /v1/ai/complete (fournisseur IA du serveur),
 * downloads → téléchargement navigateur classique. Même interface que sur claude.ai.
 */
(function () {
  'use strict';
  const csrf = (document.querySelector('meta[name="pai-csrf"]') || {}).content || '';
  const api = async (method, url, body) => {
    const res = await fetch(url, { method, credentials: 'same-origin', headers: Object.assign({ 'Content-Type': 'application/json' }, method === 'GET' ? {} : { 'X-CSRF-Token': csrf }), body: body ? JSON.stringify(body) : undefined });
    if (res.status === 401) { location.href = '/login'; throw { code: 'session_expired', message: 'Session expirée' }; }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { const d = data.detail || {}; throw { code: d.code || (res.status === 429 ? 'rate_limited' : 'upstream_error'), message: d.message || String(data.detail || res.status), text: d.text }; }
    return data;
  };
  const listeners = new Set();
  const snapDoc = (path, r) => ({ id: path.split('/').pop(), exists: !!r.exists, data: () => r.data || undefined, metadata: { fromCache: false, hasPendingWrites: false } });
  const refresh = async (l) => {
    try {
      if (l.kind === 'doc') l.cb(snapDoc(l.path, await api('GET', `/v1/store/doc?path=${encodeURIComponent(l.path)}`)));
      else {
        const q = new URLSearchParams({ collection: l.path, limit: String(l.opts.limit || 200) });
        if (l.opts.orderBy) { q.set('order_by', l.opts.orderBy[0]); q.set('direction', l.opts.orderBy[1] || 'asc'); }
        const r = await api('GET', `/v1/store/query?${q}`);
        const docs = r.docs.map((d) => ({ id: d.id, exists: true, data: () => d.data, metadata: {} }));
        l.cb({ docs, size: docs.length, empty: !docs.length, docChanges: () => [], metadata: {} });
      }
    } catch (e) { if (l.err) l.err(e); }
  };
  const touch = (path) => { for (const l of listeners) if (l.path === path || path.startsWith(`${l.path}/`)) refresh(l); };
  setInterval(() => { if (document.visibilityState === 'visible') listeners.forEach(refresh); }, 20000);
  const docRef = (path) => ({ id: path.split('/').pop(), path,
    get: async () => snapDoc(path, await api('GET', `/v1/store/doc?path=${encodeURIComponent(path)}`)),
    set: async (data) => { await api('PUT', `/v1/store/doc?path=${encodeURIComponent(path)}`, { data }); touch(path); },
    update: async (data) => { const cur = await api('GET', `/v1/store/doc?path=${encodeURIComponent(path)}`); if (!cur.exists) throw { code: 'invalid_argument', message: 'document absent' }; await api('PUT', `/v1/store/doc?path=${encodeURIComponent(path)}`, { data: Object.assign({}, cur.data, data) }); touch(path); },
    delete: async () => { await api('DELETE', `/v1/store/doc?path=${encodeURIComponent(path)}`); touch(path); },
    onSnapshot: (cb, err) => { const l = { kind: 'doc', path, cb, err }; listeners.add(l); refresh(l); return () => listeners.delete(l); },
    collection: (sub) => collRef(`${path}/${sub}`) });
  const collRef = (path, opts = {}) => ({ path, doc: (id) => docRef(`${path}/${id || Math.random().toString(36).slice(2)}`),
    orderBy: (f, dir) => collRef(path, Object.assign({}, opts, { orderBy: [f, dir || 'asc'] })), limit: (n) => collRef(path, Object.assign({}, opts, { limit: n })),
    where: () => collRef(path, opts),
    onSnapshot: (cb, err) => { const l = { kind: 'query', path, opts, cb, err }; listeners.add(l); refresh(l); return () => listeners.delete(l); },
    add: async (d) => { const r = docRef(`${path}/${Math.random().toString(36).slice(2)}`); await r.set(d); return r; } });
  const db = { doc: docRef, collection: (p) => collRef(p) };
  const toB64 = async (blob) => { const b = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000)); return btoa(s); };
  const sleep = (ms) => new Promise((res) => setTimeout(res, ms));
  // Appel IA en job : chaque requête HTTP reste courte (IA locale lente sur CPU, coupure Cloudflare à 100 s).
  const poll = async (jobId, json, signal) => {
    const t0 = Date.now();
    for (let i = 0; Date.now() - t0 < 15 * 60 * 1000; i++) {
      if (signal && signal.aborted) throw { code: 'cancelled', message: 'Annulé' };
      await sleep(i < 10 ? 1000 : 2000);
      const j = await api('GET', `/v1/jobs/${encodeURIComponent(jobId)}`);
      if (j.status === 'DONE') return json ? j.result.json : j.result.text;
      if (j.status === 'FAILED') { const m = String(j.error || ''); const code = (m.match(/^(?:RuntimeError: )?([a-z_]+):/) || [])[1] || 'upstream_error'; throw { code, message: m.replace(/^(?:RuntimeError: )?[a-z_]+:\s*/, '') }; }
    }
    throw { code: 'upstream_error', message: "L'IA n'a pas répondu à temps" };
  };
  const call = async (input, opts, json) => {
    const body = { tier: opts.modelTier || 'default', json, async: true };
    if (opts.task) body.task = opts.task;
    if (typeof input === 'string') body.prompt = input; else body.turns = input;
    if (opts.images) body.images = await Promise.all([].concat(opts.images).map(toB64));
    const r = await api('POST', '/v1/ai/complete', body);
    if (r.job_id) return poll(r.job_id, json, opts.signal);
    return json ? r.json : r.text;
  };
  const sample = async (input, opts = {}) => { const text = await call(input, opts, false); if (opts.onText) opts.onText({ text, delta: text }); return { text, truncated: false, modelTierApplied: opts.modelTier || 'default' }; };
  sample.json = async (input, opts = {}) => { const data = await call(input, opts, true); if (opts.onText) opts.onText({ text: JSON.stringify(data), delta: '' }); return data; };
  sample.limits = async () => ({ maxPromptBytes: 65536, images: { maxCount: 4, maxInputBytes: 20000000, mediaTypes: ['image/png', 'image/jpeg'] } });
  const downloads = { save: async ({ filename, data }) => {
    const blob = data instanceof Blob ? data : new Blob([data]); const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
    return { status: 'saved' };
  } };
  const user = { isOwner: () => true, canEdit: () => true, can: () => true };
  window.PAI_SERVER = true;
  window.PAI_API = api; // appels directs de l'interface (lecture d'URL, réglages IA, statut)
  window.claude = { use: async (name) => ({ db, sample, downloads, user })[name] || null };
}());
