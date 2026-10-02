// ─── Pipeline en 9 étapes, visibles en direct ────────────────────────────────
// INGEST → UNDERSTAND → COMPANY → MATCH → STRATEGY → CV → LETTER → PACK → QA.
// Chaque étape a une voie déterministe : sans IA, PAI produit quand même un pack complet (moins rédigé, tout aussi vrai).
const STAGES = [
  ['ingest', 'Ingest', "Lecture de l'offre"],
  ['understand', 'Understand', 'Compréhension du poste'],
  ['company', 'Company', "L'entreprise, d'après l'annonce"],
  ['match', 'Match', 'Ton profil face à l\'offre'],
  ['strategy', 'Strategy', 'Angle, titre et design'],
  ['cv', 'CV', 'CV lié à tes faits, validé ligne par ligne'],
  ['letter', 'Letter', 'Lettre assortie au CV'],
  ['pack', 'Pack', 'Questions, scores et versions'],
  ['qa', 'QA', 'PDF réel : pages, lecture ATS, polices'],
];
const STAGE_KEYS = STAGES.map((s) => s[0]);
const MODE_SKIP = { QUICK: ['cv', 'letter', 'qa'], STANDARD: [], DEEP: [] };
const MODE_INFO = {
  QUICK: ['Rapide', 'Analyse, correspondance, stratégie et design (≈ 30 s).'],
  STANDARD: ['Standard', 'Pack complet : CV, critique, lettre, questions, PDF contrôlé (≈ 2 à 4 min avec IA).'],
  DEEP: ['Approfondi', 'Deux variantes de CV (deux designs), jusqu\'à 3 cycles de critique, contrôle visuel du PDF (≈ 5 à 8 min).'],
};

// Contexte d'exécution courant : l'analyse en cours (S.run) ou une tâche annexe (V2, réécriture) qui ne touche pas à l'affichage de l'analyse.
let CUR = null;
function startRun(mode, meta) {
  CUR = S.run = { status: 'running', mode, controller: new AbortController(), calls: [], log: [], results: {}, packId: null, error: null, startedAt: Date.now(), meta: meta || {},
    steps: STAGES.map(([k]) => ({ key: k, state: MODE_SKIP[mode].includes(k) ? 'skip' : 'todo', detail: '', note: '', t0: 0, ms: 0 })) };
  render();
}
const setStep = (key, state, detail) => {
  if (!S.run || CUR !== S.run) return; const st = S.run.steps.find((s) => s.key === key); if (!st) return;
  if (state === 'run' && st.state !== 'run') st.t0 = performance.now();
  if ((state === 'done' || state === 'fail') && st.t0) st.ms = Math.round(performance.now() - st.t0);
  st.state = state; if (detail !== undefined) st.detail = detail; S.run.log.push({ stage: key, state, detail: detail || '' }); renderRun();
};
// Texte en direct pendant qu'une IA rédige : mise à jour ciblée (pas de rendu complet de la page).
const liveText = (key) => (text) => {
  if (!CUR || CUR !== S.run) return; const st = S.run.steps.find((s) => s.key === key); if (!st) return;
  st.detail = `${AI.short()} rédige… ${text.length.toLocaleString('fr-FR')} caractères`;
  const el = document.querySelector(`.stage[data-k="${key}"] .name span`); if (el) el.textContent = st.detail; else renderRun();
};

async function tryAi(key, fn) {
  if (!AI.ok()) return null;
  try { return await fn(); } catch (e) {
    if (e && e.code === 'cancelled') throw e;
    if (CUR) { CUR.log.push({ stage: key, state: 'ai_error', detail: AI.message(e) }); const st = CUR.steps.find((s) => s.key === key); if (st) st.note = AI.message(e); }
    return null;
  }
}

