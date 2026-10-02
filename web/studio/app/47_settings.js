// ─── Réglages : fournisseur IA (interchangeable), thème, compte, données ; Versions ──
const PROVIDERS = ['local', 'null', 'claude', 'gemini', 'mistral', 'openai'];
const PROVIDER_HINT = { claude: 'Anthropic · clé API payante', gemini: 'Google AI Studio · clé API', mistral: 'La Plateforme · clé API', openai: 'OpenAI ou API compatible · clé + URL', local: 'Ollama sur ton serveur · aucun coût, aucune clé', null: 'Aucun appel IA : tout reste déterministe' };
// Mode IA affiché en clair : SANS IA (voies déterministes), IA LOCALE (gratuite, sur ton serveur), IA EXTERNE (optionnelle).
const MODE_LABEL = { REMOTE: 'IA externe', LOCAL: 'IA locale', DEGRADED: 'Sans IA' };
const MODE_TXT = { REMOTE: 'IA externe optionnelle (fournisseur cloud, avec ta clé)', LOCAL: 'IA locale gratuite, sur ton serveur', DEGRADED: 'Sans IA : chaque étape suit sa voie déterministe, tout reste vrai' };
const modeBadge = (m, compact) => `<span class="mode-badge ${m === 'DEGRADED' ? 'warn' : m === 'LOCAL' ? 'gold' : ''}" title="${esc(MODE_TXT[m] || '')}"><span class="dot"></span>${compact ? '' : 'Mode · '}${esc((MODE_LABEL[m] || m).toUpperCase())}${compact && m !== 'DEGRADED' ? ` · ${esc(AI.short())}` : ''}</span>`;

