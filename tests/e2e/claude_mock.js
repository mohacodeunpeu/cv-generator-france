/* Doublure de `window.claude` pour les tests e2e de PAI Studio (hors ligne, déterministe).
 * - db : magasin de documents en mémoire (doc/collection/orderBy/limit/onSnapshot/set)
 * - sample : réponses JSON enregistrées par tâche (fixtures SYNTHETIC, pas de vraie IA)
 *   Contient volontairement des pièges : une ligne « MBA » et un faux chiffre « 40+ leads ».
 * - downloads : capture les fichiers proposés au téléchargement.
 */
(() => {
  const store = new Map();
  const listeners = [];
  const copy = (d) => JSON.parse(JSON.stringify(d));
  const docSnap = (path) => { const d = store.get(path); return { id: path.split('/').pop(), exists: !!d, data: () => (d ? copy(d) : undefined), metadata: { fromCache: false, hasPendingWrites: false } }; };
  const depth = (p) => p.split('/').length;
  const querySnap = (coll, opts) => {
    let docs = [...store.keys()].filter((p) => p.startsWith(`${coll}/`) && depth(p) === depth(coll) + 1).map(docSnap);
    if (opts.orderBy) { const [f, dir] = opts.orderBy; docs.sort((a, b) => { const x = a.data()[f]; const y = b.data()[f]; return (x > y ? 1 : x < y ? -1 : 0) * (dir === 'desc' ? -1 : 1); }); }
    if (opts.limit) docs = docs.slice(0, opts.limit);
    return { docs, size: docs.length, empty: !docs.length, docChanges: () => [], metadata: {} };
  };
  const deliver = (l) => setTimeout(() => l.cb(l.kind === 'doc' ? docSnap(l.path) : querySnap(l.path, l.opts)), 0);
  const notify = () => listeners.forEach(deliver);
  const docRef = (path) => ({ id: path.split('/').pop(), path, get: async () => docSnap(path),
    set: async (d) => { const s = JSON.stringify(d); if (s.length > 256 * 1024) { const e = { code: 'invalid_argument', message: 'document > 256 KiB' }; throw e; } store.set(path, JSON.parse(s)); notify(); },
    update: async (d) => { store.set(path, Object.assign(store.get(path) || {}, copy(d))); notify(); },
    delete: async () => { store.delete(path); notify(); },
    onSnapshot: (cb) => { const l = { kind: 'doc', path, cb }; listeners.push(l); deliver(l); return () => {}; },
    collection: (sub) => collRef(`${path}/${sub}`) });
  const collRef = (path, opts = {}) => ({ path, doc: (id) => docRef(`${path}/${id || Math.random().toString(36).slice(2)}`),
    orderBy: (f, dir) => collRef(path, Object.assign({}, opts, { orderBy: [f, dir || 'asc'] })), limit: (n) => collRef(path, Object.assign({}, opts, { limit: n })),
    where: () => collRef(path, opts), get: async () => querySnap(path, opts),
    onSnapshot: (cb) => { const l = { kind: 'query', path, opts, cb }; listeners.push(l); deliver(l); return () => {}; },
    add: async (d) => { const r = docRef(`${path}/${Math.random().toString(36).slice(2)}`); await r.set(d); return r; } });
  const db = { doc: docRef, collection: (p) => collRef(p) };
  for (const [p, d] of Object.entries(window.__PAI_SEED__ || {})) store.set(p, copy(d));

  const between = (s, a, b) => { const i = s.indexOf(a); if (i < 0) return ''; const j = s.indexOf(b, i + a.length); return s.slice(i + a.length, j < 0 ? undefined : j); };
  const respond = (prompt) => {
    if (prompt.startsWith('Tu es un analyste recrutement')) {
      return { company: 'Acme SaaS', job_title: 'Business Developer Junior', location: 'Paris', country: 'FR', contract: 'CDI', seniority: 'junior',
        missions: ['Prospecter de nouveaux clients PME par téléphone et LinkedIn.', 'Suivre votre pipeline dans HubSpot.'],
        skills: [{ name: 'prospection', priority: 'MUST', evidence: 'Prospecter de nouveaux clients PME' }, { name: 'CRM', priority: 'MUST', evidence: "Maîtrise d'un CRM indispensable." }],
        tools: ['HubSpot'], languages: [{ name: 'Anglais', level: 'courant', priority: 'MUST' }], remote: 'UNKNOWN', business_model: 'B2B',
        recruiter_wants: { explicit: ['Prospection outbound de PME'], inferred: ["Capacité à tenir un volume d'appels (déduit)"] },
        keywords: [{ term: 'prospection', priority: 'REQUIRED' }, { term: 'CRM', priority: 'REQUIRED' }, { term: 'anglais', priority: 'REQUIRED' }, { term: 'HubSpot', priority: 'IMPORTANT' }, { term: 'PME', priority: 'IMPORTANT' }],
        hidden_risks: [], language_of_offer: 'fr' };
    }
    if (prompt.startsWith('Tu es un stratège de candidature')) {
      const best = { title: 'Business Developer Junior', hook: '25+ leads qualifiés/mois', hook_fact_ids: ['exp.alpha.r2'], experiences_up: ['exp.alpha', 'exp.beta'], experiences_down: ['exp.gamma'],
        key_skill_fact_ids: ['tool.hubspot', 'skill.prospection_b2b', 'lang.en'], ats_mode: 'HYBRID', design_profile: 'hybrid_modern', photo_mode: 'HEADER', letter_angle: 'Preuves de prospection chiffrées',
        channel: "Lien de l'offre", risks: ['PME : vocabulaire à ne pas inventer'], next_action: 'Relire et postuler', why: 'Profil prospection B2B prouvé par des chiffres' };
      return { options: [Object.assign({ key: 'A', angle: 'ATS / mots-clés', score: 84 }, best), Object.assign({ key: 'B', angle: 'Récit humain', score: 78 }, best, { title: 'Business Developer' })], comparison: 'A couvre mieux les REQUIRED.', chosen: 'A', best };
    }
    if (prompt.startsWith('Tu es CV ARCHITECT')) {
      return { headline: { text: 'Business Developer Junior', fact_ids: ['target.roles'], offer_terms: ['Business Developer Junior'] },
        summary: [{ text: 'Business Developer B2B : prospection, négociation avec les décideurs et suivi sous HubSpot.', fact_ids: ['exp.alpha.t1', 'exp.alpha.t2', 'exp.alpha.t3'] },
          { text: '40+ leads qualifiés par mois.', fact_ids: ['exp.alpha.r2'] }],
        experiences: [
          { experience_id: 'exp.alpha', bullets: [{ text: '25+ leads qualifiés par mois grâce à LinkedIn Sales Navigator', fact_ids: ['exp.alpha.r2', 'exp.alpha.t3'] },
            { text: 'Portefeuille B2B de 250 K€/mois suivi dans HubSpot', fact_ids: ['exp.alpha.r1', 'exp.alpha.t3'] },
            { text: 'Titulaire d\'un MBA en stratégie commerciale', fact_ids: ['edu.bachelor'] },
            { text: 'Négociation directe avec les décideurs', fact_ids: ['exp.alpha.t2'] }] },
          { experience_id: 'exp.beta', bullets: [{ text: '+12 % vs objectif mensuel auprès d\'une clientèle internationale premium', fact_ids: ['exp.beta.r1', 'exp.beta.r2'] }] },
          { experience_id: 'exp.gamma', bullets: [{ text: 'Participation à la refonte du site client', fact_ids: ['exp.gamma.t1'] }] }],
        skills: [{ group: 'Commercial', items: [{ label: 'Prospection B2B', fact_ids: ['skill.prospection_b2b'] }, { label: 'Négociation', fact_ids: ['exp.alpha.t2'] }] },
          { group: 'Outils', items: [{ label: 'HubSpot', fact_ids: ['tool.hubspot'] }, { label: 'LinkedIn Sales Navigator', fact_ids: ['exp.alpha.t3'] }] }],
        education_ids: ['edu.bachelor', 'edu.unverified'], certification_ids: [], language_ids: ['lang.fr', 'lang.en'], keywords_covered: ['prospection', 'CRM', 'anglais', 'HubSpot'], gaps: [{ keyword: 'PME', why: 'aucun fait' }] };
    }
    if (prompt.startsWith("Des lignes d'un document")) {
      let items = [];
      try { items = JSON.parse(between(prompt, 'LIGNES À CORRIGER (id, texte, raisons du rejet, faits cités) :\n', '\nFAITS AUTORISÉS').trim()); } catch (e) { items = []; }
      return { lines: items.map((it) => {
        if (/MBA/i.test(it.text)) return { id: it.id, text: '', fact_ids: [], change: 'supprimée : aucun fait' };
        if (/40\+/.test(it.text)) return { id: it.id, text: '25+ leads qualifiés par mois.', fact_ids: ['exp.alpha.r2'], change: 'chiffre corrigé' };
        if (it.id === 's1') return { id: it.id, text: 'Prospection B2B, négociation avec les décideurs et suivi CRM sous HubSpot.', fact_ids: ['exp.alpha.t1', 'exp.alpha.t2', 'exp.alpha.t3'], change: 'plus précis' };
        return { id: it.id, text: it.text, fact_ids: it.fact_ids, change: 'inchangé' };
      }) };
    }
    if (prompt.startsWith("Tu n'as PAS écrit ce document")) {
      const sc = (n, w) => ({ score: n, why: w, evidence: '' });
      return { ten_second: { identity: 'Camille Test', target: 'Business Developer Junior', level: 'Junior', value: 'Prospection B2B chiffrée', verdict: 'PASS' },
        scores: { RECRUITER: sc(8, 'Lisible en 10 s'), HIRING_MANAGER: sc(8, 'Preuves chiffrées'), ATS: sc(8, 'Mots-clés présents'), DESIGN: sc(8, 'Sobre'), FACTUALITY: sc(9, 'Tracé'), MATCH: sc(8, 'Aligné'), SECTOR: sc(8, 'Codes BD') },
        issues: [{ severity: 'medium', type: 'profil_vague', line_ids: ['s1'], problem: 'Résumé un peu générique', fix: 'Citer CRM et négociation' }], keep: ['Chiffres de prospection'] };
    }
    if (prompt.startsWith('Tu écris la lettre de motivation')) {
      return { subject: 'Objet : candidature au poste de Business Developer Junior', salutation: 'Madame, Monsieur,',
        paragraphs: [
          { role: 'HOOK', sentences: [{ text: 'Votre annonce demande de « prospecter de nouveaux clients PME par téléphone et LinkedIn ».', kind: 'offer_ref', fact_ids: [], offer_quote: 'Prospecter de nouveaux clients PME par téléphone et LinkedIn' },
            { text: "C'est mon quotidien chez Alpha Services : prospection B2B et cycle commercial complet.", kind: 'claim', fact_ids: ['exp.alpha', 'exp.alpha.t1'] }] },
          { role: 'WHY_COMPANY', sentences: [{ text: 'Acme SaaS édite un logiciel pour les PME françaises.', kind: 'offer_ref', fact_ids: [], offer_quote: 'Acme SaaS édite un logiciel pour les PME françaises' }] },
          { role: 'PROOF', sentences: [{ text: 'Chez Alpha Services, je génère 25+ leads qualifiés par mois.', kind: 'claim', fact_ids: ['exp.alpha.r2'] }] },
          { role: 'VALUE', sentences: [{ text: 'Je veux mettre cette discipline de prospection au service d\'Acme SaaS.', kind: 'projection', fact_ids: [] }] },
          { role: 'CLOSE', sentences: [{ text: 'Disponible immédiatement et mobile en Île-de-France, je serais heureux d\'en parler avec vous.', kind: 'claim', fact_ids: ['avail.immediate', 'mobility.idf'] },
            { text: "Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.", kind: 'closing', fact_ids: [] }] }],
        signature: 'Camille Test' };
    }
    if (prompt.startsWith('Tu prépares les réponses')) {
      return { answers: [{ question: 'Quelle est votre disponibilité ?', type: 'AVAILABILITY', answer: 'Disponibilité immédiate.', fact_ids: ['avail.immediate'], confidence: 'HIGH', ask_user: '' },
        { question: 'Quelles sont vos prétentions salariales ?', type: 'SALARY', answer: '45 k€', fact_ids: [], confidence: 'HIGH', ask_user: '' }] };
    }
    if (prompt.startsWith('Tu es un recruteur expérimenté')) return { scores: {}, winner: 'X', reason: 'Plus concret' };
    if (prompt.startsWith("Tu regardes l'image")) return { score: 8, issues: [], verdict: 'PASS' };
    if (prompt.startsWith("Tu analyses des retours")) return { proposals: [] };
    return {};
  };
  const calls = [];
  const sample = async (input, opts = {}) => {
    const text = input === 'Réponds uniquement par OK.' ? 'OK' : 'Préparez trois exemples chiffrés de prospection B2B et la manière dont vous suivez votre pipeline.';
    calls.push({ task: 'chat' }); if (opts.onText) opts.onText({ text, delta: text }); return { text, truncated: false, modelTierApplied: opts.modelTier || 'default' };
  };
  sample.json = async (input, opts = {}) => {
    const prompt = typeof input === 'string' ? input : input.map((t) => t.content).join('\n');
    calls.push({ task: prompt.slice(0, 40), tier: opts.modelTier, images: !!opts.images });
    const out = respond(prompt);
    await new Promise((r) => setTimeout(r, window.__PAI_MOCK_DELAY__ || 25));
    if (opts.onText) opts.onText({ text: JSON.stringify(out), delta: '' });
    return copy(out);
  };
  sample.limits = async () => ({ maxPromptBytes: 65536, images: { maxCount: 4, maxInputBytes: 20000000, mediaTypes: ['image/png', 'image/jpeg'] }, tools: { maxCount: 8 } });
  const saved = [];
  const downloads = { save: async ({ filename, data }) => {
    const buf = data instanceof Blob ? new Uint8Array(await data.arrayBuffer()) : typeof data === 'string' ? new TextEncoder().encode(data) : new Uint8Array(data);
    saved.push({ filename, size: buf.length, head: String.fromCharCode(...buf.slice(0, 5)) }); return { status: 'saved' };
  } };
  const user = { isOwner: () => true, canEdit: () => true, can: () => true, id: async () => 'owner', me: async () => ({ id: 'owner' }) };
  window.__PAI_MOCK__ = { store, calls, saved };
  window.claude = { use: async (name) => ({ db, sample, downloads, user })[name] || null };
})();
