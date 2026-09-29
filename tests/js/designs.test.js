/* Design automatique, fiche entreprise et 5 gabarits de documents (web/studio/designs.js), sous Node.
 * Lancement : node --test tests/js/*.test.js  (après `python web/build_studio.py --data-json tests/js/.data.json`)
 * Profil FICTIF « Camille Test ». Les gabarits ne doivent QUE mettre en page : même texte dans les 5 designs.
 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..');
const E = require(path.join(ROOT, 'web', 'studio', 'engine.js'));
const DS = require(path.join(ROOT, 'web', 'studio', 'designs.js'));
const DATA = JSON.parse(fs.readFileSync(path.join(__dirname, '.data.json'), 'utf8'));
E.setData(DATA);
const profile = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'profile_test.json'), 'utf8'));
const P = E.P(profile);
const OFFER = 'Business Developer Junior (H/F) — CDI — Paris\nNordlys (entreprise FICTIVE) édite un logiciel SaaS pour les PME françaises. 120 salariés.\n\n'
  + 'Vos missions\n- Prospecter de nouveaux clients PME par téléphone et LinkedIn.\n- Suivre votre pipeline dans HubSpot.\n\nVotre profil\n- Anglais courant requis.';
const setup = (text = OFFER) => {
  const a = E.deterministicAnalysis({ text, title_hint: '', company_hint: 'Nordlys' });
  const m = E.computeMatch(P, a); const s = E.deterministicStrategy(P, a, m);
  return { a, m, s };
};

test('design automatique : famille connue, choix expliqué, pas de photo sans photo', () => {
  const { a, s } = setup();
  const d = E.autoDesign(a, s, { offerText: OFFER, prefs: {}, hasPhoto: false });
  assert.ok(DS.FAMILIES.includes(d.design), d.design);
  assert.ok(DATA.designs[d.design].palettes.includes(d.palette), d.palette);
  assert.equal(d.photo_mode, 'OFF');
  assert.ok(d.why.length >= 3 && d.why.every((w) => w.k && w.t), JSON.stringify(d.why));
});

test('design automatique : un ATS cité dans l\'annonce écarte les mises en page peu lisibles par les ATS', () => {
  const text = `${OFFER}\nCandidature via Workday uniquement.`;
  const { a, s } = setup(text);
  const d = E.autoDesign(a, s, { offerText: text, prefs: { design: 'digital_creative' }, hasPhoto: true });
  assert.notEqual(DATA.designs[d.design].ats_level, 'low', d.design);
  assert.ok(d.why.some((w) => /workday/i.test(w.t)), JSON.stringify(d.why));
});

test('design automatique : la préférence de l\'utilisateur est respectée quand rien ne s\'y oppose', () => {
  const { a, s } = setup();
  const d = E.autoDesign(a, s, { offerText: OFFER, prefs: { design: 'minimal_executive', palette: 'graphite' }, hasPhoto: true });
  assert.equal(d.design, 'minimal_executive');
  assert.equal(d.palette, 'graphite');
});

test('fiche entreprise : uniquement ce que dit l\'annonce, logo jamais utilisé sans vérification', () => {
  const { a } = setup();
  const c = E.companyCard(a, { text: OFFER });
  assert.equal(c.source, 'annonce');
  assert.equal(c.logo.used, false);
  assert.ok(c.figures.some((f) => /120 salariés/.test(f)), JSON.stringify(c.figures));
  for (const line of c.about) assert.ok(OFFER.includes(line), line);
});

test('5 designs : même texte, mises en page réellement différentes', () => {
  const { a, m, s } = setup();
  const cv = E.buildCvDeterministic(P, a, m, s, false);
  const texts = cv.lines.map((l) => l.text);
  const signatures = new Set();
  for (const fam of DS.FAMILIES) {
    const doc = Object.assign({}, cv, { design_profile: fam });
    const def = DS.cv(E, doc, { palette: DS.palette(DATA.designs[fam].palette_default), density: 'balanced', photo: null, photoMode: 'OFF' });
    assert.equal(def.pageSize, 'A4', fam);
    const json = JSON.stringify(def);
    for (const t of texts) {
      if (cv.lines.find((l) => l.text === t).section === 'languages') continue; // Digital Creative présente la langue et le niveau séparément
      assert.ok(json.includes(JSON.stringify(t).slice(1, -1)), `${fam} : « ${t} » absent`);
    }
    assert.ok(!/"image"/.test(json), `${fam} : aucune image sans photo`);
    const fonts = [...new Set((json.match(/"font":"(\w+)"/g) || []))].sort().join(',');
    signatures.add(`${fonts}|${def.pageMargins.join(',')}|${typeof def.background}`);
  }
  assert.equal(signatures.size, DS.FAMILIES.length, 'chaque famille doit avoir sa propre mise en page');
});

test('photo : placée seulement si demandée, jamais sur la lettre', () => {
  const { a, m, s } = setup();
  const cv = Object.assign(E.buildCvDeterministic(P, a, m, s, true), { design_profile: 'premium_corporate' });
  const photo = { circle: 'data:image/png;base64,AAAA', square: 'data:image/jpeg;base64,AAAA', scale: 1 };
  const withPhoto = JSON.stringify(DS.cv(E, cv, { palette: DS.palette('navy'), density: 'balanced', photo, photoMode: 'HEADER' }));
  const without = JSON.stringify(DS.cv(E, cv, { palette: DS.palette('navy'), density: 'balanced', photo, photoMode: 'OFF' }));
  assert.ok(withPhoto.includes('"image"') && !without.includes('"image"'));
  const letter = E.buildLetterDeterministic(P, a, m, s, { text: OFFER }, true, new Date(2026, 8, 29));
  const L = JSON.stringify(DS.letter(E, letter, { palette: DS.palette('navy'), density: 'balanced', photo, photoMode: 'HEADER', designId: 'premium_corporate', name: 'Camille Test', contact: [], headline: 'Business Developer' }));
  assert.ok(!L.includes('"image"'), 'la lettre ne porte jamais de photo');
});

test('étalement d\'une page trop vide : mêmes textes, texte +10 % au plus, plafonné', () => {
  const { a, m, s } = setup(); const cv = E.buildCvDeterministic(P, a, m, s, false);
  const base = { palette: DS.palette('petrol'), density: 'airy', photo: null, photoMode: 'OFF' };
  const layoutFree = (def) => JSON.stringify(def.content, (k, v) => (['fontSize', 'margin', 'lineHeight'].includes(k) ? undefined : v));
  for (const fam of DS.FAMILIES) {
    cv.design_profile = fam;
    const d1 = DS.cv(E, cv, Object.assign({}, base, { spread: 1 }));
    const d2 = DS.cv(E, cv, Object.assign({}, base, { spread: 2 }));
    const d9 = DS.cv(E, cv, Object.assign({}, base, { spread: 9 }));
    assert.equal(layoutFree(d2), layoutFree(d1), `${fam} : l'étalement ne change que la mise en page`);
    assert.equal(JSON.stringify(d9), JSON.stringify(d2), `${fam} : étalement plafonné à 2`);
    assert.ok(d2.defaultStyle.fontSize > d1.defaultStyle.fontSize && d2.defaultStyle.fontSize <= d1.defaultStyle.fontSize * 1.1 + 1e-9, fam);
  }
});