function aiProviderCard() {
  if (!SERVER) {
    const t = S.server.aiTest.claude;
    return `<div class="card stack"><div class="card-head"><h3 class="h3">Fournisseur IA</h3>${modeBadge(AI.mode())}</div>
      <p class="small" style="margin:0">PAI n'est pas Claude : le moteur, les règles de vérité et le validateur sont à toi ; l'IA n'est qu'un rédacteur interchangeable. Dans claude.ai, PAI utilise Claude via ton compte. Sur ton serveur PAI, tu choisis : Claude, Gemini, Mistral, OpenAI, une IA locale, ou aucune.</p>
      <div class="providers">${PROVIDERS.map((id) => `<div class="provider ${id === 'claude' ? 'on' : 'off'}"><div class="row between"><div class="stack tight"><b>${esc(PROVIDER_LABEL[id])}</b><span class="hint">${id === 'claude' ? 'Actif ici (capacité claude.ai)' : 'Réglable sur ton serveur PAI'}</span></div>${id === 'claude' ? chip(S.ai === 'denied' ? 'Refusé' : S.caps.sample ? 'Disponible' : 'Indisponible', S.ai === 'denied' || !S.caps.sample ? 'warn' : 'good') : ''}</div></div>`).join('')}</div>
      <div class="row"><button class="btn primary" data-act="ai-test" data-arg="claude" ${S.caps.sample ? '' : 'disabled'}>${icon('i-plug')} Tester la connexion</button>${t ? testChip(t) : ''}</div></div>`;
  }
  const st = S.server.ai;
  if (!S.server.aiLoaded) { Srv.loadAi(); return `<div class="card"><h3 class="h3">Fournisseur IA</h3><p class="muted small live-dots">Chargement</p></div>`; }
  if (!st) return `<div class="card stack"><h3 class="h3">Fournisseur IA</h3><div class="notice warn">${icon('i-alert')}<span>Réglages IA illisibles (serveur plus ancien ou droits insuffisants).</span></div></div>`;
  const open = S.server.aiOpen || st.active;
  const order = PROVIDERS.filter((id) => st.providers.some((x) => x.id === id)).concat(st.providers.map((x) => x.id).filter((id) => !PROVIDERS.includes(id)));
  const providers = order.map((id) => st.providers.find((x) => x.id === id));
  const prof = st.profile || 'balanced';
  return `<div class="card stack"><div class="card-head"><h3 class="h3">Fournisseur IA</h3>${modeBadge(st.mode)}</div>
    <p class="small" style="margin:0">PAI fonctionne entièrement sans IA. L'IA locale (Ollama, gratuite) améliore la rédaction ; un fournisseur externe reste optionnel. Le score, les preuves et la factualité ne passent jamais par une IA. Les clés sont chiffrées sur ton serveur et ne sont jamais réaffichées (seulement un indice).</p>
    <div class="field"><span class="label">Usage de l'IA</span><div class="seg" role="group" aria-label="Profil d'usage de l'IA">${[['eco', 'Économe'], ['balanced', 'Équilibré'], ['quality', 'Qualité']].map(([k, l]) => `<button data-act="ai-profile" data-arg="${k}" aria-pressed="${prof === k}">${l}</button>`).join('')}</div>
      <span class="hint">Économe : l'IA seulement pour la lettre et l'extraction. Équilibré : aussi la stratégie et les reformulations. Qualité : toutes les étapes rédactionnelles.</span></div>
    <div class="providers">${providers.map((pv) => { const active = pv.id === st.active; const t = S.server.aiTest[pv.id];
      return `<div class="provider ${active ? 'on' : ''}"><div class="row between"><div class="stack tight"><b>${esc(pv.label || PROVIDER_LABEL[pv.id] || pv.id)}</b><span class="hint">${esc(PROVIDER_HINT[pv.id] || '')}${pv.model ? ` · ${esc(pv.model)}` : ''}${pv.key_hint ? ` · clé ${esc(pv.key_hint)}` : ''}</span></div>
        <div class="row" style="gap:6px">${active ? chip('Actif', 'good') : ''}${pv.id !== 'null' ? chip(pv.configured ? 'Configuré' : 'Non configuré', pv.configured ? 'accent' : 'warn') : ''}</div></div>
        <div class="row">${active ? '' : `<button class="btn sm" data-act="ai-activate" data-arg="${esc(pv.id)}">Activer</button>`}${pv.id !== 'null' ? `<button class="btn sm ghost" data-act="ai-open" data-arg="${esc(pv.id)}">${open === pv.id ? 'Fermer' : 'Configurer'}</button><button class="btn sm ghost" data-act="ai-test" data-arg="${esc(pv.id)}">${icon('i-plug')} Tester la connexion</button>` : ''}${t ? testChip(t) : ''}</div>
        ${open === pv.id && pv.id !== 'null' ? `<div class="grid g2 provider-form">${['claude', 'gemini', 'mistral', 'openai'].includes(pv.id) ? `<div class="field"><label for="ai-key-${pv.id}">Clé d'API ${pv.key_hint ? '(laisser vide = inchangée)' : ''}</label><input id="ai-key-${pv.id}" class="input" type="password" autocomplete="off" spellcheck="false" placeholder="${pv.key_hint ? esc(pv.key_hint) : 'colle ta clé'}"></div>` : ''}
          <div class="field"><label for="ai-model-${pv.id}">${pv.id === 'local' ? 'Grand modèle (vide = choix mesuré sur ta machine)' : 'Modèle (vide = défaut)'}</label><input id="ai-model-${pv.id}" class="input" value="${esc(pv.source === 'ui' ? pv.model : '')}" placeholder="${esc(pv.model || '')}"></div>
          ${pv.id === 'local' ? `<div class="field"><label for="ai-small-${pv.id}">Petit modèle (vide = choix mesuré)</label><input id="ai-small-${pv.id}" class="input" value="${esc(pv.source === 'ui' ? pv.model_small || '' : '')}" placeholder="${esc(pv.model_small || '')}"></div>` : ''}
          ${['openai', 'local'].includes(pv.id) ? `<div class="field"><label for="ai-url-${pv.id}">URL de base</label><input id="ai-url-${pv.id}" class="input" value="${esc(pv.base_url || '')}" placeholder="${pv.id === 'local' ? 'http://ollama:11434' : 'https://api.openai.com/v1'}"></div>` : ''}
          <div class="row" style="grid-column:1/-1"><button class="btn sm primary" data-act="ai-save" data-arg="${esc(pv.id)}">Enregistrer</button>${pv.key_hint ? `<button class="btn sm ghost danger" data-act="ai-clear" data-arg="${esc(pv.id)}">Effacer la clé</button>` : ''}</div></div>` : ''}</div>`; }).join('')}</div></div>`;
}
const testChip = (t) => (t.busy ? '<span class="chip accent live"><span class="dot"></span>Test…</span>' : t.ok ? chip(`OK · ${fmtMs(t.latency_ms || 0)}${t.model ? ` · ${t.model}` : ''}`, 'good') : `<span class="chip bad" title="${esc(t.error || '')}">Échec : ${esc(String(t.error || 'erreur').slice(0, 80))}</span>`);

V.reglages = () => {
  const P = Pp(); const lim = S.aiLimits;
  const csrf = ((document.querySelector('meta[name="pai-csrf"]') || {}).content) || '';
  const account = SERVER ? `<div class="card stack"><h3 class="h3">Compte</h3><p class="small muted" style="margin:0">Changer le mot de passe révoque tes autres sessions. La déconnexion est effective côté serveur.</p>
      <div class="row"><a class="btn" href="/change-password">Changer le mot de passe</a><form method="post" action="/logout" style="margin:0"><input type="hidden" name="csrf" value="${esc(csrf)}"><button class="btn danger" type="submit">${icon('i-logout')} Se déconnecter</button></form></div></div>` : '';
  const todo = [SERVER ? 'Une clé d\'API pour le fournisseur IA de ton serveur (ou une IA locale), à saisir ci-contre.' : 'Rien pour l\'IA ici : Claude passe par ton compte claude.ai.',
    'Pour publier une mise à jour sur ton serveur Oracle : les secrets de déploiement GitHub (voir docs/DEPLOIEMENT_AUTO.md).', 'Un export JSON du JobAgent (Learning → Learn from JobAgent).',
    'Tes anciens CV et lettres en PDF (Configuration → Documents) pour le benchmark sur tes vrais documents.', 'De vraies offres : chaque pack REAL compte plus que tous les tests SYNTHETIC.'];
  return `<div class="page"><div class="page-head"><div class="stack"><span class="kicker">Compte · IA · données</span><h1 class="title">Réglages</h1></div></div>
    <div class="split"><div class="stack">${aiProviderCard()}
      <div class="card stack"><h3 class="h3">Apparence</h3><div class="seg" role="group" aria-label="Thème">${[['system', 'Système'], ['dark', 'Sombre'], ['light', 'Clair']].map(([k, l]) => `<button data-act="theme" data-arg="${k}" aria-pressed="${S.themeChoice === k}">${l}</button>`).join('')}</div>
        <span class="hint">Les animations se coupent d'elles-mêmes si ton système demande moins de mouvement.</span></div>
      <div class="card"><details class="more"><summary>Détails techniques : niveau de modèle par tâche</summary><div class="table-wrap" style="margin-top:10px"><table class="t"><tbody>${Object.entries(D.models.artifact_tiers || {}).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div>
        <p class="hint" style="margin:8px 0 0">quick : extraction · default : rédaction · complex : stratégie, critique, jugement.</p></details></div></div>
    <div class="stack">${account}
      <div class="card"><h3 class="h3">État</h3><div class="list">
        <div class="item"><span class="grow">IA</span>${modeBadge(AI.mode())}</div>
        <div class="item"><span class="grow">Contrôle visuel du PDF (images)</span>${lim && lim.images ? chip('Oui', 'good') : chip('Non', '')}</div>
        <div class="item"><span class="grow">Stockage privé</span>${S.storage === 'db' ? chip(SERVER ? 'PostgreSQL (serveur PAI)' : 'Base privée claude.ai', 'good') : chip('Mémoire seulement : rien n\'est conservé', 'warn')}</div>
        <div class="item"><span class="grow">Téléchargements</span>${S.caps.downloads ? chip('Actifs', 'good') : chip('Indisponibles', 'warn')}</div>
        ${SERVER && S.server.status ? `<div class="item"><span class="grow">Serveur</span>${chip(`moteur ${S.server.status.engine_v} · base ${S.server.status.db}`, S.server.status.db === 'ok' ? 'good' : 'bad')}</div>` : ''}</div></div>
      <div class="card stack"><h3 class="h3">Données</h3><p class="small muted" style="margin:0">Export complet (profil, packs, avis, votes, règles, préférences ; photo exclue) au format JSON.</p>
        <div class="row"><button class="btn" data-act="backup" ${P ? '' : 'disabled'}>${icon('i-download')} Tout exporter</button></div>
        ${S.packs.length ? `<details class="more"><summary>Supprimer des packs (${S.packs.length})</summary><div class="list">${S.packs.map((p) => `<div class="item"><span class="grow small">${esc(p.analysis.job_title)} · ${fmtDate(p.created_at)}</span>${S.confirmDel === p.id ? `<button class="btn sm danger" data-act="pack-delete" data-arg="${esc(p.id)}">Confirmer</button><button class="btn sm ghost" data-act="pack-delete-cancel">Non</button>` : `<button class="btn sm ghost danger" data-act="pack-delete-ask" data-arg="${esc(p.id)}">Supprimer</button>`}</div>`).join('')}</div></details>` : ''}</div>
      <div class="card"><h3 class="h3">À fournir pour aller plus loin</h3><ul class="why-list" style="margin-top:12px">${todo.map((t) => `<li><span>${esc(t)}</span></li>`).join('')}</ul></div></div></div></div>`;
};

V.versions = () => `<div class="page"><div class="page-head"><div class="stack"><span class="eyebrow">Versions</span><h1 class="title">Tout est <em>versionné</em></h1><p class="lede">Chaque pack fige l'offre, le profil, le moteur, les prompts, les règles et le design utilisés : tu peux toujours savoir pourquoi un document est ce qu'il est.</p></div></div>
  <div class="grid g4 stats"><div class="stat"><span class="v mono-v">${esc(D.version.engine)}</span><span class="l">Moteur</span></div><div class="stat"><span class="v mono-v">${esc(D.version.rules)}</span><span class="l">Règles de base</span></div><div class="stat"><span class="v mono-v">${esc(D.version.prompts)}</span><span class="l">Prompts</span></div><div class="stat"><span class="v mono-v">v${S.rules.rules_version || 0}</span><span class="l">Règles apprises</span></div></div>
  <div class="split"><div class="card"><h3 class="h3">Versions validées du profil</h3>${S.profileVersions.length ? `<div class="list">${S.profileVersions.map((v) => `<div class="item"><span class="grow"><span class="t">v${v.version}</span><span class="s">${esc(v.tag || '')} · ${(v.facts || []).length} faits</span></span><span class="s">${fmtDate(v.validated_at)}</span></div>`).join('')}</div>` : '<p class="muted small" style="margin:12px 0 0">Aucune version validée pour l\'instant.</p>'}</div>
  <div class="card"><h3 class="h3">Designs</h3><div class="table-wrap"><table class="t"><tbody>${DS.FAMILIES.map((f) => `<tr><td>${esc(DESIGN_NAME(f))}</td><td class="mono">${esc(f)}</td><td class="num mono">v${esc((D.designs[f] || {}).version || 1)}</td><td>${chip(`ATS ${(D.designs[f] || {}).ats_level || '—'}`, '')}</td></tr>`).join('')}</tbody></table></div></div></div>
  <div class="card"><h3 class="h3">Packs</h3><div class="table-wrap"><table class="t"><thead><tr><th>Pack</th><th>profile_v</th><th>cv_v</th><th>letter_v</th><th>design_v</th><th>engine_v</th><th>prompt_v</th><th>rules_v</th></tr></thead><tbody>
  ${S.packs.map((p) => `<tr><td>${esc(p.analysis.job_title)}</td>${['profile_v', 'cv_v', 'letter_v', 'design_v', 'engine_v', 'prompt_v', 'rules_v'].map((k) => `<td class="mono">${esc(p.versions[k] || '—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>
  <div class="card"><h3 class="h3">Prompts</h3><div class="table-wrap"><table class="t"><tbody>${Object.entries(D.prompts).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td class="num mono">v${v.version}</td></tr>`).join('')}</tbody></table></div></div></div>`;
