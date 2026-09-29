/* PAI Studio — gabarits de documents (pdfmake) : 5 familles de CV et la lettre assortie à chacune.
 * Un gabarit ne fait QUE la mise en page : le texte vient des lignes du document, chacune liée à des faits
 * et validée (claim → evidence). Rien n'est ajouté, reformulé ou inventé ici.
 * Familles : premium_corporate, modern_commercial, minimal_executive, digital_creative, ats_hybrid.
 */
(function (root) {
  'use strict';
  const A4 = { w: 595.28, h: 841.89 };
  const INK = '#16191C';
  const INK2 = '#343B41';
  const MUTED = '#5D656B';
  const RULE = '#D9DCDF';

  // Palettes imprimables : deep = aplats (bandeaux, colonne), accent = titres et marqueurs, soft/tint = fonds légers,
  // gold = filets champagne (toujours discret), onDeep = texte sur aplat sombre.
  const PALETTES = {
    petrol: { label: 'Pétrole', deep: '#0F3A46', accent: '#1D6E82', soft: '#E4EFF2', tint: '#F2F7F8', gold: '#B08A4A', goldLight: '#E2C996', onDeep: '#F3F1EA', onDeepMuted: '#A7C2C9', tag: '#1E4B57' },
    navy: { label: 'Marine', deep: '#132A45', accent: '#1F4670', soft: '#E6ECF4', tint: '#F3F6FA', gold: '#A8864A', goldLight: '#DEC693', onDeep: '#F3F1EA', onDeepMuted: '#AEBFD3', tag: '#23405F' },
    graphite: { label: 'Graphite', deep: '#1E2227', accent: '#3A4148', soft: '#ECEDEE', tint: '#F6F6F5', gold: '#8C6D2C', goldLight: '#D8C08E', onDeep: '#F1EFE9', onDeepMuted: '#B3B8BC', tag: '#343A40' },
    forest: { label: 'Forêt', deep: '#16352D', accent: '#2F6B58', soft: '#E5EFEA', tint: '#F3F8F5', gold: '#A58A4E', goldLight: '#DCC794', onDeep: '#F2F1EA', onDeepMuted: '#AFC8BE', tag: '#24493F' },
    bordeaux: { label: 'Bordeaux', deep: '#3A1620', accent: '#6E2A3A', soft: '#F3E7EA', tint: '#FAF4F5', gold: '#A8864A', goldLight: '#E0C897', onDeep: '#F5EFEA', onDeepMuted: '#D3B3BA', tag: '#552430' },
  };
  const FAMILIES = ['premium_corporate', 'modern_commercial', 'minimal_executive', 'digital_creative', 'ats_hybrid'];
  const LEGACY_FAMILY = { hybrid_modern: 'ats_hybrid', ats_classic: 'ats_hybrid', human_premium: 'premium_corporate' };
  const DENSITY = { airy: { fs: 1, gap: 1.2 }, balanced: { fs: 1, gap: 1 }, compact: { fs: 0.955, gap: 0.78 } };
  const DENSITY_ORDER = ['airy', 'balanced', 'compact'];

  function registerFonts(pdfMake, vfs) {
    pdfMake.vfs = vfs;
    pdfMake.fonts = {
      Fira: { normal: 'FiraSans-Regular.ttf', bold: 'FiraSans-SemiBold.ttf', italics: 'FiraSans-Italic.ttf', bolditalics: 'FiraSans-Bold.ttf' },
      FiraMedium: { normal: 'FiraSans-Medium.ttf', bold: 'FiraSans-Bold.ttf', italics: 'FiraSans-Italic.ttf', bolditalics: 'FiraSans-Bold.ttf' },
      Serif: { normal: 'SourceSerif4-Regular.ttf', bold: 'SourceSerif4-SemiBold.ttf', italics: 'SourceSerif4-Italic.ttf', bolditalics: 'SourceSerif4-SemiBoldItalic.ttf' },
      Manrope: { normal: 'Manrope-Medium.ttf', bold: 'Manrope-ExtraBold.ttf', italics: 'Manrope-Medium.ttf', bolditalics: 'Manrope-ExtraBold.ttf' },
      ManropeBold: { normal: 'Manrope-Bold.ttf', bold: 'Manrope-ExtraBold.ttf', italics: 'Manrope-Bold.ttf', bolditalics: 'Manrope-ExtraBold.ttf' },
    };
  }

  const familyOf = (designId) => (FAMILIES.includes(designId) ? designId : LEGACY_FAMILY[designId] || 'ats_hybrid');

  function shade(hex, amount) {
    const n = parseInt(String(hex).replace('#', ''), 16);
    if (Number.isNaN(n)) return hex;
    const f = (c) => Math.max(0, Math.min(255, Math.round(c + (amount < 0 ? c : 255 - c) * amount)));
    return `#${[f((n >> 16) & 255), f((n >> 8) & 255), f(n & 255)].map((c) => c.toString(16).padStart(2, '0')).join('')}`;
  }

  function palette(name, customAccent) {
    const p = Object.assign({}, PALETTES[name] || PALETTES.petrol);
    if (customAccent && /^#[0-9a-f]{6}$/i.test(customAccent)) {
      p.accent = customAccent; p.deep = shade(customAccent, -0.45); p.soft = shade(customAccent, 0.88); p.tint = shade(customAccent, 0.94); p.tag = shade(customAccent, -0.25);
    }
    return p;
  }

  // ── Aides communes ──────────────────────────────────────────────────────────
  const lines = (E, doc, sec) => E.sectionLines(doc, sec);
  const skillGroups = (E, cv) => { const g = {}; lines(E, cv, 'skills').forEach((l) => (g[l.group || ''] = g[l.group || ''] || []).push(l.text)); return Object.entries(g); };
  const expBullets = (E, cv, b) => b.bullet_ids.map((id) => E.lineById(cv, id)).filter(Boolean);
  const draftLabel = (lang) => (lang === 'en' ? 'DRAFT — PROFILE NOT VALIDATED' : 'BROUILLON — PROFIL NON VALIDÉ');

  function stamp(lang, x, y) {
    return { absolutePosition: { x, y: y || 12 }, table: { body: [[{ text: draftLabel(lang), fontSize: 7.2, bold: true, color: '#8A2B12' }]] },
      layout: { hLineColor: () => '#8A2B12', vLineColor: () => '#8A2B12', hLineWidth: () => 0.8, vLineWidth: () => 0.8, paddingLeft: () => 5, paddingRight: () => 5, paddingTop: () => 1.5, paddingBottom: () => 1.5, fillColor: () => '#FFFFFF' } };
  }

  // Marqueur de puce vectoriel (hors couche texte : extraction ATS propre).
  const marker = (shape, color, size) => {
    if (shape === 'dash') return [{ type: 'line', x1: 1, y1: 6.2, x2: 6, y2: 6.2, lineWidth: 0.9, lineColor: color }];
    if (shape === 'dot') return [{ type: 'ellipse', x: 3, y: 5.9, r1: 1.7, r2: 1.7, color }];
    const s = size || 3.4;
    return [{ type: 'rect', x: 1, y: 6.2 - s / 2, w: s, h: s, color }];
  };
  function bulletList(items, o) {
    return items.map((l) => ({ columns: [{ width: o.indent || 10, canvas: marker(o.shape, o.color, o.size) },
      { width: '*', text: l.text, fontSize: o.fs, color: o.ink || INK, lineHeight: o.lh || 1.22 }], columnGap: 0, margin: [o.left || 0, 0, 0, o.gap] }));
  }

  // Chiffres clés : même ligne (liée aux faits), coupée en « chiffre » + « reste ». Aucune reformulation.
  const NUM = /(^|[\s(])([+−-]?\d{1,3}(?:[   .,]\d{3})*(?:[.,]\d+)?\s?(?:%|[kKM]€|€|\+)?(?:\s?\/\s?[a-zéûA-Z]+)?)/;
  function highlights(E, cv, max) {
    const out = []; const seen = new Set();
    const exps = cv.experiences.slice().sort((a, b) => Number(!!b.featured) - Number(!!a.featured));
    for (const b of exps) {
      for (const l of expBullets(E, cv, b)) {
        const m = NUM.exec(l.text); if (!m || seen.has(b.experience_id)) continue;
        const big = m[2].trim(); if (!/\d/.test(big) || big.length > 14) continue;
        const rest = (l.text.slice(0, m.index + m[1].length) + l.text.slice(m.index + m[0].length)).replace(/\s{2,}/g, ' ').replace(/^[\s,:;·–-]+|[\s,:;·–-]+$/g, '');
        if (rest.length < 4) continue;
        out.push({ id: l.id, big, rest, company: b.company }); seen.add(b.experience_id);
        break;
      }
      if (out.length >= max) break;
    }
    return out.length >= 2 ? out : [];
  }

  // Langues : « Anglais (courant, TOEIC 915/990) » → niveau lu dans le texte du fait (jamais deviné).
  const LEVEL = [['natif', 5], ['native', 5], ['bilingue', 5], ['bilingual', 5], ['courant', 4], ['fluent', 4], ['c1', 4], ['c2', 5], ['b2', 3], ['intermédiaire', 3], ['intermediate', 3], ['b1', 3], ['notions', 2], ['basic', 2], ['a2', 2], ['a1', 1]];
  function languageItems(E, cv) {
    const out = [];
    for (const l of lines(E, cv, 'languages')) {
      for (const part of l.text.split(/\s·\s|;\s/)) {
        const m = /^\s*([^()]+?)\s*\(([^)]*)\)\s*$/.exec(part);
        const name = m ? m[1].trim() : part.trim(); const detail = m ? m[2] : '';
        const n = E.norm(detail); const lvl = (LEVEL.find(([w]) => new RegExp(`(^|[^a-z])${w}([^a-z]|$)`).test(n)) || [null, 0])[1];
        if (name) out.push({ name, detail, level: lvl });
      }
    }
    return out;
  }
  const dots = (level, on, off) => {
    const c = []; for (let i = 0; i < 5; i++) c.push({ type: 'ellipse', x: 3 + i * 8.2, y: 4.5, r1: 2.6, r2: 2.6, color: i < level ? on : off });
    return c;
  };

  function contactItems(cv, lang) {
    const L = lang === 'en' ? { mail: 'Email', tel: 'Phone', web: 'LinkedIn', city: 'Location' } : { mail: 'E-mail', tel: 'Téléphone', web: 'LinkedIn', city: 'Ville' };
    return (cv.contact || []).map((c) => ({ label: /@/.test(c) ? L.mail : /linkedin|https?:|www\./i.test(c) ? L.web : /\d{2}.*\d{2}/.test(c) ? L.tel : L.city, value: c }));
  }

  const photoImage = (ctx, size, shape) => {
    if (!ctx.photo || !ctx.photoMode || ctx.photoMode === 'OFF') return null;
    const src = shape === 'square' ? ctx.photo.square : ctx.photo.circle;
    const s = Math.round(size * (ctx.photo.scale || 1));
    return src ? { image: src, width: s, height: s } : null;
  };

  function info(cv, heads, kind) {
    return { title: `${kind} — ${cv.name}`, author: cv.name, subject: heads.map((l) => l.text).join(' '), keywords: (cv.keywords_covered || []).join(', '), creator: 'PAI — Personal Application Intelligence' };
  }

  // spread (1 → 2) : page trop vide (profil court) → les espacements s'ouvrent et le texte grandit un peu (+10 % au plus).
  function ctxScale(ctx) {
    const d = DENSITY[ctx.density] || DENSITY.balanced; const k = Math.min(2, Math.max(1, ctx.spread || 1));
    return { fs: d.fs * (1 + (k - 1) * 0.1), g: d.gap * k };
  }

  // ── 1. Premium Corporate ─────────────────────────────────────────────────────
  function premiumCorporate(E, cv, ctx) {
    const P = ctx.palette; const { fs, g } = ctxScale(ctx); const M = { l: 46, r: 46, t: 34, b: 32 };
    const heads = lines(E, cv, 'headline'); const extras = lines(E, cv, 'extras'); const photo = photoImage(ctx, 74);
    const headStack = [
      { text: cv.name, font: 'Serif', bold: true, fontSize: 25 * fs, color: P.onDeep, lineHeight: 1.02 },
      ...heads.map((l) => ({ text: l.text, font: 'FiraMedium', fontSize: 11.4 * fs, color: P.goldLight, margin: [0, 5, 0, 0] })),
      { text: cv.contact.join('    ·    '), fontSize: 8.2 * fs, color: P.onDeepMuted, margin: [0, 10, 0, 0] },
      ...extras.map((l) => ({ text: l.text, font: 'FiraMedium', fontSize: 8.2 * fs, color: P.goldLight, margin: [0, 3, 0, 0] })),
    ];
    const band = { table: { widths: ['*'], body: [[{ columns: photo ? [{ stack: headStack, width: '*' }, { stack: [photo], width: photo.width }] : [{ stack: headStack, width: '*' }],
      columnGap: 20, margin: [M.l - 4, 28, M.r - 4, 22], fillColor: P.deep }]] }, layout: 'noBorders', margin: [-M.l, -M.t, -M.r, 0] };
    const goldRule = { canvas: [{ type: 'line', x1: -M.l, y1: 0, x2: A4.w - M.l, y2: 0, lineWidth: 2.4, lineColor: P.gold }], margin: [0, 0, 0, 4] };
    const sec = (key) => ({ stack: [{ text: cv.section_titles[key], font: 'Serif', bold: true, fontSize: 12.6 * fs, color: P.deep, margin: [0, 12 * g, 0, 0] },
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: 30, y2: 0, lineWidth: 1.6, lineColor: P.gold }], margin: [0, 3, 0, 6 * g] }] });
    const content = [band, goldRule];
    const summary = lines(E, cv, 'summary');
    if (summary.length) content.push(sec('summary'), { text: summary.map((l) => l.text).join(' '), fontSize: 9.6 * fs, lineHeight: 1.3, color: INK2 });
    content.push(sec('experience'));
    for (const b of cv.experiences) {
      content.push({ stack: [
        { columns: [{ text: b.title, bold: true, fontSize: 10.3 * fs, color: INK, width: '*' }, { text: b.period, fontSize: 8.4 * fs, color: MUTED, width: 'auto', alignment: 'right', margin: [0, 1.5, 0, 0] }], columnGap: 10 },
        { text: [{ text: b.company, font: 'FiraMedium', color: P.accent }, b.city ? { text: `   ${b.city}`, color: MUTED } : ''], fontSize: 8.8 * fs, margin: [0, 1.5, 0, 3.5] },
        ...bulletList(expBullets(E, cv, b), { shape: 'square', color: P.gold, fs: 9.3 * fs, gap: 2 * g, size: 3.2 }),
      ], margin: [0, 0, 0, 7 * g], unbreakable: true });
    }
    const groups = skillGroups(E, cv);
    if (groups.length) {
      content.push(sec('skills'));
      groups.forEach(([grp, items]) => content.push({ columns: [{ text: grp, width: 78, font: 'FiraMedium', fontSize: 8.8 * fs, color: P.accent }, { text: items.join('  ·  '), width: '*', fontSize: 9.2 * fs, lineHeight: 1.2 }], columnGap: 10, margin: [0, 0, 0, 3 * g] }));
    }
    const cols = ['education', 'certifications', 'languages'].map((k) => [k, lines(E, cv, k)]).filter(([, ls]) => ls.length);
    if (cols.length) {
      content.push({ columns: cols.map(([k, ls]) => ({ width: '*', stack: [sec(k), ...ls.map((l) => ({ text: l.text, fontSize: 9 * fs, lineHeight: 1.2, margin: [0, 0, 0, 3] }))] })), columnGap: 18 });
    }
    if (cv.draft) content.push(stamp(cv.language, A4.w - M.r - 172, 10));
    return { pageSize: 'A4', pageMargins: [M.l, M.t, M.r, M.b], content, defaultStyle: { font: 'Fira', fontSize: 9.4 * fs, color: INK, lineHeight: 1.16 }, info: info(cv, heads, 'CV') };
  }

  // ── 2. Modern Commercial ─────────────────────────────────────────────────────
  function modernCommercial(E, cv, ctx) {
    const P = ctx.palette; const { fs, g } = ctxScale(ctx); const M = { l: 50, r: 36, t: 36, b: 30 };
    const heads = lines(E, cv, 'headline'); const extras = lines(E, cv, 'extras'); const photo = photoImage(ctx, 70);
    const headStack = [
      { text: cv.name, font: 'Manrope', bold: true, fontSize: 25 * fs, color: INK, lineHeight: 1.02 },
      ...heads.map((l) => ({ text: l.text, font: 'ManropeBold', fontSize: 12.4 * fs, color: P.accent, margin: [0, 4, 0, 0] })),
      { text: cv.contact.join('   |   '), fontSize: 8.3 * fs, color: MUTED, margin: [0, 7, 0, 0] },
      ...extras.map((l) => ({ text: l.text, font: 'FiraMedium', fontSize: 8.3 * fs, color: P.gold, margin: [0, 2.5, 0, 0] })),
    ];
    const content = [{ columns: photo ? [{ stack: headStack, width: '*' }, { stack: [photo], width: photo.width }] : [{ stack: headStack, width: '*' }], columnGap: 16 }];
    const hl = highlights(E, cv, 3);
    if (hl.length) {
      content.push({ table: { widths: hl.map(() => '*'), body: [hl.map((h) => ({ stack: [{ text: h.big, font: 'Manrope', bold: true, fontSize: 15.5 * fs, color: P.accent },
        { text: h.rest, fontSize: 7.7 * fs, color: INK2, lineHeight: 1.15, margin: [0, 1, 0, 0] }, { text: h.company, fontSize: 7 * fs, color: MUTED, margin: [0, 2, 0, 0] }], fillColor: P.soft }))] },
      layout: { hLineWidth: () => 0, vLineWidth: (i, node) => (i === 0 || i === node.table.widths.length ? 0 : 7), vLineColor: () => '#FFFFFF', paddingLeft: () => 10, paddingRight: () => 8, paddingTop: () => 7, paddingBottom: () => 7 },
      margin: [0, 13 * g, 0, 2] });
    }
    const secT = (key, color) => ({ columns: [{ width: 12, canvas: [{ type: 'rect', x: 0, y: 3.2, w: 6, h: 6, color: P.gold }] }, { width: '*', text: cv.section_titles[key].toUpperCase(), font: 'Manrope', bold: true, fontSize: 9.2 * fs, color: color || P.accent }], margin: [0, 12 * g, 0, 5 * g] });
    const main = [];
    const summary = lines(E, cv, 'summary');
    if (summary.length) main.push(secT('summary'), { text: summary.map((l) => l.text).join(' '), fontSize: 9.4 * fs, lineHeight: 1.28, color: INK2 });
    main.push(secT('experience'));
    for (const b of cv.experiences) {
      main.push({ stack: [
        { text: b.title, font: 'ManropeBold', fontSize: 10.4 * fs, color: INK },
        { columns: [{ text: [{ text: b.company, font: 'FiraMedium', color: P.accent }, b.city ? { text: ` · ${b.city}`, color: MUTED } : ''], fontSize: 8.7 * fs, width: '*' }, { text: b.period, fontSize: 8.2 * fs, color: MUTED, width: 'auto' }], margin: [0, 1, 0, 3.5] },
        ...bulletList(expBullets(E, cv, b), { shape: 'square', color: P.accent, fs: 9.2 * fs, gap: 2 * g, size: 3.3 }),
      ], margin: [0, 0, 0, 7 * g], unbreakable: true });
    }
    const side = [];
    const groups = skillGroups(E, cv);
    if (groups.length) {
      side.push(secT('skills', P.deep));
      groups.forEach(([grp, items]) => side.push({ text: grp, font: 'FiraMedium', fontSize: 8.2 * fs, color: MUTED, margin: [0, 2, 0, 3] },
        { text: items.flatMap((t, i) => [{ text: ` ${t} `, background: '#FFFFFF', color: INK }, i < items.length - 1 ? { text: '  ', fontSize: 4 } : '']), fontSize: 8.6 * fs, lineHeight: 1.75, margin: [0, 0, 0, 4 * g] }));
    }
    for (const k of ['languages', 'education', 'certifications']) {
      const ls = lines(E, cv, k); if (!ls.length) continue;
      side.push(secT(k, P.deep), ...ls.map((l) => ({ text: l.text, fontSize: 8.7 * fs, lineHeight: 1.22, margin: [0, 0, 0, 3.5] })));
    }
    content.push({ columns: [{ width: '*', stack: main }, side.length ? { width: 168, table: { widths: ['*'], body: [[{ stack: side, fillColor: P.tint, margin: [4, 0, 4, 8] }]] }, layout: { hLineWidth: () => 0, vLineWidth: () => 0, paddingLeft: () => 8, paddingRight: () => 8, paddingTop: () => 2, paddingBottom: () => 6 }, margin: [0, 8, 0, 0] } : { width: 0, text: '' }], columnGap: 20 });
    if (cv.draft) content.push(stamp(cv.language, A4.w - M.r - 172, 10));
    return { pageSize: 'A4', pageMargins: [M.l, M.t, M.r, M.b],
      background: () => ({ canvas: [{ type: 'rect', x: 0, y: 0, w: 9, h: A4.h, color: P.accent }, { type: 'rect', x: 9, y: 0, w: 2, h: A4.h, color: P.gold }] }),
      content, defaultStyle: { font: 'Fira', fontSize: 9.3 * fs, color: INK, lineHeight: 1.16 }, info: info(cv, heads, 'CV') };
  }

  // ── 3. Minimal Executive ─────────────────────────────────────────────────────
  function minimalExecutive(E, cv, ctx) {
    const P = ctx.palette; const { fs, g } = ctxScale(ctx); const M = { l: 60, r: 58, t: 50, b: 38 };
    const heads = lines(E, cv, 'headline'); const extras = lines(E, cv, 'extras'); const photo = photoImage(ctx, 60);
    const headStack = [
      { text: cv.name, font: 'Serif', fontSize: 29 * fs, color: INK, lineHeight: 1 },
      ...heads.map((l) => ({ text: l.text, font: 'Serif', italics: true, fontSize: 12.6 * fs, color: P.gold, margin: [0, 5, 0, 0] })),
      { text: cv.contact.join('     '), fontSize: 8.1 * fs, color: MUTED, margin: [0, 10, 0, 0] },
      ...extras.map((l) => ({ text: l.text, fontSize: 8.1 * fs, color: P.accent, margin: [0, 3, 0, 0] })),
    ];
    const content = [{ columns: photo ? [{ stack: headStack, width: '*' }, { stack: [photo], width: photo.width }] : [{ stack: headStack, width: '*' }], columnGap: 16 },
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: A4.w - M.l - M.r, y2: 0, lineWidth: 0.5, lineColor: RULE }], margin: [0, 16 * g, 0, 4 * g] }];
    const LABEL_W = 92;
    const row = (key, stackContent) => ({ columns: [{ width: LABEL_W, text: cv.section_titles[key].toUpperCase(), font: 'FiraMedium', fontSize: 7.6 * fs, color: MUTED, margin: [0, 2.2, 0, 0] }, { width: '*', stack: stackContent }], columnGap: 14, margin: [0, 10 * g, 0, 0] });
    const summary = lines(E, cv, 'summary');
    if (summary.length) content.push(row('summary', [{ text: summary.map((l) => l.text).join(' '), font: 'Serif', fontSize: 10.2 * fs, lineHeight: 1.34, color: INK2 }]));
    content.push(row('experience', cv.experiences.map((b) => ({ stack: [
      { columns: [{ text: [{ text: b.title, bold: true }, { text: `   ${b.company}`, font: 'Serif', italics: true, color: INK2 }], fontSize: 10.1 * fs, width: '*' }, { text: b.period, fontSize: 8.1 * fs, color: MUTED, width: 'auto', margin: [0, 1.5, 0, 0] }], columnGap: 8 },
      b.city ? { text: b.city, fontSize: 8 * fs, color: MUTED, margin: [0, 0.5, 0, 0] } : { text: '' },
      { stack: bulletList(expBullets(E, cv, b), { shape: 'dash', color: P.gold, fs: 9.3 * fs, gap: 1.8 * g, indent: 11 }), margin: [0, 3, 0, 0] },
    ], margin: [0, 0, 0, 8 * g], unbreakable: true }))));
    const groups = skillGroups(E, cv);
    if (groups.length) content.push(row('skills', groups.map(([grp, items]) => ({ text: [{ text: `${grp}   `, font: 'FiraMedium', color: P.accent }, items.join('  ·  ')], fontSize: 9.1 * fs, lineHeight: 1.22, margin: [0, 0, 0, 3] }))));
    for (const k of ['education', 'certifications', 'languages']) {
      const ls = lines(E, cv, k); if (ls.length) content.push(row(k, ls.map((l) => ({ text: l.text, fontSize: 9.1 * fs, lineHeight: 1.22, margin: [0, 0, 0, 2.5] }))));
    }
    if (cv.draft) content.push(stamp(cv.language, A4.w - M.r - 172, 14));
    return { pageSize: 'A4', pageMargins: [M.l, M.t, M.r, M.b], content, defaultStyle: { font: 'Fira', fontSize: 9.3 * fs, color: INK, lineHeight: 1.16 }, info: info(cv, heads, 'CV') };
  }

  // ── 4. Digital Creative ──────────────────────────────────────────────────────
  function digitalCreative(E, cv, ctx) {
    const P = ctx.palette; const { fs, g } = ctxScale(ctx); const SB = 186; const M = { t: 30, b: 24 };
    const heads = lines(E, cv, 'headline'); const extras = lines(E, cv, 'extras');
    const photo = ctx.photoMode === 'SIDEBAR' || ctx.photoMode === 'HEADER' ? photoImage(ctx, 92) : null;
    const side = [];
    if (photo) side.push({ stack: [{ canvas: [{ type: 'ellipse', x: 50, y: 50, r1: 50, r2: 50, lineWidth: 1.6, lineColor: P.gold }] }, Object.assign(photo, { margin: [4, -96, 0, 0] })], margin: [18, 0, 0, 14] });
    side.push({ text: cv.name, font: 'Manrope', bold: true, fontSize: 19 * fs, color: P.onDeep, lineHeight: 1.05 });
    heads.forEach((l) => side.push({ text: l.text, font: 'ManropeBold', fontSize: 9.8 * fs, color: P.goldLight, margin: [0, 5, 0, 0], lineHeight: 1.15 }));
    extras.forEach((l) => side.push({ text: l.text, fontSize: 8 * fs, color: P.onDeepMuted, margin: [0, 5, 0, 0] }));
    const sideTitle = (t) => ({ text: t.toUpperCase(), font: 'ManropeBold', fontSize: 8 * fs, color: P.goldLight, margin: [0, 15 * g, 0, 6] });
    side.push(sideTitle(cv.language === 'en' ? 'Contact' : 'Contact'));
    contactItems(cv, cv.language).forEach((c) => side.push({ text: [{ text: `${c.label}\n`, fontSize: 6.8 * fs, color: P.onDeepMuted }, { text: c.value, fontSize: 8.2 * fs, color: P.onDeep }], lineHeight: 1.15, margin: [0, 0, 0, 5] }));
    const groups = skillGroups(E, cv);
    if (groups.length) {
      side.push(sideTitle(cv.section_titles.skills));
      groups.forEach(([grp, items]) => side.push({ text: grp, fontSize: 7.2 * fs, color: P.onDeepMuted, margin: [0, 2, 0, 3] },
        { text: items.flatMap((t, i) => [{ text: ` ${t} `, background: P.tag, color: P.onDeep }, i < items.length - 1 ? { text: ' ', fontSize: 5 } : '']), fontSize: 8.1 * fs, lineHeight: 1.8, margin: [0, 0, 0, 4] }));
    }
    const langs = languageItems(E, cv);
    if (langs.length) {
      side.push(sideTitle(cv.section_titles.languages));
      langs.forEach((x) => side.push({ columns: [{ width: '*', text: [{ text: x.name, color: P.onDeep }, x.detail ? { text: `\n${x.detail}`, fontSize: 6.9 * fs, color: P.onDeepMuted } : ''], fontSize: 8.2 * fs, lineHeight: 1.1 },
        x.level ? { width: 42, canvas: dots(x.level, P.goldLight, P.tag) } : { width: 0, text: '' }], columnGap: 4, margin: [0, 0, 0, 5] }));
    }
    const main = [];
    const secT = (key) => ({ columns: [{ width: 16, canvas: [{ type: 'rect', x: 0, y: 2.5, w: 8, h: 8, r: 1.5, color: P.accent }] }, { width: '*', text: cv.section_titles[key], font: 'Manrope', bold: true, fontSize: 11 * fs, color: P.deep }], margin: [0, 10 * g, 0, 6 * g] });
    const summary = lines(E, cv, 'summary');
    if (summary.length) main.push(secT('summary'), { text: summary.map((l) => l.text).join(' '), fontSize: 9.4 * fs, lineHeight: 1.3, color: INK2 });
    main.push(secT('experience'));
    for (const b of cv.experiences) {
      main.push({ columns: [{ width: 14, canvas: [{ type: 'ellipse', x: 4, y: 6, r1: 3.6, r2: 3.6, color: b.featured ? P.accent : '#FFFFFF', lineColor: P.accent, lineWidth: 1.2 }] },
        { width: '*', stack: [
          { text: b.title, font: 'ManropeBold', fontSize: 10.2 * fs, color: INK },
          { text: [{ text: ` ${b.period} `, background: P.soft, color: P.deep }, { text: `  ${b.company}`, font: 'FiraMedium', color: P.accent }, b.city ? { text: ` · ${b.city}`, color: MUTED } : ''], fontSize: 8.3 * fs, margin: [0, 2, 0, 3.5] },
          ...bulletList(expBullets(E, cv, b), { shape: 'dot', color: P.gold, fs: 9.1 * fs, gap: 1.9 * g, indent: 9 }),
        ] }], columnGap: 2, margin: [0, 0, 0, 7 * g], unbreakable: true });
    }
    for (const k of ['education', 'certifications']) {
      const ls = lines(E, cv, k); if (ls.length) main.push(secT(k), ...ls.map((l) => ({ text: l.text, fontSize: 9 * fs, lineHeight: 1.22, margin: [16, 0, 0, 3] })));
    }
    const content = [{ columns: [{ width: SB, stack: side, margin: [22, 4, 16, 0] }, { width: '*', stack: main, margin: [22, 0, 32, 0] }], columnGap: 0 }];
    if (cv.draft) content.push(stamp(cv.language, A4.w - 32 - 172, 8));
    return { pageSize: 'A4', pageMargins: [0, M.t, 0, M.b],
      background: () => ({ canvas: [{ type: 'rect', x: 0, y: 0, w: SB, h: A4.h, color: P.deep }, { type: 'rect', x: SB, y: 0, w: 1.6, h: A4.h, color: P.gold }] }),
      content, defaultStyle: { font: 'Fira', fontSize: 9.2 * fs, color: INK, lineHeight: 1.16 }, info: info(cv, heads, 'CV') };
  }

  // ── 5. ATS Hybrid ────────────────────────────────────────────────────────────
  function atsHybrid(E, cv, ctx) {
    const P = ctx.palette; const { fs, g } = ctxScale(ctx); const M = { l: 42, r: 42, t: 36, b: 32 };
    const heads = lines(E, cv, 'headline'); const extras = lines(E, cv, 'extras'); const photo = photoImage(ctx, 58);
    const headStack = [
      { text: cv.name, bold: true, fontSize: 22 * fs, color: INK },
      ...heads.map((l) => ({ text: l.text, font: 'FiraMedium', fontSize: 12 * fs, color: P.accent, margin: [0, 3, 0, 0] })),
      { text: cv.contact.join('   ·   '), fontSize: 8.5 * fs, color: MUTED, margin: [0, 6, 0, 0] },
      ...extras.map((l) => ({ text: l.text, font: 'FiraMedium', fontSize: 8.5 * fs, color: P.gold, margin: [0, 2, 0, 0] })),
    ];
    const W = A4.w - M.l - M.r;
    const content = [{ columns: photo ? [{ stack: headStack, width: '*' }, { stack: [photo], width: photo.width }] : [{ stack: headStack, width: '*' }], columnGap: 14 },
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: W, y2: 0, lineWidth: 1.3, lineColor: P.accent }], margin: [0, 9, 0, 0] }];
    const sec = (key) => ({ stack: [{ text: cv.section_titles[key].toUpperCase(), bold: true, fontSize: 9.4 * fs, color: P.accent, margin: [0, 11 * g, 0, 3] },
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: W, y2: 0, lineWidth: 0.6, lineColor: RULE }], margin: [0, 0, 0, 5 * g] }] });
    const summary = lines(E, cv, 'summary');
    if (summary.length) content.push(sec('summary'), { text: summary.map((l) => l.text).join(' '), lineHeight: 1.25 });
    content.push(sec('experience'));
    for (const b of cv.experiences) {
      content.push({ stack: [
        { columns: [{ text: b.title, bold: true, fontSize: 10.1 * fs, width: '*' }, { text: b.period, fontSize: 8.5 * fs, color: MUTED, width: 'auto', alignment: 'right', margin: [0, 1, 0, 0] }], columnGap: 10 },
        { text: [{ text: b.company, font: 'FiraMedium', color: INK }, b.city ? ` · ${b.city}` : ''], fontSize: 8.6 * fs, color: MUTED, margin: [0, 1, 0, 3] },
        ...bulletList(expBullets(E, cv, b), { shape: 'square', color: P.accent, fs: 9.4 * fs, gap: 1.8 * g, size: 3.2 }),
      ], margin: [0, 0, 0, 7 * g], unbreakable: true });
    }
    const groups = skillGroups(E, cv);
    if (groups.length) { content.push(sec('skills')); groups.forEach(([grp, items]) => content.push({ columns: [{ text: grp, bold: true, width: 70 }, { text: items.join(', '), width: '*' }], columnGap: 8, margin: [0, 0, 0, 2.5] })); }
    for (const k of ['education', 'certifications', 'languages']) {
      const ls = lines(E, cv, k); if (ls.length) content.push(sec(k), ...ls.map((l) => ({ text: l.text, margin: [0, 0, 0, 2] })));
    }
    if (cv.draft) content.push(stamp(cv.language, A4.w - M.r - 172, 10));
    return { pageSize: 'A4', pageMargins: [M.l, M.t, M.r, M.b], content, defaultStyle: { font: 'Fira', fontSize: 9.5 * fs, color: INK, lineHeight: 1.16 }, info: info(cv, heads, 'CV') };
  }

  const CV = { premium_corporate: premiumCorporate, modern_commercial: modernCommercial, minimal_executive: minimalExecutive, digital_creative: digitalCreative, ats_hybrid: atsHybrid };

  // ── Lettres assorties (même palette, mêmes polices, même identité) ───────────
  function letterBody(E, letter, o) {
    const out = [];
    out.push({ columns: [{ text: letter.recipient, width: '*', fontSize: 9.8, color: INK2 }, { text: letter.place_date, width: 'auto', fontSize: 9.4, color: MUTED }], margin: [0, 0, 0, 20] });
    out.push({ text: letter.subject, font: o.subjectFont || 'Fira', bold: true, fontSize: o.subjectSize || 11, color: o.subjectColor || INK, margin: [0, 0, 0, 16] });
    if (letter.salutation) out.push({ text: letter.salutation, margin: [0, 0, 0, 10] });
    E.letterParagraphs(letter).forEach((p) => out.push({ text: p, margin: [0, 0, 0, 10], lineHeight: o.lh || 1.36 }));
    out.push({ text: letter.signature, font: o.signFont || 'Fira', bold: true, fontSize: o.signSize || 11, color: o.signColor || INK, margin: [0, 16, 0, 0] });
    return out;
  }

  function letter(E, letterDoc, ctx) {
    const fam = familyOf(ctx.designId); const P = ctx.palette; const name = ctx.name; const contact = ctx.contact || []; const headline = ctx.headline || '';
    const draft = letterDoc.draft ? [stamp(letterDoc.language, A4.w - 50 - 172, 10)] : [];
    const meta = { title: `Lettre — ${name}`, author: name, subject: letterDoc.subject, creator: 'PAI — Personal Application Intelligence' };
    const base = { pageSize: 'A4', info: meta, defaultStyle: { font: 'Fira', fontSize: 10.2, color: INK, lineHeight: 1.2 } };
    if (fam === 'premium_corporate') {
      const M = { l: 58, r: 58, t: 34, b: 44 };
      const band = { table: { widths: ['*'], body: [[{ stack: [{ text: name, font: 'Serif', bold: true, fontSize: 21, color: P.onDeep }, headline ? { text: headline, font: 'FiraMedium', fontSize: 10.2, color: P.goldLight, margin: [0, 4, 0, 0] } : { text: '' },
        { text: contact.join('    ·    '), fontSize: 8.2, color: P.onDeepMuted, margin: [0, 8, 0, 0] }], margin: [M.l - 4, 24, M.r - 4, 18], fillColor: P.deep }]] }, layout: 'noBorders', margin: [-M.l, -M.t, -M.r, 0] };
      const rule = { canvas: [{ type: 'line', x1: -M.l, y1: 0, x2: A4.w - M.l, y2: 0, lineWidth: 2.4, lineColor: P.gold }], margin: [0, 0, 0, 26] };
      return Object.assign(base, { pageMargins: [M.l, M.t, M.r, M.b], content: [band, rule, ...letterBody(E, letterDoc, { subjectFont: 'Serif', subjectSize: 12.4, subjectColor: P.deep, signFont: 'Serif', signSize: 12, signColor: P.deep }), ...draft],
        footer: () => ({ canvas: [{ type: 'line', x1: M.l, y1: 0, x2: A4.w - M.r, y2: 0, lineWidth: 0.6, lineColor: P.gold }], margin: [0, 8, 0, 0] }) });
    }
    if (fam === 'modern_commercial') {
      const M = { l: 62, r: 52, t: 46, b: 44 };
      const head = [{ text: name, font: 'Manrope', bold: true, fontSize: 21, color: INK }, headline ? { text: headline, font: 'ManropeBold', fontSize: 11, color: P.accent, margin: [0, 3, 0, 0] } : { text: '' },
        { text: contact.join('   |   '), fontSize: 8.3, color: MUTED, margin: [0, 7, 0, 0] }, { canvas: [{ type: 'rect', x: 0, y: 0, w: 36, h: 3, color: P.gold }], margin: [0, 14, 0, 24] }];
      return Object.assign(base, { pageMargins: [M.l, M.t, M.r, M.b], content: [...head, ...letterBody(E, letterDoc, { subjectFont: 'ManropeBold', subjectSize: 11.4, subjectColor: P.accent, signFont: 'ManropeBold', signColor: INK }), ...draft],
        background: () => ({ canvas: [{ type: 'rect', x: 0, y: 0, w: 9, h: A4.h, color: P.accent }, { type: 'rect', x: 9, y: 0, w: 2, h: A4.h, color: P.gold }] }) });
    }
    if (fam === 'minimal_executive') {
      const M = { l: 70, r: 70, t: 60, b: 50 };
      const head = [{ text: name, font: 'Serif', fontSize: 24, color: INK }, headline ? { text: headline, font: 'Serif', italics: true, fontSize: 11.6, color: P.gold, margin: [0, 4, 0, 0] } : { text: '' },
        { text: contact.join('     '), fontSize: 8.1, color: MUTED, margin: [0, 9, 0, 0] }, { canvas: [{ type: 'line', x1: 0, y1: 0, x2: A4.w - M.l - M.r, y2: 0, lineWidth: 0.5, lineColor: RULE }], margin: [0, 16, 0, 28] }];
      return Object.assign(base, { pageMargins: [M.l, M.t, M.r, M.b], defaultStyle: { font: 'Fira', fontSize: 10.3, color: INK, lineHeight: 1.22 },
        content: [...head, ...letterBody(E, letterDoc, { subjectFont: 'Serif', subjectSize: 12, subjectColor: INK, signFont: 'Serif', signSize: 12, lh: 1.42 }), ...draft] });
    }
    if (fam === 'digital_creative') {
      const SB = 150;
      const side = [{ text: name, font: 'Manrope', bold: true, fontSize: 15.5, color: P.onDeep, lineHeight: 1.05 }, headline ? { text: headline, font: 'ManropeBold', fontSize: 8.8, color: P.goldLight, margin: [0, 5, 0, 14] } : { text: '', margin: [0, 0, 0, 14] },
        ...contact.map((c) => ({ text: c, fontSize: 7.8, color: P.onDeepMuted, margin: [0, 0, 0, 5] }))];
      return Object.assign(base, { pageMargins: [0, 48, 0, 44], content: [{ columns: [{ width: SB, stack: side, margin: [20, 0, 14, 0] }, { width: '*', stack: letterBody(E, letterDoc, { subjectFont: 'ManropeBold', subjectSize: 11.2, subjectColor: P.deep, signFont: 'ManropeBold' }), margin: [30, 0, 48, 0] }] }, ...draft],
        background: () => ({ canvas: [{ type: 'rect', x: 0, y: 0, w: SB, h: A4.h, color: P.deep }, { type: 'rect', x: SB, y: 0, w: 1.6, h: A4.h, color: P.gold }] }) });
    }
    const M = { l: 56, r: 56, t: 50, b: 44 };
    const head = [{ text: name, bold: true, fontSize: 17, color: INK }, headline ? { text: headline, font: 'FiraMedium', fontSize: 10.4, color: P.accent, margin: [0, 2, 0, 0] } : { text: '' },
      { text: contact.join('   ·   '), fontSize: 8.6, color: MUTED, margin: [0, 5, 0, 0] }, { canvas: [{ type: 'line', x1: 0, y1: 0, x2: 62, y2: 0, lineWidth: 1.6, lineColor: P.accent }], margin: [0, 14, 0, 22] }];
    return Object.assign(base, { pageMargins: [M.l, M.t, M.r, M.b], content: [...head, ...letterBody(E, letterDoc, { subjectColor: INK }), ...draft] });
  }

  function cv(E, doc, ctx) {
    const fam = familyOf(doc.design_profile);
    return CV[fam](E, doc, ctx);
  }

  const api = { A4, PALETTES, FAMILIES, DENSITY_ORDER, registerFonts, familyOf, palette, shade, highlights, languageItems, cv, letter };
  root.PAIDesigns = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
}(typeof window !== 'undefined' ? window : globalThis));