async function fixLoop(lines, validator, P, a, opts = {}) {
  const vars = E.commonVars(P, a); const lang = a.language_of_offer === 'en' ? 'anglais' : 'français';
  let report = validator.validateLines(lines); let instructions = opts.instructions || null;
  let targets = new Set(report.rejected_ids.concat(Object.keys(instructions || {})));
  let attempts = 0; const dropped = [];
  while (targets.size && AI.ok() && attempts < 2) {
    attempts++;
    const payload = lines.filter((l) => targets.has(l.id)).map((l) => ({ id: l.id, text: l.text, kind: l.kind, fact_ids: l.fact_ids,
      reasons: ((report.verdicts.find((v) => v.line_id === l.id) || {}).reasons || []).concat(instructions && instructions[l.id] ? [instructions[l.id]] : []) }));
    const fixed = await tryAi(opts.step || 'cv', () => AI.ask('cv_fix', { rejected_lines_json: JSON.stringify(payload), facts_table: vars.facts_table,
      critic_instructions: (opts.general || []).join(' ; ') || 'aucune', truth_rules: vars.truth_rules, language: lang }, { signal: CUR && CUR.controller.signal, cache: false }));
    if (!fixed || !Array.isArray(fixed.lines)) break;
    const byId = new Map(fixed.lines.filter((x) => x && x.id).map((x) => [String(x.id), x]));
    lines = lines.flatMap((l) => {
      const it = byId.get(l.id); if (!it) return [l];
      const t = String(it.text || '').trim();
      if (!t) { dropped.push({ id: l.id, text: l.text, reasons: ((report.verdicts.find((v) => v.line_id === l.id) || {}).reasons || []).concat(['supprimée à la correction : aucune version vraie possible']) }); return []; }
      return [Object.assign({}, l, { text: t, fact_ids: (it.fact_ids || l.fact_ids).map(String) })];
    });
    instructions = null; report = validator.validateLines(lines); targets = new Set(report.rejected_ids);
  }
  const rej = new Set(report.rejected_ids);
  const removed = dropped.concat(lines.filter((l) => rej.has(l.id)).map((l) => ({ id: l.id, text: l.text, reasons: (report.verdicts.find((v) => v.line_id === l.id) || {}).reasons || [] })));
  const kept = lines.filter((l) => !rej.has(l.id));
  const final = validator.validateLines(kept); final.forbidden_hits += report.forbidden_hits;
  return { lines: kept, report: final, removed };
}

function critiqueInstructions(ai) {
  const per = {}; const general = [];
  for (const it of (ai && ai.issues) || []) {
    if (!['high', 'medium'].includes(String(it.severity))) continue;
    const fix = `${it.problem || ''} → ${it.fix || ''}`.replace(/^ → | → $/g, '');
    const ids = (it.line_ids || []).map(String);
    if (ids.length) ids.forEach((id) => { per[id] = per[id] ? `${per[id]} ; ${fix}` : fix; }); else general.push(fix);
  }
  return [per, general];
}

async function generateCv(P, a, m, strat, offer, opts = {}) {
  const vars = E.commonVars(P, a); const d = E.design(strat.best.design_profile); const signal = CUR && CUR.controller.signal;
  let cv = E.buildCvDeterministic(P, a, m, strat, S.profile.validated);
  const ai = await tryAi('cv', () => AI.ask('cv_content', Object.assign({}, vars, {
    strategy_json: JSON.stringify(strat.best), synonyms: JSON.stringify({ equivalents: D.synonyms.equivalents.slice(0, 25), implies: D.synonyms.implies }),
    banned_phrases: D.banned.hard.slice(0, 30).join(', '), feedback_context: opts.feedback || feedbackContext(a),
    language: a.language_of_offer === 'en' ? 'anglais' : 'français', max_bullets_featured: String(d.max_bullets_featured || 4), max_bullets_other: String(d.max_bullets_other || 2),
  }), { signal, onText: liveText('cv'), cache: opts.cache }));
  if (ai && typeof ai === 'object') cv = E.cvFromAi(ai, P, a, m, strat, S.profile.validated);
  return cv;
}

async function validateAndCritique(cv, P, a, m, offer, cycles) {
  const validator = E.Validator(S.profile, offer.text, [a.job_title, a.company]);
  setStep('cv', 'run', 'Contrôle de chaque ligne contre tes faits');
  let r = await fixLoop(cv.lines, validator, P, a, { step: 'cv' });
  cv.lines = r.lines; cv.removed_lines = (cv.removed_lines || []).concat(r.removed); E.syncBlocks(cv);
  let report = r.report;
  setStep('cv', 'run', `${report.traced}/${report.total} lignes tracées · jury : recruteur, manager, ATS, design, factualité`);
  const vars = E.commonVars(P, a); let critique = { deterministic: null, ai: null };
  for (let cycle = 0; cycle < Math.max(1, cycles); cycle++) {
    const det = E.deterministicCritique(cv, a, m, report);
    const ai = await tryAi('cv', () => AI.ask('critique', { analysis_json: vars.analysis_json, sector_json: vars.sector_json, country_json: vars.country_json,
      design_json: JSON.stringify(E.design(cv.design_profile)), validation_json: JSON.stringify({ factuality: report.factuality, total: report.total, traced: report.traced, warnings: report.warnings }),
      cv_text: E.cvPlainText(cv), sector_name: vars.sector_name }, { signal: CUR && CUR.controller.signal, onText: liveText('cv'), cache: false }));
    critique = { deterministic: det, ai: ai && typeof ai === 'object' ? ai : null, cycles: cycle + 1 };
    const [per, general] = critiqueInstructions(critique.ai);
    det.issues.filter((i) => i.severity === 'high' && !i.line_ids.length).forEach((i) => general.push(i.fix));
    if (!AI.ok() || (!Object.keys(per).length && !general.length)) break;
    const targets = {}; for (const [id, t] of Object.entries(per)) if (E.lineById(cv, id)) targets[id] = t;
    if (!Object.keys(targets).length && general.length) for (const l of E.sectionLines(cv, 'summary').slice(0, 1).concat(E.sectionLines(cv, 'experience').slice(0, 2))) targets[l.id] = general.join(' ; ');
    if (!Object.keys(targets).length) break;
    setStep('cv', 'run', `Critique, cycle ${cycle + 1} : ${nb(Object.keys(targets).length, 'ligne', 'lignes')} à corriger`);
    r = await fixLoop(cv.lines, validator, P, a, { instructions: targets, general, step: 'cv' });
    cv.lines = r.lines; cv.removed_lines = cv.removed_lines.concat(r.removed); E.syncBlocks(cv); report = r.report;
  }
  return { cv, report, critique };
}

