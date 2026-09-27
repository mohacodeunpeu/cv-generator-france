/* Tests du moteur PAI Studio sous Node (node:test, aucune dépendance).
 * Lancement : node --test tests/js/  (après `python web/build_studio.py --data-json tests/js/.data.json`)
 * Vérifie la parité avec le moteur Python : mêmes cas pièges, mêmes analyses d'offres (tests/golden/).
 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..');
const E = require(path.join(ROOT, 'web', 'studio', 'engine.js'));
E.setData(JSON.parse(fs.readFileSync(path.join(__dirname, '.data.json'), 'utf8')));
const profile = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'profile_test.json'), 'utf8'));
const golden = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'golden', 'validator_cases.json'), 'utf8'));

test('validateur : cas pièges et cas valides (parité Python)', () => {
  const v = E.Validator(profile, golden.offer, golden.offer_terms);
  for (const c of golden.cases) {
    const r = v.validateLine({ id: c.id, section: 'experience', kind: c.kind, text: c.text, fact_ids: c.fact_ids, offer_quote: c.offer_quote || '' });
    assert.equal(r.ok, c.ok, `${c.id} → ${r.ok} (${r.reasons.join('; ')})`);
  }
});

test('MBA interdit : marqué forbidden', () => {
  const v = E.Validator(profile, golden.offer, []);
  const r = v.validateLine({ id: 'x', section: 'summary', kind: 'claim', text: 'Diplômé d\'un MBA', fact_ids: ['edu.bachelor'] });
  assert.equal(r.forbidden, true);
});

test('normalisation et nombres', () => {
  assert.equal(E.norm('Île-de-France — Négociation'), 'ile-de-france - negociation');
  assert.deepEqual(E.extractNumbers('+35 % en 6 mois, 1 200 clients, 915/990').sort(), ['1200', '35', '6', '915', '990'].sort());
  assert.equal(E.containsTerm(E.norm('tableaux de bord'), 'tableau software'), false);
});

const parity = path.join(ROOT, 'tests', 'golden', 'analysis_parity.json');
test('analyse d\'offre : parité avec Python sur les offres du benchmark', { skip: !fs.existsSync(parity) }, () => {
  const expected = JSON.parse(fs.readFileSync(parity, 'utf8'));
  for (const item of expected) {
    const a = E.deterministicAnalysis({ text: item.text, title_hint: item.title_hint, company_hint: item.company_hint });
    assert.equal(a.sector_id, item.sector_id, `${item.id} secteur`);
    assert.equal(a.contract, item.contract, `${item.id} contrat`);
    assert.equal(a.country, item.country, `${item.id} pays`);
    assert.equal(a.language_of_offer, item.language_of_offer, `${item.id} langue`);
    assert.deepEqual(a.keywords.filter((k) => k.priority === 'REQUIRED').map((k) => E.norm(k.term)).sort(), item.required.map(E.norm).sort(), `${item.id} REQUIRED`);
  }
});

test('pipeline déterministe : CV et lettre 100 % tracés', () => {
  const P = E.P(profile);
  const offer = { text: 'Business Developer Junior (H/F) — CDI — Paris\nAcme SaaS édite un logiciel pour les PME françaises depuis 2015.\n\nVos missions\n- Prospecter de nouveaux clients PME par téléphone et LinkedIn.\n- Suivre votre pipeline dans HubSpot.\n\nVotre profil\n- Anglais courant requis.\n- Maîtrise d\'un CRM indispensable.', title_hint: 'Business Developer Junior', company_hint: 'Acme SaaS' };
  const a = E.deterministicAnalysis(offer);
  const m = E.computeMatch(P, a);
  const s = E.deterministicStrategy(P, a, m);
  const cv = E.buildCvDeterministic(P, a, m, s, false);
  const letter = E.buildLetterDeterministic(P, a, m, s, offer, false, new Date(2026, 8, 27));
  const v = E.Validator(profile, offer.text, [a.job_title, a.company]);
  const rc = v.validateLines(cv.lines); const rl = v.validateLines(letter.lines);
  assert.equal(rc.factuality, 100, JSON.stringify(rc.verdicts.filter((x) => !x.ok)));
  assert.equal(rl.factuality, 100, JSON.stringify(rl.verdicts.filter((x) => !x.ok)));
  assert.ok(letter.lines.filter((l) => l.kind === 'offer_ref').length >= 2);
  assert.equal(cv.draft, true);
});
