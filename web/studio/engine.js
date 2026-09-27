/* PAI Studio — moteur (logique pure, testable sous Node).
 * Port fidèle du moteur Python (pai/claims.py, analyzer.py, matching.py, strategy.py,
 * cv_architect.py, letter.py, critic.py). Parité vérifiée par tests/golden/*.json.
 * Aucune dépendance au DOM ni au réseau. Les règles (secteurs, pays, synonymes, prompts…)
 * sont injectées au build dans PAI_DATA.
 */
(function (root) {
  'use strict';
  const E = {};

  // ─── Texte ────────────────────────────────────────────────────────────────
  const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  E.stripAccents = (s) => String(s).normalize('NFKD').replace(/[̀-ͯ]/g, '');
  E.norm = (s) => {
    if (s === null || s === undefined || s === '') return '';
    return E.stripAccents(String(s)).toLowerCase()
      .replace(/[’‘`´‛]/g, "'").replace(/[–—‑−‐]/g, '-')
      .replace(/œ/g, 'oe').replace(/æ/g, 'ae')
      .replace(/[\s   ]+/g, ' ').trim();
  };
  E.pluralVariants = (t) => {
    if (!t) return [];
    const variants = new Set([t]);
    const parts = t.split(' ');
    const last = parts[parts.length - 1];
    const head = t.slice(0, t.length - last.length);
    if (last.length > 3) {
      if (last.endsWith('s') || last.endsWith('x')) variants.add(head + last.slice(0, -1));
      else variants.add(head + last + 's');
    }
    return [...variants].sort();
  };
  const patCache = new Map();
  E.containsTerm = (hayNorm, term) => {
    const t = E.norm(term);
    if (!t) return false;
    for (const v of E.pluralVariants(t)) {
      let re = patCache.get(v);
      if (!re) { re = new RegExp('(?<![a-z0-9])' + escRe(v) + '(?![a-z0-9])'); patCache.set(v, re); }
      if (re.test(hayNorm)) return true;
    }
    return false;
  };
  const NUM_WORDS = [['deux', '2'], ['trois', '3'], ['quatre', '4'], ['cinq', '5'], ['six', '6'], ['huit', '8'], ['neuf', '9'],
    ['dix', '10'], ['onze', '11'], ['douze', '12'], ['quinze', '15'], ['vingt', '20'], ['trente', '30'], ['quarante', '40'],
    ['cinquante', '50'], ['cent', '100'], ['mille', '1000'], ['two', '2'], ['three', '3'], ['four', '4'], ['five', '5'],
    ['ten', '10'], ['twenty', '20'], ['hundred', '100'], ['double', '2'], ['doubler', '2'], ['triple', '3'], ['tripler', '3']];
  const NUMBER = /(?<![a-z0-9])(\d{1,3}(?:[ .]\d{3})+|\d+(?:[.,]\d+)?)(?![0-9])/g;
  E.extractNumbers = (text) => {
    const t = E.norm(text);
    const out = [];
    for (const m of t.matchAll(NUMBER)) {
      const raw = m[1];
      let c = /^\d{1,3}(?:[ .]\d{3})+$/.test(raw) ? raw.replace(/[ .]/g, '') : raw;
      c = c.replace(',', '.');
      if (c.includes('.')) c = c.replace(/0+$/, '').replace(/\.$/, '') || '0';
      out.push(c);
    }
    for (const [w, v] of NUM_WORDS) if (E.containsTerm(t, w)) out.push(v);
    return out;
  };
  E.hash = (str) => { // FNV-1a 32 bits → base36 (identifiants, pas de sécurité)
    let h = 0x811c9dc5;
    const s = typeof str === 'string' ? str : JSON.stringify(str);
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h.toString(36).padStart(7, '0');
  };
  E.unique = (items) => { const seen = new Set(); const out = []; for (const it of items) { const k = E.norm(it); if (it && !seen.has(k)) { seen.add(k); out.push(it); } } return out; };
  E.wordCount = (t) => (String(t || '').match(/[\wÀ-ÖØ-öø-ÿ'’-]+/g) || []).length;
  const cap = (t) => { t = String(t || '').trim().replace(/\.$/, ''); return t ? t[0].toUpperCase() + t.slice(1) : t; };
  const lowerFirst = (t) => (t && !/^[A-Z]{2}/.test(t) ? t[0].toLowerCase() + t.slice(1) : t);
  E.cap = cap;

  // ─── Règles ───────────────────────────────────────────────────────────────
  let DATA = null;
  E.setData = (d) => { DATA = d; patCache.clear(); };
  E.data = () => DATA;
  const sector = (id) => DATA.sectors[id] || DATA.sectors.commercial || {};
  const country = (code) => {
    const k = String(code || '').toUpperCase();
    for (const c of Object.values(DATA.countries)) if (String(c.code || '').toUpperCase() === k) return c;
    return DATA.countries._default || {};
  };
  const design = (id) => DATA.designs[id] || DATA.designs.hybrid_modern;
  E.sector = sector; E.country = country; E.design = design;

  E.synEquivalents = (term) => {
    const t = E.norm(term);
    const out = new Set([t]);
    for (const g of DATA.synonyms.equivalents) { const n = g.map(E.norm); if (n.includes(t)) n.forEach((x) => out.add(x)); }
    return out;
  };
  E.supportedBy = (term, evidenceNorm) => {
    if (E.containsTerm(evidenceNorm, term)) return 'direct';
    const t = E.norm(term);
    const eqs = E.synEquivalents(term);
    for (const eq of eqs) if (eq !== t && E.containsTerm(evidenceNorm, eq)) return 'synonyme';
    for (const [key, implied] of Object.entries(DATA.synonyms.implies)) {
      const imp = new Set(implied.map(E.norm));
      let hit = imp.has(t);
      if (!hit) for (const e of eqs) if (imp.has(e)) { hit = true; break; }
      if (hit && E.containsTerm(evidenceNorm, key)) return 'implique';
    }
    return null;
  };
  E.bannedFound = (text) => {
    const t = E.norm(text);
    return { hard: DATA.banned.hard.filter((p) => E.norm(p) && t.includes(E.norm(p))), soft: DATA.banned.soft.filter((p) => E.norm(p) && t.includes(E.norm(p))) };
  };

  // ─── Profil ───────────────────────────────────────────────────────────────
  const USABLE = new Set(['CONFIRMED', 'IMPORTED']);
  E.usable = (f) => !!f && (USABLE.has(f.status) || (f.status === 'INFERRED' && f.approved));
  E.P = (profile) => {
    const byId = new Map(profile.facts.map((f) => [f.id, f]));
    const P = {
      raw: profile,
      fact: (id) => byId.get(id) || null,
      usableFacts: () => profile.facts.filter(E.usable),
      byKind: (...kinds) => profile.facts.filter((f) => kinds.includes(f.kind) && E.usable(f)),
      children: (pid) => profile.facts.filter((f) => f.parent === pid && E.usable(f)),
      experiences: () => P.byKind('experience').slice().sort((a, b) => String(b.data.start || '0000').localeCompare(String(a.data.start || '0000'))),
      forbiddenTerms: () => profile.facts.filter((f) => f.status === 'FORBIDDEN').flatMap((f) => (f.terms && f.terms.length ? f.terms : [f.text])),
      value: (id, dflt = '') => { const f = byId.get(id); return f && E.usable(f) ? f.text : dflt; },
    };
    return P;
  };

  // ─── Lexiques du validateur (identiques à pai/claims.py) ─────────────────
  const TOOLS = ['hubspot', 'salesforce', 'pipedrive', 'zoho', 'sap', 'oracle', 'sage', 'odoo', 'dynamics', 'microsoft dynamics',
    'sales navigator', 'linkedin sales navigator', 'lemlist', 'kaspr', 'lusha', 'dropcontact', 'apollo', 'zapier',
    'excel', 'powerpoint', 'microsoft word', 'power bi', 'tableau software', 'looker', 'google analytics', 'google ads', 'meta ads',
    'seo', 'sem', 'wordpress', 'shopify', 'prestashop', 'wix', 'webflow', 'figma', 'photoshop', 'illustrator',
    'indesign', 'canva', 'notion', 'trello', 'asana', 'jira', 'slack', 'microsoft teams', 'python', 'sql', 'crm', 'erp', 'ats',
    'google suite', 'google workspace', 'mailchimp', 'brevo', 'sendinblue', 'hootsuite', 'chatgpt', 'welcome to the jungle'];
  const DEGREES = ['mba', 'master', 'mastere', 'msc', 'licence', 'bachelor', 'bts', 'doctorat', 'phd', 'deug',
    'bac+2', 'bac+3', 'bac+4', 'bac+5', 'bac +2', 'bac +3', 'bac +4', 'bac +5', 'diplome', 'diplomee',
    'grande ecole', 'ecole de commerce', 'ingenieur', 'master 1', 'master 2'];
  const DEGREE_ACRONYMS = ['BUT', 'DUT', 'M1', 'M2'];
  const CERTS = ['toeic', 'toefl', 'ielts', 'cambridge', 'delf', 'dalf', 'sst', 'pmp', 'prince2', 'scrum', 'itil', 'certification', 'certifie', 'certifiee', 'habilitation'];
  const LANGUAGES = { francais: 'fr', french: 'fr', anglais: 'en', english: 'en', arabe: 'ar', arabic: 'ar', espagnol: 'es', spanish: 'es',
    chinois: 'zh', mandarin: 'zh', chinese: 'zh', allemand: 'de', german: 'de', italien: 'it', italian: 'it', portugais: 'pt',
    portuguese: 'pt', neerlandais: 'nl', dutch: 'nl', russe: 'ru', japonais: 'ja', turc: 'tr', hindi: 'hi' };
  const LEVELS = { notions: 1, debutant: 1, a1: 1, a2: 2, intermediaire: 3, b1: 3, b2: 4, courant: 5, professionnel: 5, c1: 5,
    bilingue: 6, c2: 6, natif: 7, 'langue maternelle': 7, fluent: 5, native: 7, bilingual: 6, maternelle: 7, courante: 5, professionnelle: 5 };
  const LEADERSHIP = ['dirige', 'dirigee', 'dirigeant', 'manage', 'managee', 'encadre', 'encadree', 'encadrement', 'supervise', 'supervisee',
    "direction d'equipe", "chef d'equipe", "responsable d'equipe", "management d'equipe", 'manager une equipe', 'a la tete', 'head of',
    'team lead', 'led a team', 'managed a team', 'supervised'];
  const OWNERSHIP = ['pilote', 'pilotee', 'piloter', 'pilotage', 'gere', 'geree', 'gerer', 'gestion', 'mene', 'menee', 'conduit', 'realise',
    'realisee', 'assure', 'livre', 'livres', 'developpe', 'coordonne', 'coordination', 'organise', 'negocie', 'negociation', 'prospecte',
    'prospection', 'vendu', 'conseille', 'recrute', 'recrutement', 'cree', 'produit', 'production', 'optimise', 'suivi', 'responsable',
    'owned', 'managed', 'delivered'];
  const CONTRIBUTION = ['participe', 'participee', 'participation', 'contribue', 'contribuee', 'contribution', 'assiste', 'assistee', 'aide',
    'soutien', 'appui', 'en support', 'assisted', 'contributed', 'participated'];
  const STOP_CAP = new Set(("je j' nous vous votre vos madame monsieur objet candidature cordialement bonjour profil experience experiences " +
    'formation competences langues outils commercial commerciale digital cv lettre poste le la les un une des de du en et a au aux pour ' +
    'avec sur dans chez par ce cette ces mon ma mes son sa ses leur leurs il elle ils elles on si mais ou donc or ni car the and of to in ' +
    'for with at my our your i janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre janv fevr avr juil sept ' +
    "oct nov dec present aujourd'hui actuellement depuis puis ainsi enfin aussi egalement fort forte pret prete disponible ravi ravie").split(' '));
  const TEAM_LEAD = /(manag|encadr|dirig|supervis|anim|lead)\w*\s+(d'|de\s+|des\s+|l'|la\s+|une\s+|un\s+)*(equipe|team|collaborateurs|commerciaux|stagiaires|personnes|vendeurs|conseillers)/;
  E.LEVELS = LEVELS; E.LANGUAGES = LANGUAGES; E.TOOLS = TOOLS;

  const flatten = (v, out = []) => {
    if (v && typeof v === 'object') { for (const x of Object.values(v)) flatten(x, out); } else if (v !== null && v !== undefined) out.push(String(v));
    return out;
  };
  E.buildEvidence = (P, ids) => {
    const facts = []; const chunks = [];
    for (const id of ids) {
      const f = P.fact(id); if (!f) continue;
      facts.push(f); chunks.push(f.text);
      const d = Object.assign({}, f.data || {}); delete d.raw; flatten(d, chunks);
      if (f.parent) {
        const p = P.fact(f.parent);
        if (p && E.usable(p)) { chunks.push(p.text); const pd = Object.assign({}, p.data || {}); delete pd.raw; flatten(pd, chunks); }
      }
    }
    const numbers = new Set(); for (const c of chunks) E.extractNumbers(c).forEach((n) => numbers.add(n));
    return { text: E.norm(chunks.join(' \n ')), numbers, facts };
  };
  const levelOf = (t) => {
    if (LEADERSHIP.some((w) => E.containsTerm(t, w)) || TEAM_LEAD.test(t)) return 3;
    if (OWNERSHIP.some((w) => E.containsTerm(t, w))) return 2;
    if (CONTRIBUTION.some((w) => E.containsTerm(t, w))) return 1;
    return 0;
  };
  const WORD = /[A-Za-zÀ-ÖØ-öø-ÿ0-9][\wÀ-ÖØ-öø-ÿ'’&+./-]*/g;
  const SENT_BREAK = /[.!?:;•·|—–("«]\s*$/;
  E.properNounCandidates = (text) => {
    const cands = []; let cur = []; let prevEnd = 0; let sentenceStart = true;
    for (const m of text.matchAll(WORD)) {
      const word = m[0].replace(/[.,;:'’]+$/, '');
      const gap = text.slice(prevEnd, m.index);
      if (prevEnd && SENT_BREAK.test(text.slice(0, m.index).trimEnd() + ' ') && gap.trim()) sentenceStart = true;
      if (prevEnd === 0) sentenceStart = true;
      const s = word.replace(/^['’]+|['’]+$/g, '');
      const isAcr = s.length >= 2 && s === s.toUpperCase() && /[A-Za-zÀ-ÿ]/.test(s) && s !== s.toLowerCase();
      const internalCap = /[A-ZÀ-Ö]/.test(s.slice(1)) && s !== s.toUpperCase();
      const isCap = /^[A-ZÀ-ÖØ-Þ]/.test(s);
      let keep = false;
      if (isAcr || internalCap) keep = true; else if (isCap && !sentenceStart) keep = true; else if (isCap && cur.length) keep = true;
      if (keep && !STOP_CAP.has(E.norm(s))) cur.push(s); else if (cur.length) { cands.push(cur.join(' ')); cur = []; }
      prevEnd = m.index + m[0].length;
      sentenceStart = SENT_BREAK.test(text.slice(0, prevEnd) + ' ');
    }
    if (cur.length) cands.push(cur.join(' '));
    return cands;
  };

  E.Validator = function (profile, offerText, offerTerms) {
    const P = profile.fact ? profile : E.P(profile);
    const offerNorm = E.norm(offerText || '');
    const offerNumbers = new Set(E.extractNumbers(offerText || ''));
    const offerTermsNorm = E.norm((offerTerms || []).join(' '));
    const forbidden = P.forbiddenTerms().map(E.norm).filter(Boolean);
    const supported = (term, ev, allowOffer) => !!E.supportedBy(term, ev.text) ||
      (allowOffer && (E.containsTerm(offerNorm, term) || E.containsTerm(offerTermsNorm, term)));

    const validateLine = (line) => {
      const v = { line_id: line.id, ok: true, reasons: [], warnings: [], forbidden: false, exaggeration: false };
      const text = String(line.text || '').trim();
      if (line.kind === 'structure' || !text) return v;
      const t = E.norm(text);
      for (const term of forbidden) if (E.containsTerm(t, term)) { v.ok = false; v.forbidden = true; v.reasons.push(`Terme interdit : « ${term} »`); }
      const b = E.bannedFound(text);
      for (const p of b.hard) { v.ok = false; v.reasons.push(`Phrase creuse interdite : « ${p} »`); }
      for (const p of b.soft) v.warnings.push(`Phrase à éviter : « ${p} »`);
      const needsFacts = line.kind === 'claim' || line.kind === 'fact';
      const ids = line.fact_ids || [];
      const unknown = ids.filter((id) => !P.fact(id));
      const unusable = ids.filter((id) => P.fact(id) && !E.usable(P.fact(id)));
      if (unknown.length) { v.ok = false; v.reasons.push(`Faits inexistants : ${unknown.join(', ')}`); }
      if (unusable.length) { v.ok = false; v.reasons.push(`Faits non utilisables (statut) : ${unusable.map((id) => `${id} (${P.fact(id).status})`).join(', ')}`); }
      const usableIds = ids.filter((id) => !unknown.includes(id) && !unusable.includes(id));
      if (needsFacts && !usableIds.length) { v.ok = false; v.reasons.push('Aucun fait source valide pour une affirmation'); }
      const ev = E.buildEvidence(P, usableIds);
      const allowOffer = ['headline', 'offer_ref', 'projection', 'closing'].includes(line.kind);
      if (line.kind === 'offer_ref') {
        const q = E.norm(line.offer_quote || '');
        if (!q) { v.ok = false; v.reasons.push("offer_ref sans citation de l'offre"); }
        else if (!offerNorm.includes(q)) {
          const words = (q.match(/[a-z0-9]+/g) || []).filter((w) => w.length > 2);
          const hits = words.filter((w) => E.containsTerm(offerNorm, w)).length;
          if (!words.length || hits / words.length < 0.85) { v.ok = false; v.reasons.push("Citation introuvable dans l'offre"); }
        }
      }
      for (const n of E.extractNumbers(text)) {
        if (ev.numbers.has(n) || (allowOffer && offerNumbers.has(n))) continue;
        v.ok = false; v.reasons.push(`Nombre sans preuve : ${n}`);
      }
      for (const term of DEGREES.concat(CERTS)) {
        if (E.containsTerm(t, term) && !supported(term, ev, false)) {
          if (['certification', 'certifie', 'certifiee', 'diplome', 'diplomee'].includes(term) && allowOffer && E.containsTerm(offerNorm, term)) continue;
          v.ok = false; v.reasons.push(`Diplôme/certification sans preuve : « ${term} »`);
        }
      }
      for (const acro of DEGREE_ACRONYMS) {
        if (new RegExp(`(?<![A-Za-z0-9])${acro}(?![A-Za-z0-9])`).test(text) && !supported(acro, ev, false)) { v.ok = false; v.reasons.push(`Diplôme sans preuve : « ${acro} »`); }
      }
      for (const term of TOOLS) {
        if (E.containsTerm(t, term) && !supported(term, ev, line.kind === 'headline')) {
          if (allowOffer && line.kind !== 'projection' && E.containsTerm(offerNorm, term)) continue;
          v.ok = false; v.reasons.push(`Outil/compétence technique sans preuve : « ${term} »`);
        }
      }
      const words = t.split(' ');
      words.forEach((w, i) => {
        const clean = w.replace(/[,.;:()]/g, '');
        if (!LANGUAGES[clean]) return;
        if (!supported(clean, ev, allowOffer && line.kind !== 'projection')) { v.ok = false; v.reasons.push(`Langue sans preuve : « ${w} »`); return; }
        const win = words.slice(Math.max(0, i - 3), i + 5).join(' ');
        let claimed = 0; for (const [lw, lv] of Object.entries(LEVELS)) if (E.containsTerm(win, lw)) claimed = Math.max(claimed, lv);
        if (claimed) {
          let factLevel = 0;
          for (const f of ev.facts) {
            if (f.kind === 'language') factLevel = Math.max(factLevel, LEVELS[E.norm(String((f.data || {}).level || ''))] || 0);
            if (f.kind === 'certification' && E.norm(f.text).includes('toeic')) factLevel = Math.max(factLevel, 5);
          }
          if (factLevel && claimed > factLevel) { v.ok = false; v.exaggeration = true; v.reasons.push(`Niveau de langue gonflé : ${win.trim()}`); }
        }
      });
      for (const cand of E.properNounCandidates(text)) {
        if (supported(cand, ev, allowOffer)) continue;
        const parts = cand.split(/[\s/&]+/).filter((p) => p && !STOP_CAP.has(E.norm(p)));
        if (parts.length && parts.every((p) => supported(p, ev, allowOffer))) continue;
        v.ok = false; v.reasons.push(`Nom propre ou sigle sans preuve : « ${cand} »`);
      }
      if (needsFacts && ev.facts.length) {
        const ll = levelOf(t); const fl = Math.max(0, ...ev.facts.map((f) => levelOf(E.norm(f.text))));
        if (ll === 3 && fl < 3) { v.ok = false; v.exaggeration = true; v.reasons.push('Responsabilité gonflée (management/direction) sans fait qui le prouve'); }
        else if (fl === 1 && ll >= 2) { v.ok = false; v.exaggeration = true; v.reasons.push('« Participé » ne devient pas « piloté/géré »'); }
      }
      if (line.section === 'experience' && text.length > 130) v.warnings.push(`Puce longue (${text.length} caractères)`);
      if (line.kind === 'headline' && E.extractNumbers(text).length) { v.ok = false; v.reasons.push('Chiffre dans le titre'); }
      return v;
    };
    const validateLines = (lines) => {
      const r = { verdicts: [], total: 0, traced: 0, factuality: 0, forbidden_hits: 0, rejected_ids: [], warnings: [] };
      for (const ln of lines) {
        if (ln.kind === 'structure') continue;
        const v = validateLine(ln);
        r.verdicts.push(v); r.total += 1;
        if (v.ok) r.traced += 1; else r.rejected_ids.push(ln.id);
        if (v.forbidden) r.forbidden_hits += 1;
        v.warnings.forEach((w) => r.warnings.push(`${ln.id}: ${w}`));
      }
      r.factuality = r.total ? Math.round((1000 * r.traced) / r.total) / 10 : 0;
      r.perfect = r.total > 0 && r.traced === r.total && r.forbidden_hits === 0;
      return r;
    };
    return { validateLine, validateLines, P };
  };

  // ─── Analyse d'offre (déterministe) ───────────────────────────────────────
  const CITIES = { paris: 'FR', 'ile-de-france': 'FR', 'la defense': 'FR', 'boulogne-billancourt': 'FR', levallois: 'FR', neuilly: 'FR',
    'saint-denis': 'FR', 'issy-les-moulineaux': 'FR', nanterre: 'FR', courbevoie: 'FR', puteaux: 'FR', montrouge: 'FR', clichy: 'FR',
    'rueil-malmaison': 'FR', massy: 'FR', versailles: 'FR', montreuil: 'FR', 'saint-ouen': 'FR', vincennes: 'FR', pantin: 'FR',
    aubervilliers: 'FR', ivry: 'FR', vitry: 'FR', creteil: 'FR', cergy: 'FR', 'marne-la-vallee': 'FR', 'noisy-le-grand': 'FR', roissy: 'FR',
    rungis: 'FR', 'saint-cloud': 'FR', suresnes: 'FR', velizy: 'FR', guyancourt: 'FR', evry: 'FR', lyon: 'FR', marseille: 'FR', lille: 'FR',
    bordeaux: 'FR', toulouse: 'FR', nantes: 'FR', nice: 'FR', strasbourg: 'FR', rennes: 'FR', montpellier: 'FR', grenoble: 'FR',
    bruxelles: 'BE', brussels: 'BE', geneve: 'CH', lausanne: 'CH', zurich: 'CH', luxembourg: 'LU', londres: 'GB', london: 'GB', dublin: 'IE',
    madrid: 'ES', barcelone: 'ES', barcelona: 'ES', lisbonne: 'PT', lisbon: 'PT', milan: 'IT', berlin: 'DE', munich: 'DE', amsterdam: 'NL',
    dubai: 'AE', 'abu dhabi': 'AE', 'new york': 'US', montreal: 'CA', toronto: 'CA', singapour: 'SG', singapore: 'SG', shanghai: 'CN',
    'hong kong': 'HK', casablanca: 'MA', tunis: 'TN' };
  const IDF = new Set(['paris', 'ile-de-france', 'la defense', 'boulogne-billancourt', 'levallois', 'neuilly', 'saint-denis', 'issy-les-moulineaux',
    'nanterre', 'courbevoie', 'puteaux', 'montrouge', 'clichy', 'rueil-malmaison', 'massy', 'versailles', 'montreuil', 'saint-ouen', 'vincennes',
    'pantin', 'aubervilliers', 'ivry', 'vitry', 'creteil', 'cergy', 'marne-la-vallee', 'noisy-le-grand', 'roissy', 'rungis', 'saint-cloud',
    'suresnes', 'velizy', 'guyancourt', 'evry']);
  const MUST = /imperatif|requis|exig|indispensable|obligatoire|maitrise|must|required|minimum|essential|vous avez|vous disposez|vous justifiez|necessaire|essentiel/;
  const NICE = /un plus|idealement|apprecie|souhaite|bonus|nice to have|serait un atout|est un atout|appreciee|preferred|a plus|strong plus|advantage|un atout/;
  const MISSION_HEAD = /^\s*(vos |les |tes )?(missions?|responsabilit|ce que vous ferez|votre r[oô]le|au quotidien|what you.ll do|what you will do|responsibilities|your role|le poste)/i;
  const PROFILE_HEAD = /^\s*(votre |le |ton )?(profil|compétences|competences|qualifications|requirements|what we.re looking for|what we are looking for|vous êtes|vous etes|ce que nous recherchons)/i;
  const BULLET = /^\s*([-•*·▪►✓✔]|\d+[.)])\s*/;
  const SOFT = new Set(['organisation', 'communication', 'autonomie', 'adaptabilite', 'presentation', 'rigueur', 'tenacite', 'ecoute', 'polyvalence', 'reactivite', 'patience', 'precision', 'discretion', 'fiabilite']);
  const NOT_SKILLS = new Set(['business france', 'filiale', 'logistique', 'zone geographique', 'marche local', 'implantation', 'maison', 'boutique', 'store', 'hotel', 'hotellerie']);
  const HARD_REQ = ['permis b', 'permis de conduire', 'vehicule personnel', 'casier judiciaire vierge', 'titre de sejour', 'nationalite', 'passeport', 'habilitation electrique', 'cariste'];
  const CONTRACTS = [['VIE', /(?<![a-z])v\.?i\.?e\.?(?![a-z])|volontariat international/], ['CDI', /\bcdi\b|contrat a duree indeterminee|\bpermanent\b/],
    ['CDD', /\bcdd\b|contrat a duree determinee|fixed-term/], ['Alternance', /\balternance\b|apprentissage|contrat pro/],
    ['Stage', /\bstage\b|stagiaire|internship/], ['Freelance', /freelance|independant|auto-entrepreneur/], ['Intérim', /mission d'interim|contrat d'interim|\binterim\b/]];

  const sentences = (text) => text.split(/(?<=[.!?;])\s+|\n+/).map((s) => s.trim()).filter(Boolean);
  E.detectLanguage = (text) => {
    const t = ` ${E.norm(text)} `;
    const count = (ws) => ws.reduce((n, w) => n + (t.split(` ${w} `).length - 1), 0);
    const fr = count(['le', 'la', 'les', 'des', 'vous', 'nous', 'et', 'pour', 'une', 'avec']);
    const en = count(['the', 'and', 'you', 'we', 'with', 'for', 'our', 'your', 'will', 'to']);
    return en > fr * 1.2 ? 'en' : 'fr';
  };
  const detectContract = (t, head) => {
    for (const zone of [E.norm(head || ''), t]) {
      if (!zone) continue;
      const hits = [];
      for (const [label, re] of CONTRACTS) { const m = zone.match(re); if (m) hits.push([m.index, label]); }
      if (hits.length) {
        if (zone !== t || hits.length === 1) return hits.sort((a, b) => a[0] - b[0])[0][1];
        return CONTRACTS.find(([, re]) => re.test(t))[0];
      }
    }
    return 'UNKNOWN';
  };
  const detectLocation = (text) => {
    const t = E.norm(text);
    for (const [city, cc] of Object.entries(CITIES)) if (E.containsTerm(t, city)) return [city.replace(/\b\w/g, (c) => c.toUpperCase()), cc];
    return ['UNKNOWN', 'UNKNOWN'];
  };
  const detectSeniority = (t) => {
    let years = null;
    const m = t.match(/(\d{1,2})\s?(?:\+|a \d+)?\s?ans? (?:d'experience|minimum|d'exp)/) || t.match(/minimum (\d{1,2}) ans|au moins (\d{1,2}) ans|(\d{1,2})\+? years/);
    if (m) years = Number(m.slice(1).find((g) => g));
    if ((years !== null && years >= 6) || /\bsenior\b|head of|directeur|directrice|10 ans/.test(t)) return ['senior', years];
    if (/junior|debutant|premiere experience|jeune diplome|0 a 2 ans|entry level|graduate/.test(t) || (years !== null && years <= 2)) return ['junior', years];
    if (/confirme|experimente|\b3 a 5 ans\b/.test(t) || (years && years >= 3)) return ['confirmé', years];
    return ['UNKNOWN', years];
  };
  const detectDegree = (t) => {
    const explicit = [...t.matchAll(/bac\s?\+\s?([2-5])/g)].map((m) => Number(m[1]));
    if (explicit.length) return `Bac+${Math.min(...explicit)}`;
    for (const [label, re] of [['Bac+5', /\bmaster\b|\bmba\b|grande ecole|\bmsc\b/], ['Bac+3', /\blicence\b|\bbachelor|ecole de commerce|universit/], ['Bac+2', /\bbts\b|\bdut\b|\bbut\b/], ['Bac', /\bbac\b|baccalaureat/]]) if (re.test(t)) return label;
    return 'UNKNOWN';
  };
  E.detectSector = (title, text) => {
    const tn = E.norm(title); const xn = E.norm(text); const scores = {};
    for (const [sid, s] of Object.entries(DATA.sectors)) {
      const d = s.detect || {}; let sc = 0;
      for (const kw of d.title_keywords || []) { if (E.containsTerm(tn, kw)) sc += 5; else if (E.containsTerm(xn, kw)) sc += 1; }
      for (const kw of d.text_keywords || []) if (E.containsTerm(xn, kw)) sc += 1;
      scores[sid] = sc;
    }
    let best = 'commercial'; let max = 0;
    for (const [k, v] of Object.entries(scores)) if (v > max) { max = v; best = k; }
    return [best, scores];
  };
  E.cleanTitle = (title) => {
    let t = String(title || '').replace(/\s*[([]?\s*(h\s*\/\s*f|f\s*\/\s*h|m\s*\/\s*f|f\s*\/\s*m|h\/f\/x|x\/f\/h)\s*[)\]]?/gi, '');
    t = t.replace(/\s*[-–—|]\s*(cdi|cdd|stage|alternance|freelance|vie|v\.i\.e|interim|intérim)\b.*$/i, '');
    return t.replace(/^[\s\-–|,]+|[\s\-–|,]+$/g, '') || 'UNKNOWN';
  };
  const bestPriority = (sents, term) => {
    let best = ''; let rank = 3;
    for (const s of sents) {
      const sn = E.norm(s); if (!E.containsTerm(sn, term)) continue;
      const r = MUST.test(sn) ? 0 : NICE.test(sn) ? 2 : 1;
      if (r < rank) { best = s; rank = r; }
    }
    return [best.slice(0, 160), ({ 0: 'MUST', 1: 'IMPORTANT', 2: 'NICE', 3: 'IMPORTANT' })[rank]];
  };
  const sectionBullets = (lines, head) => {
    const out = []; let active = false;
    for (const line of lines) {
      if (head.test(line)) { active = true; continue; }
      if (!active) continue;
      if ((PROFILE_HEAD.test(line) || MISSION_HEAD.test(line)) && !BULLET.test(line)) break;
      if (BULLET.test(line) || (line.length > 25 && out.length < 12)) { const c = line.replace(BULLET, '').trim(); if (c.length > 8 && c.length < 220) out.push(c); }
      else if (out.length && line.length < 60 && line.endsWith(':')) break;
    }
    return out.slice(0, 10);
  };
  const singular = (t) => { const w = t.split(' '); const l = w[w.length - 1]; if (l.length > 3 && l.endsWith('s')) w[w.length - 1] = l.slice(0, -1); return w.join(' '); };
  const dedupeKeywords = (kws) => {
    const rank = { REQUIRED: 0, IMPORTANT: 1, NICE: 2 }; const best = new Map();
    for (const kw of kws) { const k = singular(E.norm(kw.term)); if (!best.has(k) || rank[kw.priority] < rank[best.get(k).priority]) best.set(k, Object.assign({}, kw)); }
    const keys = [...best.keys()];
    for (const s of keys) for (const l of keys) {
      if (s !== l && best.has(s) && best.has(l) && new RegExp(`(?<![a-z])${escRe(s)}(?![a-z])`).test(l)) {
        if (rank[best.get(s).priority] < rank[best.get(l).priority]) best.get(l).priority = best.get(s).priority;
        best.delete(s); break;
      }
    }
    return [...best.values()].sort((a, b) => rank[a.priority] - rank[b.priority]).slice(0, 24);
  };
  E.deterministicAnalysis = (offer) => {
    const text = offer.text; const t = E.norm(text);
    const lines = text.split('\n').filter((l) => l.trim());
    const title = offer.title_hint || (lines[0] || 'UNKNOWN').slice(0, 120);
    const [location, ctry] = detectLocation(text);
    const [seniority, years] = detectSeniority(t);
    const contract = detectContract(t, [offer.title_hint || '', lines[0] || ''].join(' '));
    let [sectorId, sectorScores] = E.detectSector(title, text);
    if (contract === 'VIE') sectorId = 'international_vie';
    const start = lines.findIndex((l) => MISSION_HEAD.test(l) || PROFILE_HEAD.test(l));
    const useful = (start > 0 ? [lines[0]].concat(lines.slice(start)) : lines).join('\n');
    const u = E.norm(useful); const sents = sentences(useful);
    let vocab = [];
    for (const s of Object.values(DATA.sectors)) vocab = vocab.concat(s.dominant_skills || [], s.vocabulary || []);
    for (const g of DATA.synonyms.equivalents) vocab = vocab.concat(g.slice(0, 2));
    vocab = E.unique(vocab.filter((v) => v.length > 2 && !NOT_SKILLS.has(E.norm(v))));
    const skills = [];
    for (const term of vocab) {
      if (!E.containsTerm(u, term)) continue;
      let [ev, pr] = bestPriority(sents, term);
      if (SOFT.has(E.norm(term)) && pr !== 'MUST') pr = 'NICE';
      skills.push({ name: term, priority: pr, evidence: ev });
    }
    for (const hard of HARD_REQ) if (E.containsTerm(u, hard)) { const [ev, pr] = bestPriority(sents, hard); skills.push({ name: hard, priority: pr, evidence: ev }); }
    const tools = TOOLS.filter((x) => x !== 'ats' && E.containsTerm(u, x));
    const languages = [];
    for (const [word, code] of Object.entries(LANGUAGES)) {
      if (languages.some((l) => l.code === code) || !E.containsTerm(u, word)) continue;
      const mentions = sents.filter((s) => E.containsTerm(E.norm(s), word));
      const score = (s) => { const n = E.norm(s); return (MUST.test(n) || /essential/.test(n) ? 2 : 0) + (Object.keys(LEVELS).some((l) => E.containsTerm(n, l)) ? 1 : 0); };
      const sentence = mentions.sort((a, b) => score(b) - score(a))[0] || '';
      const sn = E.norm(sentence);
      const level = Object.keys(LEVELS).find((l) => E.containsTerm(sn, l)) || '';
      if (!(level || MUST.test(sn) || NICE.test(sn) || /langue|language|parl|speak|advantage|atout/.test(sn))) continue;
      languages.push({ name: word[0].toUpperCase() + word.slice(1), code, level: level || 'UNKNOWN',
        priority: MUST.test(sn) || /essential|imperatif/.test(sn) ? 'MUST' : NICE.test(sn) || /advantage|atout/.test(sn) ? 'NICE' : 'IMPORTANT' });
    }
    const toKw = { MUST: 'REQUIRED', NICE: 'NICE', IMPORTANT: 'IMPORTANT', UNKNOWN: 'IMPORTANT' };
    let keywords = skills.map((s) => ({ term: s.name, priority: toKw[s.priority] }));
    for (const tool of tools) keywords.push({ term: tool.length <= 3 ? tool.toUpperCase() : tool.replace(/\b\w/g, (c) => c.toUpperCase()), priority: toKw[bestPriority(sents, tool)[1]] });
    for (const l of languages) keywords.push({ term: l.name, priority: toKw[l.priority] });
    keywords = dedupeKeywords(keywords);
    return {
      company: offer.company_hint || 'UNKNOWN', job_title: E.cleanTitle(title), location, country: ctry, contract,
      seniority, experience_years_min: years, degree_required: detectDegree(t), missions: sectionBullets(lines, MISSION_HEAD),
      skills, tools, languages, remote: /full remote|100 ?% (remote|teletravail)/.test(t) ? 'full' : /teletravail|hybride|hybrid|jours? de remote/.test(t) ? 'hybrid' : /sur site|presentiel|on-site|onsite/.test(t) ? 'onsite' : 'UNKNOWN',
      sector: sector(sectorId).name || sectorId, recruiter_wants: { explicit: sectionBullets(lines, PROFILE_HEAD).slice(0, 6), inferred: [] },
      keywords, language_of_offer: E.detectLanguage(text), sector_id: sectorId, sector_scores: sectorScores, source: 'deterministic',
      salary: { raw: '' }, hidden_risks: [], benefits: [], constraints: [],
    };
  };
  E.mergeAiAnalysis = (base, ai) => {
    const merged = Object.assign({}, base);
    for (const [k, v] of Object.entries(ai || {})) {
      if (v === null || v === undefined || v === '' || v === 'UNKNOWN' || (Array.isArray(v) && !v.length) || (typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length)) continue;
      if (['sector_id', 'sector_scores', 'source'].includes(k)) continue;
      if (k === 'country' && base.country !== 'UNKNOWN' && v !== base.country) continue;
      merged[k] = v;
    }
    if (Array.isArray(merged.keywords)) {
      merged.keywords = dedupeKeywords(merged.keywords.filter((k) => k && k.term).map((k) => ({ term: String(k.term), priority: ['REQUIRED', 'IMPORTANT', 'NICE'].includes(k.priority) ? k.priority : 'IMPORTANT' }))
        .concat(base.keywords.filter((k) => k.priority === 'REQUIRED')));
    }
    merged.sector_id = base.sector_id; merged.sector_scores = base.sector_scores;
    if (!Object.values(base.sector_scores).some((x) => x > 0)) { const [sid, sc] = E.detectSector(merged.job_title, [merged.job_title].concat(merged.missions || []).join(' ')); merged.sector_id = sid; merged.sector_scores = sc; }
    if (merged.contract === 'VIE') merged.sector_id = 'international_vie';
    merged.job_title = E.cleanTitle(merged.job_title);
    merged.source = 'ai+deterministic';
    return merged;
  };

  // ─── Matching ─────────────────────────────────────────────────────────────
  const PRIO_W = { REQUIRED: 3, MUST: 3, IMPORTANT: 2, NICE: 1, UNKNOWN: 1 };
  const WEIGHTS = { role: 0.18, skills: 0.24, experience: 0.12, sector: 0.10, degree: 0.06, language: 0.08, location: 0.07, contract: 0.05, salary: 0.02, seniority: 0.04, availability: 0.02, preferences: 0.02 };
  E.factIndex = (P) => P.usableFacts().filter((f) => !['contact', 'preference'].includes(f.kind)).map((f) => [f, E.buildEvidence(P, [f.id]).text]);
  E.coverTerm = (term, index) => {
    const ids = []; let via = '';
    for (const [f, ev] of index) { const how = E.supportedBy(term, ev); if (how) { ids.push(f.id); via = via || how; } }
    return { term, priority: '', covered: !!ids.length, fact_ids: ids.slice(0, 6), via };
  };
  const months = (s, e) => {
    const parse = (v, dm) => (v ? new Date(Number(v.split('-')[0]), (v.split('-')[1] ? Number(v.split('-')[1]) : dm) - 1, 1) : null);
    const a = parse(s, 1); const b = parse(e, 12) || new Date();
    if (!a) return 0;
    return Math.max(1, (b.getFullYear() - a.getFullYear()) * 12 + (b.getMonth() - a.getMonth()) + 1);
  };
  E.computeMatch = (P, a) => {
    const index = E.factIndex(P); const scores = {};
    const coverage = (a.keywords || []).map((kw) => Object.assign(E.coverTerm(kw.term, index), { priority: kw.priority }));
    const tw = coverage.reduce((n, c) => n + (PRIO_W[c.priority] || 1), 0) || 1;
    const cw = coverage.filter((c) => c.covered).reduce((n, c) => n + (PRIO_W[c.priority] || 1), 0);
    scores.skills = coverage.length ? Math.round((1000 * cw) / tw) / 10 : 50;
    const titleN = E.norm(a.job_title);
    const tr = P.fact('target.roles'); const roles = ((tr && tr.data.roles) || []).map(E.norm);
    const held = P.experiences().map((e) => E.norm(e.data.title || ''));
    let role = 30;
    if (roles.some((r) => r && (titleN.includes(r) || r.includes(titleN)))) role = 95;
    else if (roles.some((r) => r && r.split(' ').some((w) => w.length > 3 && titleN.includes(w)))) role = 75;
    if (held.some((h) => h && h.replace('&', ' ').split(' ').some((w) => w.length > 4 && titleN.includes(w)))) role = Math.max(role, 80);
    if (['business_development', 'commercial', 'account_management', 'international_vie'].includes(a.sector_id)) role = Math.max(role, 70);
    const practiced = new Set();
    for (const e of P.experiences()) {
      const blob = [e.data.title || ''].concat(P.children(e.id).map((c) => c.text)).join(' ');
      const [sid, sc] = E.detectSector(e.data.title || '', blob); const top = sc[sid] || 0;
      for (const [k, v] of Object.entries(sc)) if (v >= 2 && v >= 0.25 * top) practiced.add(k);
    }
    if (practiced.has(a.sector_id)) role = Math.max(role, 75);
    if (a.seniority === 'senior') role = Math.min(role, 45);
    scores.role = role;
    const yrs = P.experiences().reduce((n, e) => n + months(e.data.start, e.data.end), 0) / 12;
    const need = a.experience_years_min;
    scores.experience = need === null || need === undefined ? 80 : need ? Math.round(Math.min(100, (100 * yrs) / need) * 10) / 10 : 90;
    const dom = sector(a.sector_id).dominant_skills || [];
    const domCov = dom.map((s) => E.coverTerm(s, index).covered);
    scores.sector = domCov.length ? Math.round((1000 * domCov.filter(Boolean).length) / domCov.length) / 10 : 50;
    const eduText = E.norm(P.byKind('education').map((f) => f.text).join(' '));
    const have = /bachelor|licence|bac\+3/.test(eduText) ? 3 : /bts|dut|bac\+2/.test(eduText) ? 2 : 0;
    const needD = ({ 'Bac+5': 5, 'Bac+3': 3, 'Bac+2': 2, Bac: 1 })[a.degree_required] || 0;
    scores.degree = !needD ? 70 : have >= needD ? 100 : needD - have === 2 ? 45 : 65;
    const ls = (a.languages || []).map((l) => {
      const facts = P.byKind('language').filter((f) => E.norm(f.data.language || '').startsWith(E.norm(l.name || '').slice(0, 4)));
      if (!facts.length) return l.priority === 'MUST' ? 0 : 40;
      const h = Math.max(...facts.map((f) => LEVELS[E.norm(f.data.level || '')] || 0));
      const n = ({ notions: 1, intermediaire: 3, courant: 5, professionnel: 5, bilingue: 6, natif: 7, c1: 5, c2: 6, b2: 4, fluent: 5 })[E.norm(l.level || '')] || 4;
      return h >= n ? 100 : 60;
    });
    scores.language = ls.length ? Math.round((10 * ls.reduce((x, y) => x + y, 0)) / ls.length) / 10 : 80;
    const loc = E.norm(a.location);
    scores.location = IDF.has(loc) && P.fact('mobility.idf') ? 100 : a.contract === 'VIE' ? 80 : loc === 'unknown' ? 60 : 35;
    const wantsVie = roles.includes('vie');
    scores.contract = ({ CDI: 95, CDD: 75, VIE: wantsVie ? 95 : 60, Freelance: 45, Alternance: 40, Stage: 35, 'Intérim': 55 })[a.contract] || 70;
    scores.salary = 60;
    scores.seniority = ({ junior: 95, 'confirmé': 70, senior: 30 })[a.seniority] || 75;
    scores.availability = P.fact('avail.immediate') ? 100 : 60;
    scores.preferences = role >= 75 ? 100 : 60;
    const match = Math.round(Object.entries(WEIGHTS).reduce((n, [k, w]) => n + scores[k] * w, 0) * 10) / 10;
    const must = coverage.filter((c) => c.priority === 'REQUIRED');
    const mustCov = must.filter((c) => c.covered).length;
    const quality = must.length ? Math.round((1000 * mustCov) / must.length) / 10 : scores.skills;
    const risk = Math.round((100 - (0.5 * match + 0.5 * quality)) * 10) / 10;
    const whyFit = []; const missing = []; const risks = []; const whyNot = [];
    for (const c of coverage) {
      if (c.covered && ['REQUIRED', 'IMPORTANT'].includes(c.priority)) whyFit.push({ text: `« ${c.term} » prouvé (${c.via})`, fact_ids: c.fact_ids.slice(0, 3) });
      else if (!c.covered) missing.push({ requirement: c.term, priority: c.priority === 'REQUIRED' ? 'MUST' : c.priority, note: "Aucun fait ne le prouve : à ne pas écrire, à préparer pour l'entretien." });
    }
    const strengths = P.byKind('result').filter((f) => coverage.some((c) => c.covered && c.fact_ids.includes(f.id))).map((f) => ({ text: f.text, fact_ids: [f.id] }));
    if (scores.seniority < 50) whyNot.push({ text: 'Offre orientée profil senior', fact_ids: [] });
    if (scores.location < 50) risks.push({ text: `Lieu hors mobilité confirmée (${a.location})` });
    if (scores.degree < 60) risks.push({ text: `Diplôme demandé : ${a.degree_required}` });
    if (must.length && mustCov < must.length) risks.push({ text: `${must.length - mustCov} mot(s)-clé(s) REQUIRED non prouvé(s)` });
    if (a.contract === 'VIE') risks.push({ text: "Éligibilité VIE (âge, nationalité) à vérifier par l'utilisateur" });
    for (const r of a.hidden_risks || []) risks.push({ text: String(r) });
    return { scores, match, quality, risk, coverage, why_fit: whyFit.slice(0, 8), why_not: whyNot, missing: missing.slice(0, 10), strengths: strengths.slice(0, 6), risks };
  };

  // ─── Stratégie (repli déterministe + garde-fous) ──────────────────────────
  E.deterministicStrategy = (P, a, m) => {
    const s = sector(a.sector_id); const style = s.cv_style || {}; const c = country(a.country);
    const covered = new Set(m.coverage.filter((x) => x.covered).flatMap((x) => x.fact_ids));
    const rel = {};
    for (const e of P.experiences()) {
      const fam = new Set([e.id].concat(P.children(e.id).map((f) => f.id)));
      let sc = 0;
      for (const cv of m.coverage) if (cv.covered && cv.fact_ids.some((id) => fam.has(id))) sc += ({ REQUIRED: 3, IMPORTANT: 2, NICE: 1 })[cv.priority] || 1;
      sc += 0.5 * [...fam].filter((id) => covered.has(id)).length;
      rel[e.id] = sc;
    }
    const ordered = Object.keys(rel).sort((x, y) => rel[y] - rel[x]);
    const up = ordered.filter((e) => rel[e] > 0).slice(0, 2); if (!up.length && ordered.length) up.push(ordered[0]);
    const down = ordered.filter((e) => !up.includes(e));
    let title = a.job_title && a.job_title !== 'UNKNOWN' ? E.cleanTitle(a.job_title) : '';
    if (!title) { const tr = P.fact('target.roles'); title = ((tr && tr.data.roles) || ['Business Developer'])[0]; }
    const keySkills = [];
    for (const cv of m.coverage) if (cv.covered) for (const id of cv.fact_ids) { const f = P.fact(id); if (f && ['skill', 'tool', 'language', 'certification'].includes(f.kind) && !keySkills.includes(id)) keySkills.push(id); }
    let hook = ''; let hookIds = [];
    const cands = [];
    for (const eid of up) for (const f of P.children(eid)) if (f.kind === 'result') cands.push([(covered.has(f.id) ? 2 : 0) + (E.extractNumbers(f.text).length ? 1 : 0), f]);
    cands.sort((x, y) => y[0] - x[0]);
    if (cands.length) { hook = cands[0][1].text; hookIds = [cands[0][1].id]; }
    let atsMode = style.ats_mode || 'HYBRID'; let dsn = style.design || 'hybrid_modern';
    if (dsn === 'human_premium' && atsMode !== 'HUMAN_FIRST') dsn = 'hybrid_modern';
    const chosen = ({ ATS_FIRST: 'A', HUMAN_FIRST: 'B' })[atsMode] || 'C';
    const missingMust = m.missing.filter((x) => x.priority === 'MUST').map((x) => x.requirement);
    const risks = m.risks.map((r) => r.text);
    if (missingMust.length) risks.push("Non prouvé (ne pas écrire, préparer l'entretien) : " + missingMust.slice(0, 5).join(', '));
    const opt = (key, angle, mode, d) => ({ key, angle, title, hook, hook_fact_ids: hookIds, experiences_up: up, experiences_down: down, key_skill_fact_ids: keySkills.slice(0, 8), ats_mode: mode, design_profile: d, score: 0 });
    return {
      options: [opt('A', 'ATS / mots-clés : couverture maximale des REQUIRED prouvés', 'ATS_FIRST', 'ats_classic'),
        opt('B', 'Récit humain : preuves chiffrées et trajectoire', 'HUMAN_FIRST', style.design === 'human_premium' ? 'human_premium' : 'hybrid_modern'),
        opt('C', 'Hybride : lisible en 10 s et robuste ATS', 'HYBRID', 'hybrid_modern')],
      comparison: 'Choix déterministe selon le profil secteur.', chosen,
      best: { title, hook, hook_fact_ids: hookIds, experiences_up: up, experiences_down: down, key_skill_fact_ids: keySkills.slice(0, 8),
        ats_mode: chosen === 'C' ? 'HYBRID' : atsMode, design_profile: dsn,
        photo_mode: ['never', 'discouraged'].includes(c.photo) || !P.byKind('media').length ? 'OFF' : 'HEADER',
        letter_angle: (s.letter_style || {}).tone || 'factuel', channel: "Candidature via le lien de l'offre (PAI n'envoie rien)",
        risks, next_action: 'Relire le pack, valider le profil si besoin, puis postuler soi-même.', why: `Secteur « ${s.name || a.sector_id} » : ${style.summary_angle || ''}` },
      source: 'deterministic',
    };
  };
  E.sanitizeStrategy = (strat, P, a) => {
    const b = strat.best; const known = new Set(P.usableFacts().map((f) => f.id));
    b.experiences_up = (b.experiences_up || []).filter((e) => known.has(e));
    b.experiences_down = (b.experiences_down || []).filter((e) => known.has(e));
    for (const e of P.experiences()) if (!b.experiences_up.includes(e.id) && !b.experiences_down.includes(e.id)) b.experiences_down.push(e.id);
    b.key_skill_fact_ids = (b.key_skill_fact_ids || []).filter((f) => known.has(f));
    b.hook_fact_ids = (b.hook_fact_ids || []).filter((f) => known.has(f));
    if (['never', 'discouraged'].includes(country(a.country).photo) || !P.byKind('media').length) b.photo_mode = 'OFF';
    if (!DATA.designs[b.design_profile]) b.design_profile = 'hybrid_modern';
    if (b.design_profile === 'human_premium' && b.ats_mode !== 'HUMAN_FIRST') b.design_profile = 'hybrid_modern';
    if (!b.title || E.norm(b.title) === 'unknown') b.title = E.cleanTitle(a.job_title);
    return strat;
  };

  // ─── CV ───────────────────────────────────────────────────────────────────
  const TITLES = { fr: { summary: 'Profil', experience: 'Expérience professionnelle', skills: 'Compétences', education: 'Formation', certifications: 'Certifications', languages: 'Langues' },
    en: { summary: 'Profile', experience: 'Experience', skills: 'Skills', education: 'Education', certifications: 'Certifications', languages: 'Languages' } };
  const GROUPS = { fr: { commercial: 'Commercial', tools: 'Outils', digital: 'Digital' }, en: { commercial: 'Sales', tools: 'Tools', digital: 'Digital' } };
  const DIGITAL = new Set(['community management', 'strategie de contenu', 'planning editorial', 'production de contenu', 'ux', 'optimisation conversion', 'gestion de projets digitaux', 'analyse de performance']);
  E.contactLines = (P) => {
    const out = []; const city = P.fact('contact.city');
    if (city && E.usable(city)) out.push((city.data && city.data.city) || city.text);
    for (const id of ['contact.phone', 'contact.email']) { const v = P.value(id); if (v) out.push(v); }
    const li = P.value('contact.linkedin'); if (li) out.push(li.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, ''));
    return out;
  };
  const covScore = (f, m) => m.coverage.filter((c) => c.covered && c.fact_ids.includes(f.id)).reduce((n, c) => n + (({ REQUIRED: 3, IMPORTANT: 2, NICE: 1 })[c.priority] || 1), 0);
  const factLines = (P, ids, section, prefix) => ids.map((id, i) => { const f = P.fact(id); return f && E.usable(f) ? { id: `${prefix}${i + 1}`, section, kind: 'fact', text: cap(f.text), fact_ids: [id] } : null; }).filter(Boolean);
  const langLine = (P) => {
    const facts = P.byKind('language'); if (!facts.length) return null;
    const toeic = P.fact('cert.toeic'); const parts = []; const ids = [];
    for (const f of facts) { const name = f.data.language || f.text; parts.push(`${name} (${f.data.level || ''}${toeic && E.usable(toeic) && E.norm(name) === 'anglais' ? ', ' + toeic.text : ''})`); ids.push(f.id); }
    if (toeic && E.usable(toeic)) ids.push(toeic.id);
    return { id: 'l1', section: 'languages', kind: 'fact', text: parts.join(' · '), fact_ids: ids };
  };
  const eduIds = (P) => [P.byKind('education').map((f) => f.id), P.byKind('certification').filter((f) => f.id !== 'cert.toeic').map((f) => f.id)];
  E.experienceBlocks = (P, strat) => P.experiences().map((e) => ({ experience_id: e.id, title: e.data.title || '', company: e.data.company || '', city: e.data.city || '', period: e.data.period_label || '', featured: (strat.best.experiences_up || []).includes(e.id), bullet_ids: [] }));
  // Sélection gloutonne (parité avec pai/cv_architect.py::_pick) : d'abord les faits qui prouvent des mots-clés encore absents du CV.
  const baseCmp = (m) => (x, y) => (covScore(y, m) - covScore(x, m)) || ((x.kind !== 'result') - (y.kind !== 'result')) || (E.extractNumbers(y.text).length - E.extractNumbers(x.text).length);
  const pickGreedy = (facts, m, covered, limit) => {
    const W = { REQUIRED: 3, IMPORTANT: 2, NICE: 1 };
    const weight = new Map(m.coverage.map((c) => [c.term, W[c.priority] || 1]));
    const terms = new Map(facts.map((f) => [f.id, m.coverage.filter((c) => c.covered && (c.fact_ids || []).includes(f.id)).map((c) => c.term)]));
    const rest = facts.slice().sort(baseCmp(m)); const out = [];
    while (rest.length && out.length < limit) {
      let bi = 0; let bg = -1;
      rest.forEach((f, i) => { const g = terms.get(f.id).filter((t) => !covered.has(t)).reduce((sum, t) => sum + weight.get(t), 0); if (g > bg) { bg = g; bi = i; } });
      const [f] = rest.splice(bi, 1); out.push(f); terms.get(f.id).forEach((t) => covered.add(t));
    }
    return out;
  };
  E.buildCvDeterministic = (P, a, m, strat, profileValidated) => {
    const lang = a.language_of_offer === 'en' ? 'en' : 'fr'; const c = country(a.country); const best = strat.best; const d = design(best.design_profile);
    const lines = [{ id: 'h1', section: 'headline', kind: 'headline', text: best.title, fact_ids: P.fact('target.roles') ? ['target.roles'] : [], offer_terms: [a.job_title] }];
    const dom = P.fact('profile.domains');
    if (dom && E.usable(dom)) lines.push({ id: 's1', section: 'summary', kind: 'claim', text: cap(dom.text) + '.', fact_ids: [dom.id] });
    if (best.hook && best.hook_fact_ids && best.hook_fact_ids.length) {
      const hf = P.fact(best.hook_fact_ids[0]); const par = hf && hf.parent ? P.fact(hf.parent) : null;
      lines.push({ id: 's2', section: 'summary', kind: 'claim', text: cap(best.hook) + (par ? ` (${par.data.company})` : '') + '.', fact_ids: best.hook_fact_ids });
    }
    const summaryIds = new Set(lines.flatMap((l) => l.fact_ids));
    const covered = new Set(m.coverage.filter((c) => c.covered && (c.fact_ids || []).some((id) => summaryIds.has(id))).map((c) => c.term));
    const blocks = E.experienceBlocks(P, strat);
    for (const b of blocks) {
      const ch = P.children(b.experience_id).filter((f) => ['result', 'responsibility'].includes(f.kind));
      const limit = b.featured ? (d.max_bullets_featured || 4) : (d.max_bullets_other || 2);
      pickGreedy(ch, m, covered, limit).forEach((f, k) => { const id = `e.${b.experience_id.split('.').slice(1).join('.')}.b${k + 1}`; lines.push({ id, section: 'experience', kind: 'claim', text: cap(f.text), fact_ids: [f.id], experience_id: b.experience_id }); b.bullet_ids.push(id); });
    }
    const groups = { commercial: [], tools: P.byKind('tool'), digital: [] };
    for (const f of P.byKind('skill')) (DIGITAL.has(E.norm(f.text)) ? groups.digital : groups.commercial).push(f);
    for (const [key, facts] of Object.entries(groups)) {
      pickGreedy(facts, m, covered, 6).forEach((f, i) => lines.push({ id: `k.${key}.${i + 1}`, section: 'skills', kind: 'fact', text: f.text, fact_ids: [f.id], group: GROUPS[lang][key] }));
    }
    const [edu, certs] = eduIds(P);
    lines.push(...factLines(P, edu, 'education', 'd'), ...factLines(P, certs, 'certifications', 'c'));
    const ll = langLine(P); if (ll) lines.push(ll);
    const extras = ['avail.immediate', 'mobility.idf'].filter((id) => P.fact(id) && E.usable(P.fact(id)));
    if (extras.length) lines.push({ id: 'x1', section: 'extras', kind: 'fact', text: extras.map((id) => P.value(id)).join(' · '), fact_ids: extras });
    return { version: 1, language: lang, design_profile: best.design_profile, photo_mode: best.photo_mode, ats_mode: best.ats_mode, paper: c.paper || 'A4',
      draft: !profileValidated, name: P.value('id.name', 'Candidat'), contact: E.contactLines(P), lines, experiences: blocks,
      section_order: ['summary', 'experience', 'skills', 'education', 'certifications', 'languages'], section_titles: TITLES[lang],
      keywords_covered: m.coverage.filter((x) => x.covered).map((x) => x.term), gaps: m.missing.map((x) => ({ keyword: x.requirement, why: x.note })), removed_lines: [], source: 'deterministic' };
  };
  E.cvFromAi = (payload, P, a, m, strat, profileValidated) => {
    const base = E.buildCvDeterministic(P, a, m, strat, profileValidated);
    const lines = []; const head = payload.headline || {};
    lines.push({ id: 'h1', section: 'headline', kind: 'headline', text: String(head.text || strat.best.title), fact_ids: (head.fact_ids || []).map(String), offer_terms: (head.offer_terms || []).map(String) });
    (payload.summary || []).forEach((s, i) => lines.push({ id: `s${i + 1}`, section: 'summary', kind: 'claim', text: String(s.text || ''), fact_ids: (s.fact_ids || []).map(String) }));
    const blocks = new Map(base.experiences.map((b) => [b.experience_id, Object.assign({}, b, { bullet_ids: [] })]));
    const seen = new Set();
    for (const ex of payload.experiences || []) {
      const eid = String(ex.experience_id || ''); if (!blocks.has(eid) || seen.has(eid)) continue; seen.add(eid);
      (ex.bullets || []).forEach((bl, k) => { const id = `e.${eid.split('.').slice(1).join('.')}.b${k + 1}`; lines.push({ id, section: 'experience', kind: 'claim', text: String(bl.text || ''), fact_ids: (bl.fact_ids || []).map(String), experience_id: eid }); blocks.get(eid).bullet_ids.push(id); });
    }
    for (const [eid, b] of blocks) if (!seen.has(eid)) for (const ln of base.lines) if (ln.experience_id === eid) { lines.push(ln); b.bullet_ids.push(ln.id); }
    (payload.skills || []).forEach((g, gi) => (g.items || []).forEach((it, i) => lines.push({ id: `k${gi + 1}.${i + 1}`, section: 'skills', kind: 'claim', text: String(it.label || ''), fact_ids: (it.fact_ids || []).map(String), group: String(g.group || '') })));
    const usable = new Set(P.usableFacts().map((f) => f.id));
    const [edu0, certs0] = eduIds(P);
    const edu = (payload.education_ids || []).filter((i) => usable.has(i)); const certs = (payload.certification_ids || []).filter((i) => usable.has(i) && i !== 'cert.toeic');
    lines.push(...factLines(P, edu.length ? edu : edu0, 'education', 'd'), ...factLines(P, certs.length ? certs : certs0, 'certifications', 'c'));
    const ll = langLine(P); if (ll) lines.push(ll);
    lines.push(...base.lines.filter((l) => l.section === 'extras'));
    return Object.assign({}, base, { lines, experiences: [...blocks.values()], keywords_covered: (payload.keywords_covered || base.keywords_covered).map(String), gaps: payload.gaps || base.gaps, source: 'ai' });
  };
  E.sectionLines = (doc, section) => doc.lines.filter((l) => l.section === section);
  E.lineById = (doc, id) => doc.lines.find((l) => l.id === id) || null;
  E.syncBlocks = (doc) => { for (const b of doc.experiences) b.bullet_ids = b.bullet_ids.filter((id) => E.lineById(doc, id)); return doc; };
  E.cvPlainText = (doc) => {
    const out = [doc.name, doc.contact.join(' | ')];
    for (const l of E.sectionLines(doc, 'headline').concat(E.sectionLines(doc, 'extras'))) out.push(`[${l.id}] ${l.text}`);
    for (const sec of doc.section_order) {
      const title = doc.section_titles[sec] || sec;
      if (sec === 'experience') {
        out.push(`\n## ${title}`);
        for (const b of doc.experiences) { out.push(`${b.title} — ${b.company} (${b.city}) · ${b.period}`); for (const id of b.bullet_ids) { const l = E.lineById(doc, id); if (l) out.push(`  [${l.id}] ${l.text}`); } }
        continue;
      }
      const ls = E.sectionLines(doc, sec); if (!ls.length) continue;
      out.push(`\n## ${title}`);
      if (sec === 'skills') { const g = {}; for (const l of ls) (g[l.group || ''] = g[l.group || ''] || []).push(l); for (const [k, items] of Object.entries(g)) out.push(`${k} : ` + items.map((i) => `[${i.id}] ${i.text}`).join(', ')); }
      else ls.forEach((l) => out.push(`[${l.id}] ${l.text}`));
    }
    return out.join('\n');
  };
  E.trimForSpace = (doc, step) => {
    const d = JSON.parse(JSON.stringify(doc)); const drop = new Set();
    if (step >= 1) for (const b of d.experiences) if (!b.featured && b.bullet_ids.length > 1) b.bullet_ids.slice(1).forEach((x) => drop.add(x));
    if (step >= 2) { const g = {}; for (const l of E.sectionLines(d, 'skills')) (g[l.group || ''] = g[l.group || ''] || []).push(l); for (const ls of Object.values(g)) ls.slice(4).forEach((l) => drop.add(l.id)); E.sectionLines(d, 'certifications').slice(1).forEach((l) => drop.add(l.id)); }
    if (step >= 3) { for (const b of d.experiences) if (b.featured && b.bullet_ids.length > 3) b.bullet_ids.slice(3).forEach((x) => drop.add(x)); E.sectionLines(d, 'summary').slice(2).forEach((l) => drop.add(l.id)); }
    d.removed_lines = (d.removed_lines || []).concat(d.lines.filter((l) => drop.has(l.id)).map((l) => ({ id: l.id, text: l.text, reasons: ['place (1 page)'] })));
    d.lines = d.lines.filter((l) => !drop.has(l.id));
    return E.syncBlocks(d);
  };

  // ─── Lettre ───────────────────────────────────────────────────────────────
  const MONTHS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
  const MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  E.placeDate = (P, lang, today) => {
    today = today || new Date(); const cf = P.fact('contact.city'); const city = (cf && cf.data.city) || 'Paris';
    return lang === 'en' ? `${city}, ${MONTHS_EN[today.getMonth()]} ${today.getDate()}, ${today.getFullYear()}` : `${city}, le ${today.getDate() === 1 ? '1er' : today.getDate()} ${MONTHS_FR[today.getMonth()]} ${today.getFullYear()}`;
  };
  const introSentence = (offer) => { const ls = offer.text.split('\n').map((l) => l.trim()).filter(Boolean); for (const l of ls.slice(1, 4)) if (l.length > 40 && !/^\s*[-•*]/.test(l) && !l.slice(0, 25).includes(':')) return l.replace(/\.$/, ''); return ''; };
  E.buildLetterDeterministic = (P, a, m, strat, offer, profileValidated, today) => {
    const lang = a.language_of_offer === 'en' ? 'en' : 'fr';
    const company = a.company && a.company !== 'UNKNOWN' ? a.company : lang === 'en' ? 'your company' : 'votre entreprise';
    const title = strat.best.title; const lines = [];
    const add = (sec, kind, text, ids, quote) => lines.push({ id: `${sec.toLowerCase()}${lines.filter((l) => l.section === sec).length + 1}`, section: sec, kind, text, fact_ids: ids || [], offer_quote: quote || '' });
    const up = (strat.best.experiences_up || []).map((e) => P.fact(e)).filter(Boolean);
    const main = up[0] || P.experiences()[0];
    const covered = new Set(m.coverage.filter((c) => c.covered).flatMap((c) => c.fact_ids));
    const missions = (a.missions || []).filter((x) => x.length > 15).slice(0, 2);
    if (missions.length) { const q = missions[0].replace(/\.$/, ''); lang === 'en' ? add('HOOK', 'offer_ref', `Your ${title} opening puts one mission first: “${q}”.`, [], q) : add('HOOK', 'offer_ref', `Votre offre de ${title} place une mission au premier plan : « ${q} ».`, [], q); }
    if (main) {
      const tasks = P.children(main.id).slice().sort((x, y) => (!covered.has(x.id)) - (!covered.has(y.id)));
      const task = tasks.find((t) => t.kind === 'responsibility');
      if (task) {
        const d = main.data;
        if (lang === 'en') add('HOOK', 'claim', `${d.current ? 'I currently work' : 'I worked'} as ${d.title} at ${d.company}: ${lowerFirst(task.text)}.`, [main.id, task.id]);
        else add('HOOK', 'claim', `${d.current ? "J'exerce actuellement" : "J'ai exercé"} comme ${d.title} chez ${d.company} : ${lowerFirst(task.text)}.`, [main.id, task.id]);
      }
    }
    if (missions.length > 1) {
      const q = missions[1].replace(/\.$/, '');
      if (lang === 'en') { add('WHY_ROLE', 'offer_ref', `The role also involves this: “${q}”.`, [], q); add('WHY_ROLE', 'projection', 'That combination of field work and follow-up is exactly the scope I am looking for.'); }
      else { add('WHY_ROLE', 'offer_ref', `Le poste comprend aussi : « ${q} ».`, [], q); add('WHY_ROLE', 'projection', 'C\'est précisément ce périmètre, de la prise de contact au suivi, que je recherche.'); }
    }
    const intro = introSentence(offer);
    if (intro) {
      if (lang === 'en') { add('WHY_COMPANY', 'offer_ref', `Your posting describes the company this way: “${intro}”.`, [], intro); add('WHY_COMPANY', 'projection', `I would like to contribute to that development at ${company}.`); }
      else { add('WHY_COMPANY', 'offer_ref', `Votre annonce présente l'entreprise ainsi : « ${intro} ».`, [], intro); add('WHY_COMPANY', 'projection', `C'est dans ce contexte que je souhaite m'investir chez ${company}.`); }
    }
    const results = P.byKind('result').slice().sort((x, y) => ((!covered.has(x.id)) - (!covered.has(y.id))) || ((!E.extractNumbers(x.text).length) - (!E.extractNumbers(y.text).length)));
    const usedParents = new Set();
    for (const f of results) {
      if (usedParents.size >= 3 || !f.parent || usedParents.has(f.parent)) continue;
      const par = P.fact(f.parent); if (!par) continue; usedParents.add(f.parent);
      add('PROOF', 'claim', lang === 'en' ? `At ${par.data.company}: ${lowerFirst(f.text)}.` : `Chez ${par.data.company} : ${lowerFirst(f.text)}.`, [f.id, par.id]);
    }
    add('VALUE', 'projection', lang === 'en' ? `I want to bring that same discipline to ${company}, starting with the priorities set in your posting.` : `Je souhaite apporter cette même rigueur à ${company}, en commençant par les priorités fixées dans votre annonce.`);
    const extras = ['avail.immediate', 'mobility.idf'].filter((id) => P.fact(id) && E.usable(P.fact(id)));
    if (extras.length) add('CLOSE', 'claim', lang === 'en' ? 'I am available immediately and can travel across the Île-de-France region.' : `Disponible immédiatement${extras.includes('mobility.idf') ? ' et mobile en Île-de-France' : ''}, je serais heureux d'échanger avec vous sur ce poste.`, extras);
    add('CLOSE', 'closing', lang === 'en' ? 'Thank you for your time and consideration.' : "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.");
    return { version: 1, language: lang, draft: !profileValidated, place_date: E.placeDate(P, lang, today),
      recipient: lang === 'en' ? `${company} — Recruitment team` : `${company} — Service recrutement`,
      subject: lang === 'en' ? `Application — ${title}` : `Objet : candidature au poste de ${title}`,
      salutation: lang === 'en' ? 'Dear Hiring Team,' : 'Madame, Monsieur,', lines, paragraph_order: ['HOOK', 'WHY_ROLE', 'WHY_COMPANY', 'PROOF', 'VALUE', 'CLOSE'],
      signature: P.value('id.name', 'Candidat'), removed_lines: [], source: 'deterministic' };
  };
  E.letterFromAi = (payload, P, base) => {
    const lines = [];
    for (const para of payload.paragraphs || []) {
      let role = String(para.role || 'PROOF').toUpperCase(); if (!base.paragraph_order.includes(role)) role = 'PROOF';
      for (const s of para.sentences || []) {
        let kind = String(s.kind || 'claim'); if (!['claim', 'offer_ref', 'projection', 'closing'].includes(kind)) kind = 'claim';
        const text = String(s.text || '').trim(); if (!text) continue;
        lines.push({ id: `${role.toLowerCase()}${lines.filter((l) => l.section === role).length + 1}`, section: role, kind, text, fact_ids: (s.fact_ids || []).map(String), offer_quote: String(s.offer_quote || '') });
      }
    }
    return Object.assign({}, base, { lines, subject: payload.subject ? String(payload.subject) : base.subject, salutation: payload.salutation ? String(payload.salutation) : base.salutation, signature: P.value('id.name', base.signature), source: 'ai' });
  };
  E.letterParagraphs = (letter) => letter.paragraph_order.map((r) => letter.lines.filter((l) => l.section === r).map((l) => l.text.trim()).filter(Boolean).join(' ')).filter(Boolean);
  E.letterChecks = (letter, a) => {
    const issues = []; const body = letter.lines.map((l) => l.text).join(' '); const full = E.norm(letter.subject + ' ' + body);
    if (a.company && a.company !== 'UNKNOWN' && !full.includes(E.norm(a.company))) issues.push({ severity: 'high', check: 'entreprise', detail: `« ${a.company} » absent de la lettre` });
    const tw = E.norm(a.job_title).split(' ').filter((w) => w.length > 3);
    if (tw.length && !tw.some((w) => full.includes(w))) issues.push({ severity: 'high', check: 'intitule', detail: 'intitulé du poste absent' });
    const refs = letter.lines.filter((l) => l.kind === 'offer_ref').length;
    if (refs < 2) issues.push({ severity: 'medium', check: 'personnalisation', detail: `${refs} élément(s) de l'annonce cité(s) (min 2)` });
    const words = E.wordCount(body); const [lo, hi] = ((sector(a.sector_id).letter_style || {}).length_words) || [200, 340];
    if (words < lo * 0.7 || words > hi * 1.25) issues.push({ severity: 'low', check: 'longueur', detail: `${words} mots (cible ${lo}-${hi})` });
    for (const l of letter.lines) for (const p of E.bannedFound(l.text).soft) issues.push({ severity: 'low', check: 'phrase_creuse', detail: `${l.id} : « ${p} »` });
    return issues;
  };

  // ─── Critique déterministe + points ───────────────────────────────────────
  const GENERIC = new Set(['cv', 'curriculum vitae', 'profil', 'candidat', 'commercial polyvalent', "chercheur d'emploi", 'profil junior']);
  E.deterministicCritique = (cv, a, m, report) => {
    const issues = []; const textN = E.norm(cv.lines.map((l) => l.text).join(' '));
    const headline = E.sectionLines(cv, 'headline').map((l) => l.text).join(' ');
    if (!headline || GENERIC.has(E.norm(headline))) issues.push({ severity: 'high', type: 'titre_generique', line_ids: ['h1'], problem: 'Titre absent ou générique', fix: "Reprendre l'intitulé exact du poste visé." });
    const summary = E.sectionLines(cv, 'summary');
    if (!summary.length) issues.push({ severity: 'medium', type: 'profil_absent', line_ids: [], problem: 'Pas de résumé de profil', fix: "Ajouter 2 phrases : qui, et la preuve la plus forte pour l'offre." });
    else if (summary.reduce((n, l) => n + l.text.length, 0) > 380) issues.push({ severity: 'low', type: 'profil_dense', line_ids: summary.map((l) => l.id), problem: 'Résumé trop long', fix: 'Réduire à 45 mots.' });
    for (const b of cv.experiences) if (b.featured && !b.bullet_ids.length) issues.push({ severity: 'high', type: 'experience_vide', line_ids: [], problem: `${b.title} sans puce`, fix: 'Ajouter 2-3 puces prouvées.' });
    for (const l of E.sectionLines(cv, 'experience')) if (l.text.length > 130) issues.push({ severity: 'low', type: 'puce_longue', line_ids: [l.id], problem: 'Puce > 130 caractères', fix: 'Couper à 110 caractères.' });
    const majorGaps = m.coverage.filter((c) => c.covered && c.priority === 'REQUIRED' && !E.supportedBy(c.term, textN)).map((c) => c.term);
    for (const t of majorGaps) issues.push({ severity: 'high', type: 'mot_cle_absent', line_ids: [], problem: `« ${t} » est prouvé mais absent du CV`, fix: `Intégrer « ${t} » dans une puce qui le prouve.` });
    for (const kw of a.keywords || []) { const n = textN.split(E.norm(kw.term)).length - 1; if (kw.term.length > 3 && n > 4) issues.push({ severity: 'medium', type: 'bourrage', line_ids: [], problem: `« ${kw.term} » répété ${n} fois`, fix: 'Garder 2 occurrences utiles.' }); }
    return { issues, major_gaps: majorGaps };
  };
  E.scoreEvents = (cv, letter, a, m, strat, reports, crit) => {
    const grid = DATA.scoring.events; const ev = []; const add = (k, r) => ev.push({ event: k, points: grid[k].points, label: grid[k].label, reason: r });
    if (cv) {
      const h = E.norm(E.sectionLines(cv, 'headline').map((l) => l.text).join(' '));
      const tw = E.norm(a.job_title).split(' ').filter((w) => w.length > 3);
      if (tw.length && tw.slice(0, 3).every((w) => h.includes(w))) add('good_title', "Titre aligné sur l'intitulé de l'offre"); else if (!h || GENERIC.has(h)) add('weak_title', 'Titre générique');
      if (cv.experiences.some((b) => b.featured)) add('good_experience_pick', 'Expériences les plus pertinentes mises en avant');
      const ds = (sector(a.sector_id).cv_style || {}).design;
      if (ds === cv.design_profile || cv.design_profile === 'hybrid_modern') add('design_fit', 'Design conforme au profil secteur / ATS');
      for (const t of (crit && crit.major_gaps) || []) add('major_gap', `« ${t} » prouvé mais absent`);
    }
    if (letter && letter.lines.filter((l) => l.kind === 'offer_ref').length >= 2) add('personalization', "≥ 2 éléments propres à l'annonce dans la lettre");
    for (const r of Object.values(reports)) for (let i = 0; i < (r.forbidden_hits || 0); i++) add('invented_fact', 'Fait interdit détecté (ligne supprimée)');
    return { events: ev, total: ev.reduce((n, e) => n + e.points, 0) };
  };

  // ─── Prompts ──────────────────────────────────────────────────────────────
  E.render = (name, vars) => {
    const p = DATA.prompts[name]; if (!p) throw new Error(`Prompt inconnu : ${name}`);
    let text = p.template;
    for (const [k, v] of Object.entries(vars)) text = text.split(`{{${k}}}`).join(typeof v === 'string' ? v : String(v));
    const left = text.match(/\{\{(\w+)\}\}/g);
    if (left) throw new Error(`Variables manquantes pour ${name} : ${[...new Set(left)].join(', ')}`);
    return text;
  };
  E.truthRules = (P) => { const terms = P.forbiddenTerms(); return E.render('_truth_rules', { forbidden_terms: terms.length ? terms.map((t) => `« ${t} »`).join(', ') : 'aucun' }); };
  E.factsTable = (P, includeContact) => P.usableFacts().filter((f) => includeContact || f.kind !== 'contact').map((f) => `${f.id} | ${f.kind}${f.parent ? ` (↳ ${f.parent})` : ''} | ${f.status} | ${f.text}`).join('\n');
  E.experiencesTable = (P) => P.experiences().map((e) => `${e.id} | ${e.data.title || ''} | ${e.data.company || ''} | ${e.data.period_label || ''}`).join('\n');
  E.commonVars = (P, a) => {
    const s = sector(a.sector_id); const c = country(a.country); const pick = {};
    for (const k of ['name', 'vocabulary', 'priorities', 'expectations', 'cv_style', 'letter_style', 'common_mistakes', 'useful_proofs']) pick[k] = s[k];
    const ana = Object.assign({}, a); delete ana.sector_scores;
    return { truth_rules: E.truthRules(P), facts_table: E.factsTable(P), experiences_table: E.experiencesTable(P), analysis_json: JSON.stringify(ana),
      sector_json: JSON.stringify(pick), country_json: JSON.stringify(c), sector_name: s.name || a.sector_id, country_name: c.name || 'France' };
  };
  E.tierFor = (task) => (DATA.models.artifact_tiers || {})[task] || 'default';

  // ─── Export Node ──────────────────────────────────────────────────────────
  if (typeof module !== 'undefined' && module.exports) module.exports = E;
  else root.PAIEngine = E;
}(typeof globalThis !== 'undefined' ? globalThis : this));