async function buildLetter(P, a, m, strat, offer) {
  const vars = E.commonVars(P, a); const s = E.sector(a.sector_id); const [lo, hi] = (s.letter_style || {}).length_words || [220, 320];
  const base = E.buildLetterDeterministic(P, a, m, strat, offer, S.profile.validated);
  const ai = await tryAi('letter', () => AI.ask('letter', { analysis_json: vars.analysis_json, strategy_json: JSON.stringify(strat.best),
    company_facts: JSON.stringify({ source: 'offre', texte: offer.text.slice(0, 1500) }), facts_table: vars.facts_table, sector_json: vars.sector_json,
    banned_phrases: D.banned.hard.slice(0, 30).join(', '), feedback_context: feedbackContext(a), truth_rules: vars.truth_rules, candidate_name: P.value('id.name'),
    language: a.language_of_offer === 'en' ? 'anglais' : 'français', length_words: `${lo} à ${hi}`, company: a.company, job_title: strat.best.title },
  { signal: CUR && CUR.controller.signal, onText: liveText('letter') }));
  const letter = ai && typeof ai === 'object' ? E.letterFromAi(ai, P, base) : base;
  const validator = E.Validator(S.profile, offer.text, [a.job_title, a.company]);
  const r = await fixLoop(letter.lines, validator, P, a, { step: 'letter' });
  letter.lines = r.lines; letter.removed_lines = r.removed;
  return { letter, report: r.report, checks: E.letterChecks(letter, a) };
}

function splitQuestions(raw) { return String(raw || '').split(/\n+|(?<=\?)\s+/).map((q) => q.replace(/^[\s\-•*]+/, '').trim()).filter((q) => q.length > 5).slice(0, 15); }
function answerDeterministic(q, P) {
  const n = E.norm(q);
  if (/salaire|remuneration|pretention|salary|compensation/.test(n)) return { question: q, type: 'SALARY', answer: '', fact_ids: [], confidence: 'BLOCKED', ask_user: 'Quelles sont tes prétentions salariales (fixe + variable) ?' };
  if (/disponib|date de debut|start date|preavis|notice/.test(n) && P.fact('avail.immediate')) return { question: q, type: 'AVAILABILITY', answer: `${P.value('avail.immediate')}.`, fact_ids: ['avail.immediate'], confidence: 'HIGH', ask_user: '' };
  if (/langue|anglais|english|espagnol|arabe|toeic/.test(n)) { const fs = P.byKind('language'); return { question: q, type: 'LANGUAGE', answer: fs.map((f) => f.text).join(' ; ') + (P.fact('cert.toeic') ? ` (${P.value('cert.toeic')})` : '') + '.', fact_ids: fs.map((f) => f.id).concat(P.fact('cert.toeic') ? ['cert.toeic'] : []), confidence: 'HIGH', ask_user: '' }; }
  if (/mobilit|demenag|relocat/.test(n) && P.fact('mobility.idf')) return { question: q, type: 'ADMIN', answer: `${P.value('mobility.idf')} (confirmée). Au-delà : à préciser.`, fact_ids: ['mobility.idf'], confidence: 'MEDIUM', ask_user: '' };
  return { question: q, type: 'OPEN', answer: '', fact_ids: [], confidence: 'BLOCKED', ask_user: 'Réponse personnelle nécessaire : que veux-tu dire ?' };
}
async function buildAnswers(raw, P, a) {
  const qs = splitQuestions(raw); if (!qs.length) return [];
  const vars = E.commonVars(P, a);
  const ai = await tryAi('pack', () => AI.ask('answers', { questions: qs.map((q) => `- ${q}`).join('\n'), analysis_json: vars.analysis_json, facts_table: vars.facts_table,
    truth_rules: vars.truth_rules, candidate_name: P.value('id.name'), language: a.language_of_offer === 'en' ? 'anglais' : 'français' }, { signal: CUR && CUR.controller.signal }));
  if (ai && Array.isArray(ai.answers)) {
    const known = new Set(P.usableFacts().map((f) => f.id));
    return ai.answers.map((x) => {
      const ans = { question: String(x.question || ''), type: String(x.type || 'OPEN'), answer: String(x.answer || ''), fact_ids: (x.fact_ids || []).map(String), confidence: String(x.confidence || 'BLOCKED'), ask_user: String(x.ask_user || '') };
      if (ans.confidence !== 'BLOCKED' && (!ans.fact_ids.length || !ans.fact_ids.every((id) => known.has(id)))) { ans.confidence = 'BLOCKED'; ans.answer = ''; ans.ask_user = ans.ask_user || 'Aucun fait du profil ne permet de répondre : à compléter par toi.'; }
      return ans;
    });
  }
  return qs.map((q) => answerDeterministic(q, P));
}

