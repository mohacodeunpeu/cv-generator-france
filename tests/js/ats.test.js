/* Moteur ATS du Studio (web/studio/ats.js) : parité exacte avec pai/ats sur les 13 offres du benchmark
 * (exigences classées et prouvées, mots-clés expliqués, Score PAI et ses dimensions, critères, variante, changements)
 * et sur les cas de l'auto-évaluation. Golden : python tests/golden/make_golden.py.
 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..');
const E = require(path.join(ROOT, 'web', 'studio', 'ats.js'));
E.setData(JSON.parse(fs.readFileSync(path.join(__dirname, '.data.json'), 'utf8')));
const A = E.ATS;
const golden = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'golden', 'ats_parity.json'), 'utf8'));

function report(item) {
  const P = E.P(golden.profile);
  const a = E.deterministicAnalysis({ text: item.text, title_hint: item.title_hint, company_hint: item.company_hint });
  const m = E.computeMatch(P, a);
  const s = E.deterministicStrategy(P, a, m);
  const cv = E.buildCvDeterministic(P, a, m, s, false);
  const v = E.Validator(golden.profile, item.text, [a.job_title, a.company]).validateLines(cv.lines);
  return { r: A.matchReport(P, a, m, item.text, { cv, validation: v }), cv, P };
}

test('classement et preuve : cas de l\'auto-évaluation (parité Python)', () => {
  for (const c of golden.classification) assert.equal(A.classifyRequirement(c.text), c.expected, c.text);
  for (const c of golden.matching.items) assert.equal(A.proofStatusForTexts(c.requirement, golden.matching.facts), c.expected, c.requirement);
});

test('Score PAI : parité exacte sur les 13 offres du benchmark', () => {
  for (const item of golden.offers) {
    const { r, cv, P } = report(item);
    const reqs = Object.fromEntries(Object.entries(r.requirements).map(([k, items]) => [k, items.map((q) => ({ text: q.text, class: q.class, kind: q.kind,
      status: q.proof.status, match: q.proof.match, via: q.proof.via, note: q.proof.note, fact_ids: q.proof.fact_ids, related: q.proof.related }))]));
    assert.deepEqual(reqs, item.requirements, `${item.id} : exigences`);
    assert.deepEqual(r.keywords.map((k) => ({ term: k.term, status: k.status, in_cv: k.in_cv, why: k.why })), item.keywords, `${item.id} : mots-clés`);
    assert.deepEqual(r.dimensions.map((d) => ({ id: d.id, value: d.value, available: d.available, summary: d.summary })), item.dimensions, `${item.id} : dimensions`);
    assert.deepEqual(Object.fromEntries(r.dimensions.map((d) => [d.id, d.details.map((c) => ({ label: c.label, status: c.status, detail: c.detail }))])), item.criteria, `${item.id} : critères`);
    assert.deepEqual({ value: r.score.value, complete: r.score.complete, missing: r.score.missing, formula: r.score.formula }, item.score, `${item.id} : score`);
    assert.equal(r.variant.id, item.variant, `${item.id} : variante`);
    assert.deepEqual(r.strengths.map((x) => x.text), item.strengths, `${item.id} : points forts`);
    assert.deepEqual(r.improvements.map((x) => x.text), item.improvements, `${item.id} : à améliorer`);
    assert.deepEqual(A.changes(cv, P).changes.map((c) => ({ line_id: c.line_id, before: c.before, after: c.after, reason: c.reason })), item.changes, `${item.id} : changements`);
  }
});

test('vérité : la sémantique ne prouve jamais, un voisin est seulement signalé', () => {
  const facts = ['Suivi du pipeline commercial dans HubSpot.', 'Prospection B2B par téléphone et LinkedIn.'];
  const ev = facts.map((x, i) => [`t${i}`, E.norm(x)]);
  const sf = A.prove('Salesforce', ev);
  assert.equal(sf.status, 'NON_PROUVÉ');
  assert.deepEqual(sf.related, ['hubspot']);
  assert.equal(A.prove('Utilisation d\'un CRM', ev).status, 'PLAUSIBLE');
  assert.equal(A.prove('Prospecter', ev).status, 'PROUVÉ');
  assert.equal(A.prove('Immobilier', ev).status, 'NON_PROUVÉ');
});

test('score provisoire tant que le PDF n\'est pas relu ; complet avec la relecture', () => {
  const item = golden.offers[0];
  const { r } = report(item);
  assert.equal(r.score.complete, false);
  assert.deepEqual(r.score.missing, ['Format & parsing']);
  assert.match(r.score.disclaimer, /ni le score d'un ATS réel ni une probabilité d'embauche/);
  const P = E.P(golden.profile);
  const a = E.deterministicAnalysis({ text: item.text, title_hint: item.title_hint, company_hint: item.company_hint });
  const m = E.computeMatch(P, a);
  const scan = { score: 92, checks: [{ label: 'Texte extractible', status: 'OK', detail: '' }, { label: 'Colonnes', status: 'WARNING', detail: '' }] };
  const full = A.matchReport(P, a, m, item.text, { cv: report(item).cv, validation: { total: 1, traced: 1, factuality: 100, forbidden_hits: 0, verdicts: [] }, scan });
  assert.equal(full.score.complete, true);
  assert.equal(full.dimensions[0].id, 'parsing');
  assert.equal(full.dimensions[0].value, 92);
});
