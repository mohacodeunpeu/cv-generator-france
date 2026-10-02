/* PAI Studio — moteur ATS (port fidèle de pai/ats : lexicon, semantic, requirements, scoring, report, variants, changes).
 * Exigences classées (Obligatoire / Important / Un plus / Contexte) et prouvées (Prouvé / Correspondance possible /
 * Non prouvé) ; Score PAI en pourcentages, critères détaillés à la demande. Listes de mots, motifs, taxonomie et
 * pondérations viennent de PAI_DATA.ats (générées depuis Python : une seule source). Parité : tests/golden/ats_parity.json.
 * La correspondance sémantique n'est jamais une preuve. Aucun DOM, aucun réseau.
 */
(function (root) {
  'use strict';
  const E = typeof module !== 'undefined' && module.exports ? require('./engine.js') : root.PAIEngine;
  const A = {};
  const OK = 'OK'; const WARNING = 'WARNING'; const ERROR = 'ERROR';
  const PROVEN = 'PROUVÉ'; const PLAUSIBLE = 'PLAUSIBLE'; const UNPROVEN = 'NON_PROUVÉ';
  const RANK = { [PROVEN]: 2, [PLAUSIBLE]: 1, [UNPROVEN]: 0 };
  const MATCH_RANK = { EXACT: 3, SYNONYME: 2, 'SÉMANTIQUE': 1, '': 0 };
  const KEYWORD_CLASS = { REQUIRED: 'MUST', IMPORTANT: 'IMPORTANT', NICE: 'NICE_TO_HAVE' };
  const CLASS_WEIGHT = { MUST: 3, IMPORTANT: 2, NICE_TO_HAVE: 1, CONTEXT: 0 };
  const STATUS_VALUE = { [PROVEN]: 1, [PLAUSIBLE]: 0.5, [UNPROVEN]: 0 };
  Object.assign(A, { OK, WARNING, ERROR, PROVEN, PLAUSIBLE, UNPROVEN });

  // Données (compilées une fois par jeu de données).
  let cacheFor = null; let C = null;
  const cfg = () => {
    const d = E.data();
    if (C && cacheFor === d) return C;
    const x = d.ats; const re = (p) => new RegExp(p);
    C = { stop: new Set(x.lexicon.stopwords), filler: new Set(x.lexicon.filler), suffixes: x.lexicon.suffixes,
      notVerbs: new Set(x.classify.not_verbs), irReVerbs: new Set(x.classify.ir_re_verbs), contextWords: new Set(x.classify.context_words),
      soft: new Set(x.classify.soft), MUST: re(x.patterns.must), NICE: re(x.patterns.nice), CONTEXT_STRONG: re(x.patterns.context_strong),
      CONTEXT: re(x.patterns.context), ACTION_NOUN: re(x.patterns.action_noun), DEGREE: re(x.patterns.degree), YEARS: re(x.patterns.years),
      LEAD: re(x.patterns.lead_strip), families: x.taxonomy, scoring: x.scoring, variants: x.variants, labels: x.labels,
      languages: x.languages, levelWords: x.level_words };
    cacheFor = d;
    return C;
  };
  const LABEL = (k) => cfg().labels[k] || k;

  // Python round() : arrondi au pair sur les égalités exactes (mêmes pourcentages des deux côtés).
  const pyRound = (x) => { const f = Math.floor(x); const d = x - f; if (d > 0.5) return f + 1; if (d < 0.5) return f; return f % 2 === 0 ? f : f + 1; };
  const round1 = (x) => pyRound(x * 10) / 10;
  const fixed1 = (x) => (pyRound(x * 10) / 10).toFixed(1);
  const fmtG = (y) => String(Number(y));
  const cps = (s, n) => Array.from(String(s)).slice(0, n).join('');   // découpe en caractères (comme Python)
  A.pyRound = pyRound;

  // ── Lexique (pai/ats/lexicon.py) ─────────────────────────────────────────────────────────────
  A.stem = (word) => {
    const w = E.norm(word);
    if (w.endsWith('aux') && w.length > 5) return `${w.slice(0, -3)}al`;
    for (const suf of cfg().suffixes) if (w.endsWith(suf) && w.length - suf.length >= 4) return w.slice(0, -suf.length);
    return w;
  };
  const TOKEN = /[a-z0-9][a-z0-9+#.-]*[a-z0-9+#]|[a-z0-9]/g;
  const SHORT_OK = new Set(['ux', 'ui', 'rh', 'bi', 'pr']);
  A.tokens = (text) => E.norm(text).replace(/'/g, ' ').match(TOKEN) || [];
  A.contentTokens = (text) => {
    const c = cfg(); const out = [];
    for (const t of A.tokens(text)) {
      if (c.stop.has(t) || c.filler.has(t) || (t.length < 3 && !/^\d+$/.test(t) && !SHORT_OK.has(t))) continue;
      if (!out.includes(t)) out.push(t);
    }
    return out;
  };
  A.core = (text) => A.contentTokens(text).join(' ');
  A.stems = (text) => new Set(A.contentTokens(text).map(A.stem));
  A.levenshtein = (a, b) => {
    let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      for (let j = 1; j <= b.length; j++) cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] !== b[j - 1] ? 1 : 0)));
      prev = cur;
    }
    return prev[b.length];
  };
  A.fuzzyEqual = (a, b) => (a.length < 6 || b.length < 6 ? false : A.levenshtein(a, b) <= (Math.max(a.length, b.length) < 10 ? 1 : 2));
  A.stemRelated = (a, b) => { const [s, l] = a.length <= b.length ? [a, b] : [b, a]; return s.length >= 6 && l.startsWith(s); };
  A.dice = (a, b) => {
    const x = E.norm(a); const y = E.norm(b);
    const big = (s) => { const out = []; for (let i = 0; i < s.length - 1; i++) out.push(s.slice(i, i + 2)); return out; };
    const ba = big(x); const bb = big(y);
    if (!ba.length || !bb.length) return 0;
    const counts = new Map(); ba.forEach((g) => counts.set(g, (counts.get(g) || 0) + 1));
    let inter = 0;
    for (const g of bb) { const n = counts.get(g) || 0; if (n > 0) { counts.set(g, n - 1); inter++; } }
    return (2 * inter) / (ba.length + bb.length);
  };

  // ── Taxonomie métier (pai/ats/semantic.py) : jamais une preuve ──────────────────────────────────
  A.familyOfCategory = (term) => { const t = E.norm(term); return cfg().families.find((f) => f.category.includes(t)) || null; };
  A.familiesOfMember = (term) => { const t = E.norm(term); return cfg().families.filter((f) => f.members.includes(t)); };
  A.membersIn = (textNorm, fam, exclude = '') => { const ex = E.norm(exclude); return fam.members.filter((m) => m !== ex && E.containsTerm(textNorm, m)); };

  // ── Classement des exigences ──────────────────────────────────────────────────────────────────
  const startsWithAction = (text) => {
    const c = cfg(); const t = text.replace(/^vous (?:allez |serez |aurez |devrez )?/, '');
    if (c.ACTION_NOUN.test(t)) return true;
    const m = t.match(/^[a-z]+/); const w = m ? m[0] : '';
    return (w.length > 4 && w.endsWith('er') && !c.notVerbs.has(w)) || c.irReVerbs.has(w);
  };
  A.classifyRequirement = (text, section = '') => {
    const c = cfg(); const t = E.norm(text).replace(c.LEAD, '');
    if (!t) return 'CONTEXT';
    if (c.NICE.test(t.replace(/\([^)]*\)/g, ' '))) return 'NICE_TO_HAVE';
    const action = startsWithAction(t);
    if (c.CONTEXT_STRONG.test(t) && !action) return 'CONTEXT';
    if (c.MUST.test(t) || /\bessentiel|imperatif|exige/.test(t)) return 'MUST';
    if (action || section === 'profile' || section === 'mission') return 'IMPORTANT';
    if (section === 'company' || c.CONTEXT.test(t)) return 'CONTEXT';
    return 'IMPORTANT';
  };

  // ── Preuve ────────────────────────────────────────────────────────────────────────────────────
  const proof = (status = UNPROVEN, match = '', via = '', ids = [], extra = {}) => Object.assign({ status, match, via, fact_ids: ids.slice(), related: [], note: '' }, extra);
  const copyProof = (p) => Object.assign({}, p, { fact_ids: p.fact_ids.slice(), related: p.related.slice() });
  const better = (p, q) => RANK[p.status] > RANK[q.status] || (RANK[p.status] === RANK[q.status] && MATCH_RANK[p.match] > MATCH_RANK[q.match]);
  const implyingKey = (term, ev) => {
    const targets = E.synEquivalents(term);
    for (const [key, implied] of Object.entries(E.data().synonyms.implies)) if (implied.some((x) => targets.has(E.norm(x))) && E.containsTerm(ev, key)) return key;
    return '';
  };
  const languageOf = (t) => { for (const [w] of cfg().languages) if (E.containsTerm(t, w)) return w; return ''; };
  const levelOf = (t) => {
    let best = [0, ''];
    for (const [w, v] of cfg().levelWords) if (E.containsTerm(t, w) && (v > best[0] || (v === best[0] && w > best[1]))) best = [v, w];
    return best;
  };
  const proveLanguage = (t, word, evidence) => {
    const langs = cfg().languages; const code = (langs.find(([w]) => w === word) || [])[1];
    const names = langs.filter(([, c]) => c === code).map(([w]) => w);
    const [need, needW] = levelOf(t);
    const hits = evidence.filter(([, ev]) => names.some((n) => E.containsTerm(ev, n)));
    if (!hits.length) return proof(UNPROVEN, '', '', [], { note: `Aucun fait ne mentionne la langue « ${word} ».` });
    let have = [0, ''];
    for (const [, ev] of hits) { const l = levelOf(ev); if (l[0] > have[0] || (l[0] === have[0] && l[1] > have[1])) have = l; }
    const exact = hits.some(([, ev]) => E.containsTerm(ev, word));
    const ids = hits.map(([id]) => id).slice(0, 4);
    if (!need || have[0] >= need) return proof(PROVEN, exact ? 'EXACT' : 'SYNONYME', need ? 'langue et niveau prouvés' : 'langue prouvée', ids);
    if (!have[0]) return proof(PLAUSIBLE, 'SÉMANTIQUE', 'langue prouvée, niveau non précisé', ids, { note: `Niveau demandé : ${needW}. Préciser le niveau réel dans le profil.` });
    return proof(PLAUSIBLE, 'SÉMANTIQUE', 'langue prouvée, niveau inférieur', ids, { note: `Niveau demandé : ${needW} ; niveau prouvé : ${have[1]}. Ne pas surévaluer.` });
  };

  A.prove = (term, evidence) => {
    const t = E.norm(term); const c = A.core(term);
    if (!t) return proof();
    const lang = languageOf(t);
    if (lang) return proveLanguage(t, lang, evidence);
    let best = proof();
    for (const cand of [...new Set([t, c].filter(Boolean))]) {
      for (const [fid, ev] of evidence) {
        const how = E.supportedBy(cand, ev);
        if (!how) continue;
        let p;
        if (how === 'implique') {
          const key = implyingKey(cand, ev);
          p = proof(PLAUSIBLE, 'SÉMANTIQUE', key ? `déduit de « ${key} »` : 'déduction', [fid], { note: 'Déduction (règle déclarée), pas une mention explicite : formulation prudente.' });
        } else p = proof(PROVEN, how === 'direct' ? 'EXACT' : 'SYNONYME', how === 'direct' ? 'mention directe' : 'synonyme déclaré', [fid]);
        if (better(p, best)) best = p;
        else if (p.status === best.status && p.match === best.match && !best.fact_ids.includes(fid)) best.fact_ids.push(fid);
      }
    }
    if (best.status === PROVEN) { best.fact_ids = best.fact_ids.slice(0, 6); return best; }
    const key = c || t;
    const fam = A.familyOfCategory(key);
    if (fam && best.status === UNPROVEN) {
      for (const [fid, ev] of evidence) {
        const found = A.membersIn(ev, fam);
        if (found.length) { best = proof(PLAUSIBLE, 'SÉMANTIQUE', `« ${found[0]} » appartient à la famille ${fam.label}`, [fid], { note: 'Famille métier : pas une mention explicite.' }); break; }
      }
    }
    const related = [];
    for (const f of A.familiesOfMember(key)) for (const [, ev] of evidence) for (const m of A.membersIn(ev, f, key)) if (!related.includes(m)) related.push(m);
    best.related = related.slice(0, 4);
    const words = A.contentTokens(key); const need = new Set(words.map(A.stem));
    if (need.size && best.status === UNPROVEN) {
      for (const [fid, ev] of evidence) {
        const have = A.stems(ev);
        if ([...need].every((x) => have.has(x))) {
          best = need.size <= 2 ? proof(PROVEN, 'EXACT', 'forme proche', [fid]) : proof(PLAUSIBLE, 'SÉMANTIQUE', 'tous les mots présents, formulation différente', [fid]);
          break;
        }
      }
    }
    if (best.status === UNPROVEN && words.length) {
      const union = new Set(); for (const [, ev] of evidence) for (const s of A.stems(ev)) union.add(s);
      let hit;
      if (words.length === 1) { const w0 = A.stem(words[0]); hit = [...union].some((s) => A.stemRelated(w0, s) || A.fuzzyEqual(w0, s)) ? words.slice() : []; }
      else hit = words.filter((w) => union.has(A.stem(w)));
      if (hit.length && (words.length === 1 || (hit.length >= 2 && hit.length / words.length >= 0.5))) {
        const miss = words.filter((w) => !hit.includes(w));
        const ids = evidence.filter(([, ev]) => hit.some((w) => E.containsTerm(ev, w))).map(([id]) => id).slice(0, 3);
        best = proof(PLAUSIBLE, 'SÉMANTIQUE', `mots proches : ${hit.join(', ')}`, ids, { note: miss.length ? `non prouvé : ${miss.join(', ')}` : 'forme voisine, à vérifier' });
      }
    }
    if (best.status === UNPROVEN) {
      best.note = best.related.length ? `Compétence voisine prouvée : ${best.related.join(', ')}. À valoriser en entretien, ne pas l'écrire à la place de « ${term} ».`
        : 'Aucun fait ne le prouve : à ne pas écrire.';
    }
    return best;
  };
  A.proofStatusForTexts = (requirement, texts) => A.prove(requirement, texts.map((x, i) => [`t${i}`, E.norm(x)])).status;

  // ── Exigences d'une offre ─────────────────────────────────────────────────────────────────────
  const req = (id, text, term, kind, klass, source = '') => ({ id, text, term, kind, klass, source, proof: proof() });
  const asDict = (r) => ({ id: r.id, text: r.text, term: r.term, kind: r.kind, class: r.klass, source: r.source,
    proof: Object.assign({}, r.proof, { label: LABEL(r.proof.status) }), class_label: LABEL(r.klass) });
  A.displayTerm = (term) => { const t = String(term).trim(); if (/^[a-z0-9+#]{2,4}$/.test(t) && !/^\d+$/.test(t)) return t.toUpperCase(); return t.slice(0, 1).toUpperCase() + t.slice(1); };
  const sourceOf = (sents, term) => {
    const hits = sents.filter((s) => E.containsTerm(E.norm(s), term));
    return cps(hits.find((s) => cfg().MUST.test(E.norm(s))) || hits[0] || '', 200);
  };
  const asText = (x) => (typeof x === 'string' ? x : (x && (x.text || x.requirement)) || '');
  A.extract = (a, offerText = '') => {
    const c = cfg(); const sents = offerText ? E._sentences(offerText) : []; const out = [];
    const langs = new Map((a.languages || []).map((x) => [E.norm(x.name || ''), x]));
    for (const kw of a.keywords || []) {
      const lang = langs.get(E.norm(kw.term)); const level = lang ? String(lang.level || '') : '';
      const term = lang && !['', 'UNKNOWN'].includes(level) ? `${kw.term} ${level}`.trim() : kw.term;
      out.push(req(`kw.${E.hash(E.norm(kw.term))}`, A.displayTerm(term), term, lang ? 'language' : 'keyword', KEYWORD_CLASS[kw.priority] || 'IMPORTANT', sourceOf(sents, kw.term)));
    }
    const seen = new Set(out.map((r) => E.norm(r.text)));
    for (const [section, items] of [['profile', (a.recruiter_wants || {}).explicit || []], ['mission', a.missions || []]]) {
      for (const raw of items) {
        const s = asText(raw); if (!s || seen.has(E.norm(s))) continue;
        seen.add(E.norm(s));
        out.push(req(`${section.slice(0, 3)}.${E.hash(E.norm(s))}`, s, s, section === 'profile' ? 'sentence' : 'mission', A.classifyRequirement(s, section), s));
      }
    }
    if (a.degree_required && !['', 'UNKNOWN'].includes(a.degree_required)) {
      const src = sents.find((s) => c.DEGREE.test(E.norm(s))) || '';
      out.push(req('degree', `Diplôme : ${a.degree_required}`, a.degree_required, 'degree', c.MUST.test(E.norm(src)) ? 'MUST' : 'IMPORTANT', src));
    }
    if (a.experience_years_min) {
      const y = Number(a.experience_years_min); const src = sents.find((s) => c.YEARS.test(E.norm(s))) || '';
      out.push(req('experience', `Expérience : ${fmtG(y)} an${y > 1 ? 's' : ''} minimum`, String(y), 'experience', c.NICE.test(E.norm(src)) ? 'NICE_TO_HAVE' : 'MUST', src));
    }
    return out;
  };
  const evidenceOf = (P) => E.factIndex(P).map(([f, text]) => [f.id, text]);
  const DEG_LEVELS = [[5, 'Bac+5', /\bmaster\b|\bmsc\b|bac\s?\+\s?5|\bm2\b|grande ecole|ingenieur/], [4, 'Bac+4', /bac\s?\+\s?4|\bm1\b|master 1/],
    [3, 'Bac+3', /bachelor|licence|bac\s?\+\s?3|\bbut\b/], [2, 'Bac+2', /\bbts\b|\bdut\b|bac\s?\+\s?2/], [1, 'Bac', /\bbac\b|baccalaureat/]];
  const profileDegree = (P) => { const t = E.norm(P.byKind('education').map((f) => f.text).join(' ')); for (const [lv, label, re] of DEG_LEVELS) if (re.test(t)) return [lv, label]; return [0, '']; };
  const proveDegree = (P, required) => {
    const need = ({ 'Bac+5': 5, 'Bac+4': 4, 'Bac+3': 3, 'Bac+2': 2, Bac: 1 })[required] || 0;
    const [have, label] = profileDegree(P); const ids = P.byKind('education').map((f) => f.id).slice(0, 3);
    if (need && have >= need) return proof(PROVEN, 'EXACT', `diplôme prouvé : ${label}`, ids);
    return proof(UNPROVEN, '', '', ids, { note: `Niveau demandé : ${required} ; niveau prouvé : ${label || 'aucun diplôme renseigné'}. Ne jamais ajouter ni gonfler un diplôme.` });
  };
  const proveYears = (P, years) => {
    const exps = P.experiences(); const months = exps.reduce((n, e) => n + E._months(e.data.start, e.data.end), 0);
    const have = months / 12; const ids = exps.map((e) => e.id).slice(0, 4);
    const text = `${fixed1(have).replace('.', ',')} ${have >= 2 ? 'ans' : 'an'} d'expérience cumulée pour ${fmtG(years)} ${years >= 2 ? 'ans demandés' : 'an demandé'}`;
    if (have >= years) return proof(PROVEN, 'EXACT', text, ids);
    if (have >= 0.6 * years) return proof(PLAUSIBLE, 'SÉMANTIQUE', text, ids, { note: "Durée un peu courte : mettre en avant l'intensité et les résultats." });
    return proof(UNPROVEN, '', '', ids, { note: `${text}.` });
  };
  const sentenceWords = (text) => A.contentTokens(text).filter((w) => !cfg().contextWords.has(w) && !/^\d+(?:[.,]\d+)?k?$/.test(w));
  const containsKeyword = (tn, sentStems, r) => {
    const base = r.kind === 'language' ? r.term.split(' ')[0] : r.term;
    const kst = new Set(A.contentTokens(base).map(A.stem));
    return E.containsTerm(tn, base) || (kst.size > 0 && [...kst].every((x) => sentStems.has(x)));
  };
  const proveSentence = (text, kwReqs, evidence, special) => {
    const c = cfg(); const tn = E.norm(text);
    if (special.degree && c.DEGREE.test(tn)) return copyProof(special.degree);
    if (special.experience && c.YEARS.test(tn)) return copyProof(special.experience);
    const words = sentenceWords(text); const st = new Set(words.map(A.stem));
    const inside = kwReqs.filter((r) => containsKeyword(tn, st, r));
    const union = new Set(); for (const [, ev] of evidence) for (const s of A.stems(ev)) union.add(s);
    const covered = words.filter((w) => { const s = A.stem(w); return union.has(s) || [...union].some((u) => A.stemRelated(s, u)); });
    const share = words.length ? covered.length / words.length : 0;
    const firstOk = words.length > 0 && covered.includes(words[0]);
    let ids = []; for (const r of inside) for (const i of r.proof.fact_ids) if (!ids.includes(i)) ids.push(i);
    const missing = words.filter((w) => !covered.includes(w));
    const note = missing.length ? `non prouvé : ${missing.slice(0, 6).join(', ')}` : '';
    const byCovered = () => evidence.filter(([, ev]) => covered.some((w) => E.containsTerm(ev, w))).map(([id]) => id).slice(0, 3);
    if (words.length && words.every((w) => c.soft.has(w))) return proof(UNPROVEN, '', '', [], { note: 'Qualités personnelles : aucune preuve écrite possible, à illustrer en entretien par un exemple réel.' });
    if (words.length && firstOk && share >= 0.5 && inside.every((r) => r.proof.status === PROVEN) && (inside.length || share >= 0.75)) {
      const worst = inside.length ? inside.map((r) => r.proof.match).reduce((m, x) => (MATCH_RANK[x] < MATCH_RANK[m] ? x : m)) : 'EXACT';
      const via = inside.length ? `mots-clés prouvés : ${inside.map((r) => r.term).join(', ')}` : 'mots présents dans les faits';
      if (!ids.length) ids = byCovered();
      return proof(PROVEN, worst, via, ids.slice(0, 6), { note });
    }
    if (inside.some((r) => r.proof.status !== UNPROVEN) || share >= 0.34 || firstOk) {
      const via = inside.length ? `mots-clés : ${inside.map((r) => `${r.term} (${LABEL(r.proof.status).toLowerCase()})`).join(', ')}` : `mots proches : ${covered.slice(0, 6).join(', ')}`;
      if (!ids.length) ids = byCovered();
      return proof(PLAUSIBLE, 'SÉMANTIQUE', via, ids.slice(0, 6), { note });
    }
    return proof(UNPROVEN, '', '', [], { note: "Aucun fait ne le prouve : à préparer pour l'entretien, à ne pas écrire." });
  };
  A.proveAll = (reqs, P, a) => {
    const evidence = evidenceOf(P);
    const kws = reqs.filter((r) => r.kind === 'keyword' || r.kind === 'language');
    for (const r of kws) r.proof = A.prove(r.term, evidence);
    const special = {};
    for (const r of reqs) {
      if (r.kind === 'degree') { special.degree = proveDegree(P, a.degree_required); r.proof = special.degree; }
      else if (r.kind === 'experience') { special.experience = proveYears(P, Number(r.term)); r.proof = special.experience; }
    }
    for (const r of reqs) {
      if (r.klass === 'CONTEXT') r.proof = proof(UNPROVEN, '', '', [], { note: 'Information sur le poste : aucune preuve attendue.' });
      else if (r.kind === 'sentence' || r.kind === 'mission') r.proof = proveSentence(r.text, kws, evidence, special);
    }
    return reqs;
  };
  A.coverage = (reqs) => {
    let total = 0; let got = 0;
    for (const r of reqs) { total += CLASS_WEIGHT[r.klass]; got += CLASS_WEIGHT[r.klass] * STATUS_VALUE[r.proof.status]; }
    return total ? round1((100 * got) / total) : 0;
  };

  // ── Score PAI (pai/ats/scoring.py) ────────────────────────────────────────────────────────────
  A.crit = (label, status, detail = '', value = null) => { const d = { label, status, detail }; if (value !== null && value !== undefined) d.value = pyRound(value); return d; };
  A.dimension = (mode, id, value, details, summary = '', measured = true) => {
    const c = cfg().scoring[mode][id]; const has = value !== null && value !== undefined;
    return { id, label: c.label, help: c.help, weight: c.weight, value: has ? Math.max(0, Math.min(100, pyRound(value))) : null, available: has, measured, summary, details };
  };
  A.globalScore = (dims) => {
    const avail = dims.filter((d) => d.available); const total = avail.reduce((n, d) => n + d.weight, 0);
    const missing = dims.filter((d) => !d.available).map((d) => d.label);
    return { value: total ? pyRound(avail.reduce((n, d) => n + d.value * d.weight, 0) / total) : null, complete: !missing.length, missing,
      disclaimer: cfg().scoring.disclaimer,
      formula: avail.map((d) => `${d.label} × ${d.weight} %`).join(' + ') + (missing.length ? ` (renormalisé : ${missing.join(', ')} non mesuré)` : '') };
  };
  A.structureFromDoc = (cv) => {
    const secs = new Set(cv.lines.map((l) => l.section)); const details = []; let pts = 0; let total = 0;
    for (const [sid, label, w] of [['headline', 'Titre du CV', 10], ['summary', 'Profil', 10], ['experience', 'Expérience', 25], ['education', 'Formation', 15], ['skills', 'Compétences', 15], ['languages', 'Langues', 5]]) {
      const ok = secs.has(sid) || (sid === 'languages' && secs.has('certifications'));
      total += w; pts += ok ? w : 0;
      details.push(A.crit(label, ok ? OK : ['summary', 'languages'].includes(sid) ? WARNING : ERROR, ok ? 'présente' : 'absente'));
    }
    const blocks = cv.experiences.filter((b) => (b.bullet_ids || []).length); const dated = blocks.filter((b) => b.period);
    total += 10; pts += blocks.length ? 10 * (dated.length / blocks.length) : 0;
    details.push(A.crit('Expériences datées', blocks.length && dated.length === blocks.length ? OK : WARNING, `${dated.length}/${blocks.length}`));
    const good = blocks.filter((b) => b.bullet_ids.length >= 1 && b.bullet_ids.length <= 6);
    total += 10; pts += blocks.length ? 10 * (good.length / blocks.length) : 0;
    details.push(A.crit('Puces par expérience (1 à 6)', blocks.length && good.length === blocks.length ? OK : WARNING, `${good.length}/${blocks.length} expériences`));
    const contact = (cv.contact || []).join(' '); const mail = contact.includes('@'); const phone = /\d{2}[\s.]?\d{2}[\s.]?\d{2}/.test(contact);
    total += 10; pts += 5 * mail + 5 * phone;
    details.push(A.crit('Coordonnées (e-mail, téléphone)', mail && phone ? OK : !mail ? ERROR : WARNING, [['e-mail', mail], ['téléphone', phone]].filter(([, ok]) => ok).map(([x]) => x).join(', ') || 'absentes'));
    return [(100 * pts) / total, details];
  };
  A.docText = (cv) => [cv.name, ...(cv.contact || []), ...cv.lines.map((l) => l.text), ...cv.experiences.map((b) => `${b.title} ${b.company}`)].join('\n');
  const KW = { REQUIRED: 3, IMPORTANT: 2, NICE: 1 }; const kwW = (p) => (KW[p] === undefined ? 2 : KW[p]);
  A.keywordEntries = (a, reqs, cvText) => {
    const byTerm = new Map();
    for (const r of reqs) if (r.kind === 'keyword' || r.kind === 'language') byTerm.set(E.norm(r.kind === 'language' ? r.term.split(' ')[0] : r.term), r);
    const textN = E.norm(cvText || ''); const has = !!cvText;
    return (a.keywords || []).map((kw) => {
      const r = byTerm.get(E.norm(kw.term)); const status = r ? r.proof.status : UNPROVEN;
      const present = has && [...E.synEquivalents(kw.term)].some((f) => E.containsTerm(textN, f));
      let why;
      if (present && status === PROVEN) why = 'Présent : prouvé par tes faits.';
      else if (present && status === PLAUSIBLE) why = `Présent sous une forme prudente : ${r.proof.via}.`;
      else if (present) why = 'Présent dans le CV source, mais aucun fait du profil ne le prouve : à vérifier.';
      else if (status === PROVEN) why = has ? 'Prouvé mais pas encore dans le CV : à placer (place limitée ou priorité faible).' : 'Prouvé par le profil.';
      else if (status === PLAUSIBLE) why = `Pas ajouté tel quel : ${r.proof.via}. À formuler prudemment ou à préparer pour l'entretien.`;
      else {
        why = "Pas ajouté : aucun fait ne le prouve. L'écrire gonflerait le score au prix de la vérité.";
        if (r && r.proof.related.length) why += ` Compétence voisine prouvée : ${r.proof.related.join(', ')}.`;
      }
      return { term: kw.term, priority: kw.priority, class: ({ REQUIRED: 'MUST', NICE: 'NICE_TO_HAVE' })[kw.priority] || 'IMPORTANT', status,
        status_label: LABEL(status), in_cv: present, match: r ? r.proof.match : '', fact_ids: r ? r.proof.fact_ids.slice(0, 4) : [], why };
    });
  };
  A.keywordsDim = (entries, hasCv) => {
    if (!entries.length) return [null, [], "Aucun mot-clé extrait de l'offre."];
    const total = entries.reduce((n, e) => n + kwW(e.priority), 0); let got; let summary;
    if (hasCv) {
      got = entries.filter((e) => e.in_cv).reduce((n, e) => n + kwW(e.priority), 0);
      summary = `${entries.filter((e) => e.in_cv).length}/${entries.length} mots-clés présents dans le CV`;
    } else {
      got = entries.reduce((n, e) => n + kwW(e.priority) * (e.status === PROVEN ? 1 : e.status === PLAUSIBLE ? 0.5 : 0), 0);
      summary = `${entries.filter((e) => e.status === PROVEN).length}/${entries.length} mots-clés prouvés par le profil (avant CV)`;
    }
    const details = entries.map((e) => A.crit(e.term, (hasCv ? e.in_cv : e.status === PROVEN) ? OK : e.status !== UNPROVEN ? WARNING : ERROR, e.why));
    return [(100 * got) / total, details, summary];
  };
  A.matchingDim = (reqs) => {
    const scored = reqs.filter((r) => r.klass !== 'CONTEXT');
    if (!scored.length) return [null, [], 'Aucune exigence exploitable.'];
    const details = [];
    for (const k of ['MUST', 'IMPORTANT', 'NICE_TO_HAVE']) {
      const rs = scored.filter((r) => r.klass === k); if (!rs.length) continue;
      const p = rs.filter((r) => r.proof.status === PROVEN).length; const q = rs.filter((r) => r.proof.status === PLAUSIBLE).length;
      details.push(A.crit(LABEL(k), p === rs.length ? OK : p + q === rs.length ? WARNING : ERROR,
        `${p}/${rs.length} prouvées · ${q} possibles · ${rs.length - p - q} non prouvées`, (100 * (p + 0.5 * q)) / rs.length));
    }
    const must = scored.filter((r) => r.klass === 'MUST'); const mustOk = must.filter((r) => r.proof.status === PROVEN).length;
    const summary = must.length ? `${mustOk}/${must.length} exigences obligatoires prouvées` : `${scored.filter((r) => r.proof.status === PROVEN).length}/${scored.length} exigences prouvées`;
    return [A.coverage(scored), details, summary];
  };
  const sc = (m, k, d) => (m.scores && m.scores[k] !== undefined && m.scores[k] !== null ? m.scores[k] : d);
  A.experienceDim = (m, reqs) => {
    const value = 0.4 * sc(m, 'role', 50) + 0.35 * sc(m, 'experience', 50) + 0.25 * sc(m, 'seniority', 50);
    const years = reqs.find((r) => r.kind === 'experience');
    const details = [A.crit('Intitulés proches du poste', sc(m, 'role', 0) >= 75 ? OK : WARNING, '', m.scores.role),
      A.crit("Durée d'expérience", sc(m, 'experience', 0) >= 80 ? OK : WARNING, years ? years.proof.via || years.proof.note : 'aucune durée exigée', m.scores.experience),
      A.crit('Séniorité', sc(m, 'seniority', 0) >= 70 ? OK : WARNING, '', m.scores.seniority)];
    return [value, details, "rôle, durée et niveau comparés à l'offre"];
  };
  A.educationDim = (m, reqs, a) => {
    const r = reqs.find((x) => x.kind === 'degree'); const deg = sc(m, 'degree', 70);
    if (!r) return [deg, [A.crit('Diplôme', OK, "aucun niveau exigé par l'offre")], 'aucun niveau exigé'];
    return [deg, [A.crit(`Diplôme demandé : ${a.degree_required}`, r.proof.status === PROVEN ? OK : ERROR, r.proof.via || r.proof.note)], LABEL(r.proof.status)];
  };
  A.languagesDim = (m, reqs) => {
    const langs = reqs.filter((r) => r.kind === 'language');
    if (!langs.length) return [sc(m, 'language', 80), [A.crit('Langues', OK, "aucune langue exigée par l'offre")], 'aucune langue exigée'];
    const details = langs.map((r) => A.crit(r.text, r.proof.status === PROVEN ? OK : r.proof.status === PLAUSIBLE ? WARNING : ERROR, r.proof.note || r.proof.via));
    const w = new Map(langs.map((r) => [r.id, CLASS_WEIGHT[r.klass] || 1]));
    const num = langs.reduce((n, r) => n + w.get(r.id) * STATUS_VALUE[r.proof.status], 0);
    const den = [...w.values()].reduce((n, x) => n + x, 0);
    const proven = langs.filter((r) => r.proof.status === PROVEN).length;
    return [(100 * num) / den, details, `${proven}/${langs.length} ${langs.length > 1 ? 'langues prouvées' : 'langue prouvée'}`];
  };
  A.conditionsDim = (m, a) => {
    const loc = sc(m, 'location', 60); const con = sc(m, 'contract', 70); const av = sc(m, 'availability', 60);
    const details = [A.crit(`Lieu : ${a.location !== 'UNKNOWN' ? a.location : 'non précisé'}`, loc >= 80 ? OK : loc >= 50 ? WARNING : ERROR,
      loc >= 80 ? 'dans la mobilité déclarée' : loc >= 50 ? 'mobilité à confirmer' : 'hors mobilité déclarée', loc),
    A.crit(`Contrat : ${a.contract !== 'UNKNOWN' ? a.contract : 'non précisé'}`, con >= 75 ? OK : WARNING, '', con),
    A.crit('Disponibilité', av >= 80 ? OK : WARNING, av >= 80 ? 'déclarée dans le profil' : 'non renseignée', av)];
    return [0.5 * loc + 0.3 * con + 0.2 * av, details, 'lieu, contrat, disponibilité'];
  };
  A.factualityDim = (rep) => {
    if (!rep || !rep.total) return [null, [], 'mesurée sur le CV généré'];
    const rejected = (rep.verdicts || []).filter((v) => !v.ok);
    const details = [A.crit('Lignes prouvées', rep.traced === rep.total ? OK : ERROR, `${rep.traced}/${rep.total}`),
      A.crit('Termes interdits', !rep.forbidden_hits ? OK : ERROR, String(rep.forbidden_hits || 0))];
    for (const v of rejected.slice(0, 6)) details.push(A.crit(`Ligne retirée (${v.line_id})`, ERROR, (v.reasons || []).join('; ')));
    return [rep.factuality, details, `${rep.traced}/${rep.total} lignes prouvées`];
  };

  // ── Rapport « CV + offre » (pai/ats/report.py, mode B) ────────────────────────────────────────
  const item = (kind, text, extra = {}) => Object.assign({ kind, text }, extra);
  A.requirementsView = (reqs) => {
    const view = { proven: [], plausible: [], unproven: [], context: [] }; const order = { MUST: 0, IMPORTANT: 1, NICE_TO_HAVE: 2, CONTEXT: 3 };
    for (const r of reqs.slice().sort((x, y) => order[x.klass] - order[y.klass])) {
      const key = r.klass === 'CONTEXT' ? 'context' : ({ [PROVEN]: 'proven', [PLAUSIBLE]: 'plausible', [UNPROVEN]: 'unproven' })[r.proof.status];
      view[key].push(asDict(r));
    }
    return view;
  };
  A.strengthsAndGaps = (reqs, kws, dims, hasCv) => {
    const strengths = []; const improve = [];
    for (const r of reqs) {
      if (r.klass === 'CONTEXT') continue;
      const label = LABEL(r.klass).toLowerCase();
      if (r.proof.status === PROVEN && ['MUST', 'IMPORTANT'].includes(r.klass) && ['keyword', 'language', 'degree', 'experience'].includes(r.kind)) strengths.push(item('fait', `${r.text} : prouvé (${label})`, { fact_ids: r.proof.fact_ids.slice(0, 3) }));
      else if (r.proof.status === UNPROVEN && r.klass === 'MUST') improve.push(item('fait', `${r.text} : exigence obligatoire non prouvée`, { note: r.proof.note }));
      else if (r.proof.status === PLAUSIBLE && r.klass === 'MUST') improve.push(item('interpretation', `${r.text} : correspondance possible seulement (${r.proof.via})`, { note: r.proof.note }));
    }
    for (const k of kws) if (hasCv && k.status === PROVEN && !k.in_cv && k.priority !== 'NICE') improve.push(item('suggestion', `Placer « ${k.term} » dans le CV : c'est prouvé par tes faits.`, { fact_ids: k.fact_ids.slice(0, 2) }));
    for (const d of dims) if (d.available && d.value !== null && d.value < 60 && ['parsing', 'structure'].includes(d.id)) for (const c of d.details.filter((x) => x.status !== OK).slice(0, 2)) improve.push(item('suggestion', `${d.label} — ${c.label} : ${c.detail}`));
    return [strengths.slice(0, 8), improve.slice(0, 10)];
  };
  A.MAIN = ['parsing', 'structure', 'matching', 'keywords', 'experience', 'factuality'];
  // opts : { cv, validation (rapport du validateur), scan ({score, checks}), cvText }
  A.matchReport = (P, a, m, offerText = '', opts = {}) => {
    const reqs = A.proveAll(A.extract(a, offerText), P, a);
    const cv = opts.cv || null;
    const cvText = opts.cvText !== undefined && opts.cvText !== null ? opts.cvText : cv ? A.docText(cv) : null;
    const kws = A.keywordEntries(a, reqs, cvText); const dims = [];
    let r = A.matchingDim(reqs); dims.push(A.dimension('match', 'matching', r[0], r[1], r[2]));
    r = A.keywordsDim(kws, cvText !== null); dims.push(A.dimension('match', 'keywords', r[0], r[1], r[2], cvText !== null));
    r = A.experienceDim(m, reqs); dims.push(A.dimension('match', 'experience', r[0], r[1], r[2]));
    const scan = opts.scan || null;
    if (scan) dims.push(A.dimension('match', 'parsing', scan.score, scan.checks.map((c) => A.crit(c.label, c.status, c.detail)), `${scan.checks.filter((c) => c.status === OK).length}/${scan.checks.length} contrôles OK sur le PDF réel`));
    else dims.push(A.dimension('match', 'parsing', null, [], 'mesuré sur le PDF généré'));
    r = A.factualityDim(opts.validation || null); dims.push(A.dimension('match', 'factuality', r[0], r[1], r[2]));
    if (cv) { const [sv, sd] = A.structureFromDoc(cv); dims.push(A.dimension('match', 'structure', sv, sd, `${sd.filter((c) => c.status === OK).length}/${sd.length} critères`)); }
    else dims.push(A.dimension('match', 'structure', null, [], 'mesurée sur le CV généré'));
    r = A.educationDim(m, reqs, a); dims.push(A.dimension('match', 'education', r[0], r[1], r[2]));
    r = A.languagesDim(m, reqs); dims.push(A.dimension('match', 'languages', r[0], r[1], r[2]));
    r = A.conditionsDim(m, a); dims.push(A.dimension('match', 'conditions', r[0], r[1], r[2]));
    const rank = (d) => (A.MAIN.includes(d.id) ? A.MAIN.indexOf(d.id) : 99);
    dims.sort((x, y) => rank(x) - rank(y));
    const [strengths, improvements] = A.strengthsAndGaps(reqs, kws, dims, cvText !== null);
    return { mode: cv || cvText ? 'cv_offer' : 'profile_offer', engine: { version: 'ats-1', rules: (E.data().version || {}).rules || '' },
      offer: { title: a.job_title, company: a.company, location: a.location, contract: a.contract, remote: a.remote },
      score: Object.assign(A.globalScore(dims), { label: 'Score PAI' }), dimensions: dims, main: A.MAIN.slice(), strengths, improvements,
      requirements: A.requirementsView(reqs), keywords: kws, variant: A.selectVariant(a.job_title, a.sector_id) };
  };

  // ── Variantes de CV (pai/ats/variants.py) ─────────────────────────────────────────────────────
  A.selectVariant = (title, sectorId = '') => {
    const v = cfg().variants; const t = E.norm(title);
    const out = (id, why) => { const x = v.variants[id]; return { id, label: x.label, angle: x.angle || '', skill_groups: x.skill_groups || [], why }; };
    for (const id of v.order || []) { const hit = (v.variants[id].title || []).find((w) => E.containsTerm(t, w)); if (hit) return out(id, `intitulé « ${title} » (mot repère : ${hit})`); }
    for (const id of v.order || []) if (sectorId && (v.variants[id].sectors || []).includes(sectorId)) return out(id, `secteur de l'offre (${sectorId})`);
    return out('MASTER', "aucun repère d'intitulé ou de secteur : CV maître");
  };

  // ── Changements AVANT / APRÈS / RAISON / PREUVE (pai/ats/changes.py) ──────────────────────────
  const SECTIONS = { headline: 'Titre', summary: 'Profil', experience: 'Expérience', skills: 'Compétences', education: 'Formation', certifications: 'Certifications', languages: 'Langues', extras: 'Informations' };
  const stripChars = (s, chars) => { let a = 0; let b = s.length; while (a < b && chars.includes(s[a])) a++; while (b > a && chars.includes(s[b - 1])) b--; return s.slice(a, b); };
  A.changes = (cv, P, originalText = '') => {
    const original = String(originalText || '').split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/).filter((ln) => ln.trim().length > 3).map((ln) => stripChars(ln, ' -•·*'));
    const changes = []; let unchanged = 0; const used = new Set();
    const tr = P.fact('target.roles'); const roles = ((tr && tr.data && tr.data.roles) || []).map(E.norm);
    for (const ln of cv.lines) {
      const facts = (ln.fact_ids || []).map((id) => P.fact(id)).filter(Boolean);
      facts.forEach((f) => used.add(f.id));
      let before;
      if (original.length) {
        let best = ''; let score = 0;
        for (const o of original) { const d = A.dice(ln.text, o); if (d > score) { best = o; score = d; } }
        before = score >= 0.5 ? best : '';
      } else before = facts.length && ln.section !== 'headline' ? facts[0].text : '';
      if (E.norm(before).replace(/\.+$/, '') === E.norm(ln.text).replace(/\.+$/, '')) { unchanged++; continue; }
      let reason;
      if (ln.section === 'headline') {
        const nt = E.norm(ln.text); const declared = roles.some((r) => r && (nt.includes(r) || r.includes(nt)));
        reason = declared ? 'Titre aligné sur le poste visé, qui fait partie des rôles déclarés du profil.' : "Titre = intitulé du poste visé par cette candidature (ce n'est pas un poste déjà occupé).";
      } else if ((ln.offer_terms || []).length) reason = `Reprend les mots de l'offre : ${ln.offer_terms.slice(0, 4).join(', ')}.`;
      else if (!before) reason = "Ajoutée depuis le profil : ce fait prouve une exigence de l'offre.";
      else if (facts.length > 1) reason = `Rassemble ${facts.length} faits du profil en une ligne (aucun ajout).`;
      else if (A.dice(before, ln.text) >= 0.75) reason = 'Mise en forme (même fait, même sens).';
      else reason = 'Reformulée pour être plus directe (même fait, même sens).';
      changes.push({ line_id: ln.id, section: SECTIONS[ln.section] || ln.section, before, after: ln.text, reason, proof: facts.map((f) => ({ id: f.id, text: f.text, status: f.status })) });
    }
    const dropped = [];
    for (const exp of P.experiences()) {
      const left = P.children(exp.id).filter((c) => ['result', 'responsibility'].includes(c.kind) && !used.has(c.id));
      if (left.length) dropped.push({ experience: exp.data.company || exp.text, count: left.length, reason: 'Moins liées à cette offre (place limitée) ; elles restent dans le CV maître.' });
    }
    return { changes, unchanged, dropped, rule: "Aucune ligne sans preuve : chaque APRÈS cite les faits qui l'autorisent." };
  };

  E.ATS = A;
  if (typeof module !== 'undefined' && module.exports) module.exports = E;
}(typeof globalThis !== 'undefined' ? globalThis : this));