function feedbackContext(a) {
  const ctx = S.feedback.filter((f) => f.context && (f.context.sector === a.sector_id)).slice(0, 12)
    .map((f) => `${f.id} [${f.element}${(f.reasons || []).length ? ` : ${f.reasons.join(', ')}` : ''}] ${f.rating === 1 ? '👍' : f.rating === -1 ? '👎' : '😐'} ${f.comment || ''}`.trim());
  const rules = (S.rules.accepted || []).map((r) => `RÈGLE ${r.id}: ${r.rule_text}`);
  return ctx.concat(rules).join('\n') || 'aucun';
}

// Design automatique + préférences explicites (la préférence de l'utilisateur prime, sauf règle pays « jamais »).
function designFor(a, strat, offerText) {
  const pm = Photo.mode(); const hasPhoto = !!S.photoAssets;
  const prefs = Object.assign({}, S.prefs || {}, { photo: pm === 'OFF' ? 'never' : pm === 'AUTO' ? '' : 'always' });
  const auto = E.autoDesign(a, strat, { offerText, prefs, hasPhoto });
  if (hasPhoto && (pm === 'HEADER' || pm === 'SIDEBAR') && !['never'].includes(E.country(a.country).photo)) {
    const fam = auto.design; const mode = pm === 'SIDEBAR' && fam !== 'digital_creative' ? 'HEADER' : pm;
    if (auto.photo_mode !== mode) { auto.photo_mode = mode; auto.why = auto.why.filter((w) => w.k !== 'photo').concat([{ k: 'photo', t: `Ta préférence : photo ${mode === 'SIDEBAR' ? 'en colonne' : 'dans l\'en-tête'}` }]); }
  }
  return auto;
}
const applyDesign = (cv, auto, family) => Object.assign(cv, { design_profile: family || auto.design, palette: auto.palette, density: auto.density, photo_mode: family && family !== auto.design ? (auto.photo_mode === 'SIDEBAR' ? 'HEADER' : auto.photo_mode) : auto.photo_mode, design_why: auto.why });

const hostOf = (u) => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return ''; } };
async function runPipeline(input) {
  const P = Pp(); if (!P) { toast("Aucun profil : importe d'abord ton Master Profile (Profil).", 'i-alert'); return null; }
  if (S.run && S.run.status === 'running') { toast('Une analyse est déjà en cours.', 'i-info'); S.view = 'analyser'; render(); return null; }
  const isUrl = !!input.url;
  if (!isUrl && String(input.text || '').trim().length < 80) { toast("Offre trop courte : colle le texte complet (80 caractères minimum).", 'i-alert'); return null; }
  const mode = S.draft.mode; startRun(mode, { source: isUrl ? 'url' : input.sourceType, url: input.url || '', file: input.fileName || '' });
  S.view = 'analyser'; render();
  const signal = S.run.controller.signal; const R = S.run.results;
  try {
    // 1. INGEST (lien lu côté serveur avec protection anti-SSRF ; échec honnête + repli texte/PDF)
    setStep('ingest', 'run', isUrl ? `Lecture sécurisée de ${hostOf(input.url)}` : 'Empreinte et doublons');
    let text = String(input.text || '').trim(); let sourceUrl = input.sourceUrl || ''; let sourceType = input.sourceType || 'text';
    let title = String(input.title || '').trim(); let company = String(input.company || '').trim();
    if (isUrl) {
      try {
        const got = await Ingest.fromUrl(input.url);
        text = got.text; sourceUrl = got.sourceUrl; sourceType = 'url'; title = title || got.title; company = company || got.company;
      } catch (e) {
        const msg = Ingest.message(e); setStep('ingest', 'fail', msg);
        S.run.status = 'failed'; S.run.error = msg; S.run.fallback = true; render(); return null;
      }
      if (signal.aborted) { const e = new Error('Annulé'); e.code = 'cancelled'; throw e; }
    }
    const offer = { id: `off_${E.hash(E.norm(text))}`, source_type: sourceType, source_url: sourceUrl, file_name: input.fileName || '', fetched_at: nowIso(),
      title_hint: title, company_hint: company, text: text.slice(0, 30000), text_hash: E.hash(E.norm(text)), synthetic: !!input.synthetic };
    const dup = S.packs.find((p) => p.offer && p.offer.text_hash === offer.text_hash);
    R.offer = offer; R.dup = dup ? { id: dup.id, at: dup.created_at } : null;
    setStep('ingest', 'done', `${text.length.toLocaleString('fr-FR')} caractères · ${({ url: 'lien', pdf: 'PDF', text: 'texte collé' })[offer.source_type] || offer.source_type}${dup ? ' · déjà analysée : nouvelle version' : ''}`);

    // 2. UNDERSTAND
    setStep('understand', 'run', 'Extraction déterministe');
    const base = E.deterministicAnalysis(offer);
    const aiA = await tryAi('understand', () => AI.ask('analyze_offer', { offer_text: offer.text.slice(0, 12000), job_title_hint: offer.title_hint, company_hint: offer.company_hint,
      deterministic_json: JSON.stringify(Object.assign({}, base, { sector_scores: undefined })) }, { signal, onText: liveText('understand') }));
    const a = aiA && typeof aiA === 'object' ? E.mergeAiAnalysis(base, aiA) : base;
    R.analysis = a;
    setStep('understand', 'done', `${a.job_title} · ${disp(a.contract, 'contract')} · ${E.sector(a.sector_id).name || a.sector_id}${a.source === 'deterministic' ? ' · sans IA' : ''}`);

    // 3. COMPANY (uniquement ce que dit l'annonce ; logo jamais utilisé s'il n'est pas vérifié)
    setStep('company', 'run');
    R.company = E.companyCard(a, offer);
    setStep('company', 'done', R.company.name ? `${R.company.name}${R.company.figures.length ? ` · ${nb(R.company.figures.length, 'chiffre cité', 'chiffres cités')}` : ''} · source : l'annonce` : "Entreprise non nommée dans l'annonce");

    // 4. MATCH
    setStep('match', 'run');
    const m = E.computeMatch(P, a); R.match = m;
    setStep('match', 'done', `Correspondance ${pct(m.match)}\u00a0/\u00a0100 · qualité ${pct(m.quality)} · risque\u00a0${pct(m.risk)}`);

    // 5. STRATEGY (+ design automatique expliqué)
    setStep('strategy', 'run', 'Comparaison des positionnements');
    let strat = E.deterministicStrategy(P, a, m); const vars = E.commonVars(P, a);
    const aiS = await tryAi('strategy', () => AI.ask('strategy', Object.assign({}, vars, { match_json: JSON.stringify({ scores: m.scores, match: m.match, quality: m.quality, risk: m.risk, missing: m.missing, strengths: m.strengths }),
      learned_rules: (S.rules.accepted || []).map((r) => r.rule_text).join('\n') || 'aucune', variants: mode === 'DEEP' ? '3' : '2' }),
    { signal, tier: mode === 'QUICK' ? 'default' : undefined, onText: liveText('strategy') }));
    if (aiS && aiS.best && typeof aiS.best === 'object') {
      strat = E.sanitizeStrategy({ options: Array.isArray(aiS.options) ? aiS.options : [], comparison: String(aiS.comparison || ''), chosen: String(aiS.chosen || 'A'),
        best: Object.assign({}, strat.best, aiS.best), source: 'ai' }, P, a);
    }
    const auto = designFor(a, strat, offer.text);
    strat.best.design_profile = auto.design; strat.best.photo_mode = auto.photo_mode;
    R.strategy = strat; R.design = auto;
    setStep('strategy', 'done', `« ${strat.best.title} » · ${DESIGN_NAME(auto.design)} · ${DS.PALETTES[auto.palette] ? DS.PALETTES[auto.palette].label : auto.palette}${auto.photo_mode !== 'OFF' ? ' · avec photo' : ''}`);

    const pack = { id: uid('pack'), created_at: nowIso(), mode, status: 'DRAFT', engine: 'studio', provider: AI.ok() ? AI.label() : 'aucun (mode sans IA)', ai_mode: AI.mode(),
      versions: { offer_v: offer.text_hash, profile_v: profileTag(S.profile), engine_v: D.version.engine, prompt_v: D.version.prompts, rules_v: D.version.rules, cv_v: '', letter_v: '', answers_v: '', design_v: `${auto.design}@${(D.designs[auto.design] || {}).version || 1}` },
      offer, analysis: a, match: m, strategy: strat, design: auto, company: R.company, cvs: [], cv_index: 0, letters: [], letter_index: 0, answers: [], scores: {},
      risks: m.risks.map((r) => r.text).concat(strat.best.risks || []), next_action: '', missing_profile_data: missingData(S.profile), log: [], calls: [] };

    if (mode === 'QUICK') {
      setStep('pack', 'run');
      pack.next_action = 'Relancer en mode Standard pour générer le CV et la lettre.';
      return await finishPack(pack);
    }

    // 6. CV (+ 7. LETTER en parallèle)
    const cycles = ((D.models.modes || {})[mode] || {}).critique_cycles || 1;
    setStep('cv', 'run', 'Plan de contenu');
    setStep('letter', 'run', 'Rédaction en parallèle');
    const letterPromise = buildLetter(P, a, m, strat, offer);
    const variants = [{ strat, family: auto.design }];
    if (mode === 'DEEP') {
      const alt = Array.isArray(strat.options) ? strat.options.find((o) => o && o.key !== strat.chosen) : null;
      const altStrat = alt ? E.sanitizeStrategy({ options: [], chosen: alt.key, best: Object.assign({}, strat.best, alt), source: strat.source }, P, a) : strat;
      variants.push({ strat: altStrat, family: auto.design === 'ats_hybrid' ? 'modern_commercial' : 'ats_hybrid' });
    }
    const cvs = [];
    for (const [i, vt] of variants.entries()) {
      const cv0 = await generateCv(P, a, m, vt.strat, offer); applyDesign(cv0, auto, vt.family);
      setStep('cv', 'run', `${cv0.lines.length} lignes (${cv0.source === 'ai' ? `rédigées par ${AI.short()}` : 'tirées de tes faits'})${variants.length > 1 ? ` · variante ${i + 1}/${variants.length}` : ''}`);
      const res = await validateAndCritique(cv0, P, a, m, offer, cycles);
      cvs.push(Object.assign(res, { label: i === 0 ? 'V1' : `V1 bis · ${DESIGN_NAME(vt.family)}` }));
    }
    const c0 = cvs[0];
    R.cv = { lines: c0.cv.lines.length, traced: c0.report.traced, total: c0.report.total, removed: (c0.cv.removed_lines || []).length, source: c0.cv.source, judges: c0.critique.ai && c0.critique.ai.scores ? Object.keys(c0.critique.ai.scores).length : 0 };
    setStep('cv', 'done', `${c0.report.traced}/${c0.report.total} lignes tracées · factualité ${pct(c0.report.factuality)}\u00a0%${R.cv.removed ? ` · ${nb(R.cv.removed, 'retirée', 'retirées')} faute de preuve` : ''}`);
    const L = await letterPromise; L.letter.layout = auto.design;
    R.letter = { refs: L.letter.lines.filter((l) => l.kind === 'offer_ref').length, traced: L.report.traced, total: L.report.total, checks: L.checks };
    setStep('letter', 'done', `${L.report.traced}/${L.report.total} phrases tracées · ${nb(R.letter.refs, 'élément propre', 'éléments propres')} à l'annonce`);

    // 8. PACK
    setStep('pack', 'run', 'Questions du formulaire, scores, versions');
    pack.answers = await buildAnswers(input.questions, P, a);
    pack.cvs = cvs.map((e, i) => ({ v: i + 1, label: e.label, created_at: nowIso(), source: e.cv.source, doc: e.cv, report: e.report, critique: e.critique, qa: null, change: i === 0 ? 'Première version' : 'Variante de design' }));
    pack.letters = [{ v: 1, label: 'V1', created_at: nowIso(), source: L.letter.source, doc: L.letter, report: L.report, checks: L.checks }];
    setStep('pack', 'done', `${pack.answers.length ? `${nb(pack.answers.length, 'réponse', 'réponses')} · ${pack.answers.filter((x) => x.confidence === 'BLOCKED').length} à compléter` : 'aucune question'} · ${pack.cvs.length} CV · 1 lettre`);

    // 9. QA (PDF réel)
    setStep('qa', 'run', 'pdfmake → PDF texte, relu par pdf.js');
    const maxPages = E.country(a.country).max_pages || 1;
    const required = m.coverage.filter((c) => c.covered && c.priority === 'REQUIRED').map((c) => c.term);
    for (const [i, entry] of pack.cvs.entries()) {
      const fit = await PDF.cvFitted(entry.doc, maxPages);
      entry.doc = fit.doc; entry.qa = PDF.qa(fit.info, fit.doc, required, maxPages); entry.qa.trim_steps = fit.trimSteps;
      entry.report = E.Validator(S.profile, offer.text, [a.job_title, a.company]).validateLines(entry.doc.lines);
      if (mode === 'DEEP' && i === 0 && S.aiLimits && S.aiLimits.images) {
        const png = await PDF.pngBlob(fit.bytes);
        const vis = await tryAi('qa', () => AI.ask('judge_visual', { context: `CV pour « ${a.job_title} » (${a.company}), design ${DESIGN_NAME(fit.doc.design_profile)}` }, { signal, images: [png], cache: false }));
        if (vis) entry.qa.visual = vis;
      }
    }
    if (pack.cvs.length > 1) {
      const avg = (e) => { const sc = e.critique.ai && e.critique.ai.scores ? Object.values(e.critique.ai.scores).map((v) => Number(v && v.score) || 0) : [0]; return sc.reduce((x, y) => x + y, 0) / sc.length; };
      const first = pack.cvs[0]; const best = pack.cvs.slice().sort((x, y) => avg(y) - avg(x))[0];
      pack.cv_index = pack.cvs.indexOf(best.qa && best.qa.ok ? best : first);
    }
    const q0 = pack.cvs[pack.cv_index].qa; R.qa = q0;
    setStep('qa', q0.ok ? 'done' : 'fail', `${nb(q0.pages, 'page', 'pages')} · police min. ${num(q0.min_font_pt)}\u00a0pt · mots-clés requis ${q0.required_found}${q0.issues.length ? ` · ${q0.issues.map((x) => x.detail).join(', ')}` : ' · aucun défaut'}`);
    return await finishPack(pack);
  } catch (e) {
    const cancelled = e && (e.code === 'cancelled' || e.name === 'AbortError');
    if (S.run) {
      S.run.status = cancelled ? 'cancelled' : 'failed'; S.run.error = cancelled ? 'Analyse arrêtée. Rien n\'a été enregistré.' : `Échec propre : ${(e && e.message) || e}. Rien n'a été enregistré.`;
      const st = S.run.steps.find((s) => s.state === 'run'); if (st) st.state = 'fail';
    }
    console.error(e); render();
    return null;
  }
}

function computeScores(pack) {
  const cvE = pack.cvs[pack.cv_index]; const lE = pack.letters[pack.letter_index];
  const crit = cvE && cvE.critique ? cvE.critique.deterministic : null;
  const points = E.scoreEvents(cvE && cvE.doc, lE && lE.doc, pack.analysis, pack.match, pack.strategy, { cv: (cvE && cvE.report) || {}, letter: (lE && lE.report) || {} }, crit);
  return { factuality_cv: cvE ? cvE.report.factuality : null, factuality_letter: lE ? lE.report.factuality : null, match: pack.match.match, quality: pack.match.quality, risk: pack.match.risk, points };
}
function refreshStatus(pack) {
  const cvE = pack.cvs[pack.cv_index]; const lE = pack.letters[pack.letter_index];
  const perfect = cvE && lE && cvE.report.perfect && lE.report.perfect;
  const pdfOk = cvE && cvE.qa ? cvE.qa.ok : true;
  pack.status = S.profile.validated && perfect && pdfOk ? 'FINAL' : 'DRAFT';
  pack.next_action = pack.status === 'FINAL' ? 'Relis le pack, puis postule toi-même (PAI n\'envoie rien).'
    : !S.profile.validated ? 'Valide ton Master Profile (Profil) : tes documents passeront de BROUILLON à FINAL. Puis relis et postule toi-même.'
      : !pdfOk ? 'Le PDF a un défaut de mise en page : ouvre CV Studio et change de densité ou de design.'
        : 'Corrige les lignes signalées (factualité 100 % requise) avant de postuler.';
  pack.scores = computeScores(pack);
  if (cvE) { pack.versions.cv_v = E.hash(cvE.doc.lines); pack.versions.letter_v = lE ? E.hash(lE.doc.lines) : ''; pack.versions.design_v = `${cvE.doc.design_profile}@${(D.designs[DS.familyOf(cvE.doc.design_profile)] || {}).version || 1}`; }
  pack.versions.answers_v = pack.answers.length ? E.hash(pack.answers) : '';
}
async function finishPack(pack) {
  if (pack.cvs.length) refreshStatus(pack);
  pack.log = S.run.log.slice(); pack.calls = S.run.calls.slice();
  await Store.savePack(pack);
  S.packId = pack.id; lsSet('packId', pack.id); S.run.status = 'done'; S.run.packId = pack.id; S.run.results.pack = { id: pack.id, status: pack.status };
  if (!pack.cvs.length) setStep('pack', 'done', `Pack ${pack.status} enregistré (analyse seule)`);
  S.run.ms = Date.now() - S.run.startedAt;
  Object.assign(S.draft, { input: '', title: '', company: '', questions: '', sourceType: 'text', fileName: '', synthetic: false, textMode: false, notice: null });
  render();
  return pack;
}
function missingData(p) {
  const out = (p.unknowns || []).slice();
  (p.review_queue || []).forEach((r) => out.push(`${r.fact_id} — ${r.reason}`));
  p.facts.filter((f) => f.needs_confirmation && E.usable(f)).forEach((f) => out.push(`À confirmer : ${f.text} (${f.id})`));
  return out;
}

// ─── Lecture d'une offre (lien, texte, PDF) ──────────────────────────────────
const looksLikeUrl = (t) => /^https?:\/\/[^\s]+$/i.test(String(t || '').trim());
const Ingest = {
  // Serveur PAI : lecture sûre côté serveur (anti-SSRF). claude.ai : aucune requête vers un autre site n'est possible.
  async fromUrl(raw) {
    const url = String(raw || '').trim();
    if (!looksLikeUrl(url)) { const e = new Error('Lien invalide : il doit commencer par http:// ou https://'); e.code = 'bad_url'; throw e; }
    if (!SERVER) { const e = new Error("Dans claude.ai, PAI ne peut pas ouvrir un lien (sécurité de la page). Colle le texte de l'offre ou importe son PDF — la lecture de liens fonctionne sur ton serveur PAI."); e.code = 'no_fetch_here'; throw e; }
    const r = await Srv.req('POST', '/v1/ingest/url', { url });
    const o = r.offer || {};
    if (!o.text || o.text.length < 80) { const e = new Error('Page lue, mais le texte de l\'offre est trop court ou vide.'); e.code = 'unreadable'; throw e; }
    return { text: o.text, title: o.title_hint || '', company: o.company_hint || '', sourceUrl: o.source_url || url, sourceType: 'url' };
  },
  message(e) {
    const code = (e && e.code) || '';
    return ({
      login_walled: 'Cette page demande une connexion (LinkedIn, Indeed connecté…) : PAI ne lit jamais derrière un compte. Copie le texte de l\'offre ou enregistre-la en PDF.',
      bad_url: 'Lien invalide.', blocked_address: 'Adresse refusée par sécurité (réseau privé ou local).', too_large: 'Page trop lourde pour être lue.',
      timeout: 'Le site met trop de temps à répondre.', http_error: 'Le site a renvoyé une erreur (page expirée ou supprimée ?).', unreadable: 'Page lue, mais aucun texte d\'offre exploitable.',
      no_fetch_here: e && e.message, rate_limited: 'Le site limite les lectures : réessaie dans une minute, ou colle le texte de l\'offre.',
      forbidden: 'Le serveur PAI n\'a pas pu lire cette page : le site en refuse l\'accès. Colle le texte de l\'offre ou importe son PDF.',
      anti_bot: 'Le serveur PAI n\'a pas pu lire cette page : le site bloque les lectures automatiques (protection anti-robot). Colle le texte ou importe le PDF.',
      auth_required: 'Le serveur PAI n\'a pas pu lire cette page : le site exige une connexion. Colle le texte de l\'offre ou importe son PDF.',
      not_found: 'Le serveur PAI n\'a pas trouvé cette page (offre retirée ?). Colle le texte si tu l\'as encore.',
      unavailable: 'Le site de l\'offre est indisponible pour l\'instant : réessaie plus tard, ou colle le texte de l\'offre.',
      js_required: 'Le serveur PAI n\'a pas pu lire cette page : elle n\'affiche l\'offre qu\'avec JavaScript. Colle le texte de l\'offre ou importe son PDF.',
    })[code] || `Lecture impossible (${code || (e && e.message) || 'erreur'}).`;
  },
};
