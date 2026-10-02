"""Orchestration : ingest → analyse → match → stratégie → CV → validation → critique → lettre → questions → pack.

Chaque étape IA a une voie déterministe de repli : sans fournisseur (ou plafond de coût atteint),
le pack est quand même produit, 100 % factuel, et le journal indique ce qui a été dégradé.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any, Callable

from . import ENGINE_VERSION
from .analyzer import analysis_json_for_prompt, deterministic_analysis, merge_ai_analysis
from .claims import ClaimValidator, build_evidence, drop_rejected
from .critic import ai_issue_instructions, deterministic_critique, score_events
from .cv_architect import build_cv_deterministic, cv_from_ai, cv_plain_text, replace_lines
from .letter import build_letter_deterministic, letter_checks, letter_from_ai
from .matching import compute_match
from .obs import event
from .pdf_qa import check_pdf
from .profile import experiences_table, facts_table, missing_data, profile_version_tag
from .providers.base import AIProvider, ProviderError
from .questions import answer_deterministic, split_questions
from .rules import load_rules, prompts_version, truth_rules
from .schemas import (Analysis, Answer, ApplicationPack, CvDocument, LetterDocument, Line, MasterProfile, Match, Offer,
                      Strategy, StrategyChoice, ValidationReport, Versions)
from .strategy import deterministic_strategy, sanitize_strategy
from .textnorm import stable_hash

Progress = Callable[[str, str], None]


class Pipeline:
    def __init__(self, profile: MasterProfile, provider: AIProvider, mode: str = "STANDARD",
                 progress: Progress | None = None, feedback_context: str = "", learned_rules: str = "",
                 render_pdf: bool = True):
        self.profile = profile
        self.provider = provider
        self.mode = mode
        self.rules = load_rules()
        self.progress = progress or (lambda stage, detail: None)
        self.log: list[dict[str, Any]] = []
        self.feedback_context = feedback_context or "aucun"
        self.learned_rules = learned_rules or "aucune"
        self.render_pdf = render_pdf
        self.files: dict[str, bytes] = {}
        self._stage, self._stage_t = "", time.monotonic()

    # -- utilitaires -----------------------------------------------------------
    @property
    def ai(self) -> bool:
        return self.provider.available

    def _step(self, stage: str, detail: str = "") -> None:
        """Étape suivante : journal lisible (pack) + événement structuré de l'étape précédente (durée, sans contenu)."""
        now = time.monotonic()
        if self._stage:
            event("stage", stage=self._stage, duration_ms=int((now - self._stage_t) * 1000), success=True)
        self._stage, self._stage_t = stage, now
        self.log.append({"stage": stage, "detail": detail})
        self.progress(stage, detail)

    def _try_ai(self, stage: str, fn: Callable[[], Any]) -> Any | None:
        if not self.ai:
            return None
        try:
            return fn()
        except ProviderError as exc:
            self._step(stage, f"IA indisponible → voie déterministe ({exc})")
            return None

    def _common_vars(self, analysis: Analysis) -> dict[str, str]:
        sector = self.rules.sector(analysis.sector_id)
        country = self.rules.country(analysis.country)
        return {
            "truth_rules": truth_rules(self.profile.forbidden_terms()),
            "facts_table": facts_table(self.profile),
            "experiences_table": experiences_table(self.profile),
            "analysis_json": analysis_json_for_prompt(analysis),
            "sector_json": json.dumps({k: sector.get(k) for k in ("name", "vocabulary", "priorities", "expectations", "cv_style",
                                                                    "letter_style", "common_mistakes", "useful_proofs")}, ensure_ascii=False),
            "country_json": json.dumps(country, ensure_ascii=False),
            "sector_name": sector.get("name", analysis.sector_id),
            "country_name": country.get("name", "France"),
        }

    # -- étapes ---------------------------------------------------------------
    def analyze(self, offer: Offer) -> Analysis:
        self._step("analyse", "extraction déterministe")
        base = deterministic_analysis(offer, self.rules)
        ai = self._try_ai("analyse", lambda: self.provider.analyze_offer(
            offer_text=offer.text[:12000], job_title_hint=offer.title_hint, company_hint=offer.company_hint,
            deterministic_json=base.model_dump_json(exclude={"sector_scores"})))
        return merge_ai_analysis(base, ai, self.rules) if isinstance(ai, dict) else base

    def match(self, analysis: Analysis) -> Match:
        self._step("match", "sous-scores déterministes")
        m = compute_match(self.profile, analysis, self.rules)
        v = self._common_vars(analysis)
        ai = self._try_ai("match", lambda: self.provider.analyze_profile_match(
            analysis_json=v["analysis_json"], facts_table=v["facts_table"], truth_rules=v["truth_rules"],
            deterministic_match_json=m.model_dump_json(include={"scores", "match", "quality", "risk", "coverage"})))
        if isinstance(ai, dict):
            known = {f.id for f in self.profile.usable_facts()}
            for key in ("why_fit", "strengths"):
                items = [i for i in ai.get(key, []) if isinstance(i, dict) and set(i.get("fact_ids", [])) <= known and i.get("fact_ids")]
                if items:
                    setattr(m, key, items)
            for key in ("why_not", "missing", "risks"):
                if isinstance(ai.get(key), list) and ai[key]:
                    setattr(m, key, getattr(m, key) + [i for i in ai[key] if isinstance(i, dict)])
        return m

    def strategy(self, analysis: Analysis, match: Match) -> Strategy:
        self._step("stratégie", "positionnements A/B/C")
        det = deterministic_strategy(self.profile, analysis, match, self.rules)
        v = self._common_vars(analysis)
        variants = "3" if self.mode == "DEEP" else "2"
        ai = self._try_ai("stratégie", lambda: self.provider.generate_strategy(
            analysis_json=v["analysis_json"], match_json=match.model_dump_json(include={"scores", "match", "quality", "risk", "missing", "strengths"}),
            facts_table=v["facts_table"], experiences_table=v["experiences_table"], sector_json=v["sector_json"],
            country_json=v["country_json"], learned_rules=self.learned_rules, truth_rules=v["truth_rules"], variants=variants,
            country_name=v["country_name"], sector_name=v["sector_name"]))
        if isinstance(ai, dict) and isinstance(ai.get("best"), dict):
            try:
                best = StrategyChoice.model_validate({**det.best.model_dump(), **ai["best"]})
                strat = Strategy(options=ai.get("options", []), comparison=str(ai.get("comparison", "")),
                                 chosen=str(ai.get("chosen", "A")), best=best, source="ai")
                return sanitize_strategy(strat, self.profile, analysis, self.rules)
            except Exception as exc:  # noqa: BLE001
                self._step("stratégie", f"stratégie IA invalide → déterministe ({exc})")
        return det

    def _validator(self, offer: Offer, analysis: Analysis) -> ClaimValidator:
        return ClaimValidator(self.profile, offer.text, self.rules, offer_terms=[analysis.job_title, analysis.company])

    def _fix_loop(self, lines: list[Line], validator: ClaimValidator, analysis: Analysis, instructions: dict[str, str] | None = None,
                  general: list[str] | None = None) -> tuple[list[Line], ValidationReport, list[dict[str, Any]]]:
        """Validation → réécriture des lignes rejetées (2 essais max) → suppression des lignes encore fausses."""
        report = validator.validate_lines(lines)
        targets = set(report.rejected_ids) | set((instructions or {}).keys())
        attempts = 0
        dropped: list[dict[str, Any]] = []
        while targets and self.ai and attempts < 2:
            attempts += 1
            payload = []
            for ln in lines:
                if ln.id in targets:
                    reasons = next((v.reasons for v in report.verdicts if v.line_id == ln.id), [])
                    payload.append({"id": ln.id, "text": ln.text, "reasons": reasons + ([instructions[ln.id]] if instructions and ln.id in instructions else []),
                                    "fact_ids": ln.fact_ids, "kind": ln.kind})
            v = self._common_vars(analysis)
            fixed = self._try_ai("correction", lambda: self.provider.fix_lines(
                rejected_lines_json=json.dumps(payload, ensure_ascii=False), facts_table=v["facts_table"],
                critic_instructions="; ".join(general or []) or "aucune", truth_rules=v["truth_rules"],
                language="anglais" if analysis.language_of_offer == "en" else "français"))
            if not isinstance(fixed, dict):
                break
            by_id = {str(item.get("id")): item for item in fixed.get("lines", []) if isinstance(item, dict)}
            new_lines = []
            for ln in lines:
                item = by_id.get(ln.id)
                if item is None:
                    new_lines.append(ln)
                    continue
                text = str(item.get("text", "")).strip()
                if text:
                    new_lines.append(ln.model_copy(update={"text": text, "fact_ids": [str(x) for x in item.get("fact_ids", ln.fact_ids)]}))
                else:
                    reasons = next((v.reasons for v in report.verdicts if v.line_id == ln.id), [])
                    dropped.append({"id": ln.id, "text": ln.text,
                                    "reasons": reasons + ["supprimée à la correction : aucune version vraie possible"]})
            lines = new_lines
            instructions = None
            report = validator.validate_lines(lines)
            targets = set(report.rejected_ids)
        kept, removed = drop_rejected(lines, report)
        removed = dropped + removed
        final_report = validator.validate_lines(kept)
        final_report.forbidden_hits += report.forbidden_hits
        return kept, final_report, removed

    def factuality_judge(self, lines: list[Line]) -> list[dict[str, Any]]:
        """Juge IA d'exagération sur les affirmations (règle A2-b)."""
        claims = [ln for ln in lines if ln.kind in ("claim", "fact") and ln.fact_ids]
        if not claims or not self.ai:
            return []
        payload = [{"id": ln.id, "text": ln.text, "facts": [f.text for f in build_evidence(self.profile, ln.fact_ids).facts]}
                   for ln in claims]
        out = self._try_ai("factualité", lambda: self.provider.judge_factuality(lines_with_facts_json=json.dumps(payload, ensure_ascii=False)))
        if not isinstance(out, dict):
            return []
        return [v for v in out.get("verdicts", []) if isinstance(v, dict) and v.get("verdict") not in (None, "OK")]

    def build_cv(self, offer: Offer, analysis: Analysis, match: Match, strategy: Strategy) -> tuple[CvDocument, ValidationReport, dict[str, Any]]:
        self._step("cv", "plan de contenu")
        design = self.rules.design(strategy.best.design_profile)
        cv = build_cv_deterministic(self.profile, analysis, match, strategy, self.rules,
                                    max_featured=int(design.get("max_bullets_featured", 4)), max_other=int(design.get("max_bullets_other", 2)))
        v = self._common_vars(analysis)
        ai = self._try_ai("cv", lambda: self.provider.generate_cv_content(
            analysis_json=v["analysis_json"], strategy_json=strategy.best.model_dump_json(), facts_table=v["facts_table"],
            experiences_table=v["experiences_table"], sector_json=v["sector_json"], country_json=v["country_json"],
            synonyms=json.dumps({"equivalents": self.rules.synonyms.groups[:25], "implies": self.rules.synonyms.implies}, ensure_ascii=False),
            banned_phrases=", ".join(self.rules.banned_hard[:30]), feedback_context=self.feedback_context,
            language="anglais" if analysis.language_of_offer == "en" else "français", truth_rules=v["truth_rules"],
            max_bullets_featured=str(design.get("max_bullets_featured", 4)), max_bullets_other=str(design.get("max_bullets_other", 2)),
            country_name=v["country_name"], sector_name=v["sector_name"]))
        if isinstance(ai, dict):
            cv = cv_from_ai(ai, self.profile, analysis, match, strategy, self.rules)
        validator = self._validator(offer, analysis)
        self._step("validation", "claim → evidence")
        cv.lines, report, removed = self._fix_loop(cv.lines, validator, analysis)
        cv.removed_lines += removed
        for block in cv.experiences:
            block.bullet_ids = [b for b in block.bullet_ids if cv.line(b) is not None]

        # Juge d'exagération puis critique (boucle bornée)
        flagged = self.factuality_judge(cv.lines)
        if flagged:
            instr = {str(f.get("id")): f"{f.get('verdict')}: {f.get('reason', '')}" for f in flagged}
            cv.lines, report, removed = self._fix_loop(cv.lines, validator, analysis, instructions=instr)
            cv.removed_lines += removed
        cycles = int(self.rules.models.get("modes", {}).get(self.mode, {}).get("critique_cycles", 1))
        critique: dict[str, Any] = {}
        for cycle in range(max(cycles, 1)):
            self._step("critique", f"cycle {cycle + 1}")
            det = deterministic_critique(cv, analysis, match, strategy, report, self.rules)
            ai_crit = self._try_ai("critique", lambda: self.provider.critique_document(
                analysis_json=v["analysis_json"], sector_json=v["sector_json"], country_json=v["country_json"],
                design_json=json.dumps(self.rules.design(cv.design_profile), ensure_ascii=False),
                validation_json=report.model_dump_json(include={"factuality", "total", "traced", "warnings"}),
                cv_text=cv_plain_text(cv), sector_name=v["sector_name"]))
            critique = {"deterministic": det, "ai": ai_crit if isinstance(ai_crit, dict) else None}
            per_line, general = ai_issue_instructions(ai_crit) if isinstance(ai_crit, dict) else ({}, [])
            general += [i["fix"] for i in det["issues"] if i["severity"] == "high" and not i["line_ids"]]
            if not self.ai or (not per_line and not general):
                break
            targets = {lid: txt for lid, txt in per_line.items() if cv.line(lid) is not None}
            if not targets and general:
                targets = {ln.id: "; ".join(general) for ln in cv.section_lines("summary")[:1] + cv.section_lines("experience")[:2]}
            if not targets:
                break
            cv.lines, report, removed = self._fix_loop(cv.lines, validator, analysis, instructions=targets, general=general)
            cv.removed_lines += removed
            for block in cv.experiences:
                block.bullet_ids = [b for b in block.bullet_ids if cv.line(b) is not None]
        qa: dict[str, Any] = {}
        if self.render_pdf:
            from .render import render_cv_fitted

            self._step("rendu", "HTML/CSS → Chromium → PDF")
            max_pages = int(self.rules.country(analysis.country).get("max_pages", 1))
            cv, pdf, info = render_cv_fitted(cv, max_pages=max_pages)
            cv, pdf, scan, passes = self._reread_loop(cv, pdf, max_pages, info)
            titles = cv.section_titles
            qa = check_pdf(pdf, expect_pages=max_pages,
                           required_terms=[c.term for c in match.coverage if c.covered and c.priority == "REQUIRED"],
                           reading_order=[cv.name, titles.get("experience", ""), titles.get("education", "")])
            qa["fit"] = info
            qa["ats_scan"] = {k: scan[k] for k in ("checks", "score", "status", "pages", "text_chars", "layout")} | {
                "roundtrip": {k: v for k, v in scan.get("roundtrip", {}).items() if k != "lost"}}
            qa["ats_passes"] = passes
            self.files["cv.pdf"] = pdf
            report = validator.validate_lines(cv.lines)
        return cv, report, {"critique": critique, "pdf_qa": qa, "flagged_by_judge": flagged}

    @staticmethod
    def ats_labels(cv: CvDocument) -> list[str]:
        """Textes du gabarit légitimes dans le PDF (nom, coordonnées, titres, en-têtes d'expérience, badge brouillon)."""
        from .render import DRAFT_LABEL

        labels = [cv.name, *cv.contact, *cv.section_titles.values(), *{ln.group for ln in cv.lines if ln.group},
                  *DRAFT_LABEL.values()]
        for b in cv.experiences:
            labels += [b.title, b.company, b.city, b.period]
        return [x for x in labels if x]

    def _reread_loop(self, cv: CvDocument, pdf: bytes, max_pages: int, info: dict[str, Any]
                     ) -> tuple[CvDocument, bytes, dict[str, Any], list[dict[str, Any]]]:
        """CV → PDF → relecture ATS → correction → nouvelle relecture. Trois relectures au plus (jamais de boucle infinie).
        Corrections possibles sans rien inventer : retirer une ligne porteuse d'un reste de gabarit, réduire le contenu
        secondaire en cas de débordement. Une erreur non corrigeable reste signalée (Format & parsing)."""
        from .ats.scanner import scan_pdf
        from .cv_architect import trim_for_space
        from .render import render_cv_pdf
        from .textnorm import norm

        passes: list[dict[str, Any]] = []
        scan: dict[str, Any] = {}
        for attempt in range(3):
            scan = scan_pdf(pdf, max_pages=max_pages, source_lines=[ln.text for ln in cv.lines], allowed=self.ats_labels(cv))
            errors = sorted(c["id"] for c in scan["checks"] if c["status"] == "ERROR")
            passes.append({"pass": attempt + 1, "status": scan["status"], "score": scan["score"], "errors": errors})
            fixable = set(errors) & {"added", "overflow", "pages"}
            if not fixable or attempt == 2:
                break
            self._step("relecture", f"passe {attempt + 1} : {', '.join(sorted(fixable))} → correction puis nouvelle relecture")
            if "added" in fixable:
                bad = set(scan.get("roundtrip", {}).get("placeholders", []))
                cv.lines = [ln for ln in cv.lines if not any(b in norm(ln.text) for b in bad)]
            if fixable & {"overflow", "pages"}:
                cv = trim_for_space(cv, min(3, int(info.get("trim_steps", 0)) + attempt + 1))
            pdf = render_cv_pdf(cv)
        self._step("relecture", f"PDF relu : {scan.get('status')} · Format & parsing {scan.get('score')} %")
        return cv, pdf, scan, passes

    def build_letter(self, offer: Offer, analysis: Analysis, match: Match, strategy: Strategy) -> tuple[LetterDocument, ValidationReport, list[dict[str, str]]]:
        self._step("lettre", "rédaction")
        base = build_letter_deterministic(self.profile, analysis, match, strategy, offer, self.rules)
        v = self._common_vars(analysis)
        sector = self.rules.sector(analysis.sector_id)
        low, high = sector.get("letter_style", {}).get("length_words", [220, 320])
        ai = self._try_ai("lettre", lambda: self.provider.generate_letter(
            analysis_json=v["analysis_json"], strategy_json=strategy.best.model_dump_json(),
            company_facts=json.dumps({"source": "offre", "texte": offer.text[:1500]}, ensure_ascii=False),
            facts_table=v["facts_table"], sector_json=v["sector_json"], banned_phrases=", ".join(self.rules.banned_hard[:30]),
            feedback_context=self.feedback_context, truth_rules=v["truth_rules"], candidate_name=self.profile.value("id.name"),
            language="anglais" if analysis.language_of_offer == "en" else "français", length_words=f"{low} à {high}",
            company=analysis.company, job_title=strategy.best.title))
        letter = letter_from_ai(ai, self.profile, analysis, base) if isinstance(ai, dict) else base
        validator = self._validator(offer, analysis)
        letter.lines, report, removed = self._fix_loop(letter.lines, validator, analysis)
        letter.removed_lines += removed
        issues = letter_checks(letter, analysis, self.rules)
        if self.render_pdf:
            from .cv_architect import contact_lines
            from .render import render_letter_pdf

            self.files["lettre.pdf"] = render_letter_pdf(letter, self.profile.value("id.name"), contact_lines(self.profile),
                                                        strategy.best.design_profile)
        return letter, report, issues

    def answers(self, questions_raw: str, analysis: Analysis) -> list[Answer]:
        questions = split_questions(questions_raw)
        if not questions:
            return []
        self._step("questions", f"{len(questions)} question(s)")
        v = self._common_vars(analysis)
        ai = self._try_ai("questions", lambda: self.provider.answer_question(
            questions="\n".join(f"- {q}" for q in questions), analysis_json=v["analysis_json"], facts_table=v["facts_table"],
            truth_rules=v["truth_rules"], candidate_name=self.profile.value("id.name"),
            language="anglais" if analysis.language_of_offer == "en" else "français"))
        if isinstance(ai, dict) and isinstance(ai.get("answers"), list):
            answers = []
            known = {f.id for f in self.profile.usable_facts()}
            for item in ai["answers"]:
                try:
                    ans = Answer.model_validate(item)
                except Exception:  # noqa: BLE001
                    continue
                if ans.confidence != "BLOCKED" and (not ans.fact_ids or not set(ans.fact_ids) <= known):
                    ans.confidence, ans.answer = "BLOCKED", ""
                    ans.ask_user = ans.ask_user or "Aucun fait du profil ne permet de répondre : à compléter par vous."
                answers.append(ans)
            return answers
        return [answer_deterministic(q, self.profile) for q in questions]

    def ats_report(self, offer: Offer, analysis: Analysis, match: Match, *, cv: CvDocument | None = None,
                   validation: ValidationReport | None = None, scan: dict[str, Any] | None = None) -> dict[str, Any]:
        """Score PAI + exigences prouvées + changements expliqués. Déterministe ; embeddings locaux seulement si activés."""
        from .ats import match_report
        from .ats.changes import explain
        from .ats.semantic import local_embedder

        self._step("ats", "exigences, preuves, Score PAI")
        report = match_report(self.profile, analysis, match, offer.text, cv=cv, validation=validation, scan=scan,
                              rules=self.rules, embedder=local_embedder())
        if cv is not None:
            report["changes"] = explain(cv, self.profile)
        return report

    # -- exécution complète -------------------------------------------------------
    def run(self, offer: Offer, questions: str = "") -> ApplicationPack:
        self._step("ingest", f"offre {offer.id} ({len(offer.text)} caractères)")
        analysis = self.analyze(offer)
        match = self.match(analysis)
        strategy = self.strategy(analysis, match)
        versions = Versions(application_id=f"app_{offer.text_hash[:12]}", offer_v=offer.text_hash[:12],
                            profile_v=profile_version_tag(self.profile),
                            analysis_v=stable_hash(analysis.model_dump(exclude={"sector_scores"}), 10), engine_v=ENGINE_VERSION,
                            prompt_v=prompts_version(), rules_v=self.rules.version)
        # Identifiant unique : une génération est immuable, deux runs de la même offre donnent deux packs.
        pack = ApplicationPack(id=f"pack_{stable_hash([offer.id, versions.profile_v, self.mode], 6)}{secrets.token_hex(3)}",
                               mode=self.mode, provider=self.provider.name, versions=versions, offer=offer,  # type: ignore[arg-type]
                               analysis=analysis, match=match, strategy=strategy)
        if self.mode == "QUICK":
            pack.ats = self.ats_report(offer, analysis, match)
            pack.scores = {"pai_score": pack.ats["score"]["value"], "pai_score_complete": False}
            pack.risks = [r["text"] for r in match.risks]
            pack.next_action = "Lancer le mode STANDARD pour générer le CV et la lettre."
            pack.log, pack.cost_eur = self.log, self.provider.spent_eur
            return pack
        cv, cv_report, extra = self.build_cv(offer, analysis, match, strategy)
        letter, letter_report, letter_issues = self.build_letter(offer, analysis, match, strategy)
        answers = self.answers(questions, analysis)
        pack.cv, pack.letter, pack.answers = cv, letter, answers
        pack.validation = {"cv": cv_report, "letter": letter_report}
        pack.critique = {**extra["critique"], "letter_checks": letter_issues, "flagged_by_judge": extra["flagged_by_judge"]}
        pack.pdf_qa = extra["pdf_qa"]
        pack.versions.cv_v = stable_hash([ln.model_dump() for ln in cv.lines], 10)
        pack.versions.template = cv.design_profile
        pack.versions.letter_v = stable_hash([ln.model_dump() for ln in letter.lines], 10)
        pack.versions.answers_v = stable_hash([a.model_dump() for a in answers], 10) if answers else ""
        pack.scores = {
            "factuality_cv": cv_report.factuality, "factuality_letter": letter_report.factuality,
            "match": match.match, "quality": match.quality, "risk": match.risk,
            "points": score_events(cv, letter, analysis, match, strategy, pack.validation, extra["critique"].get("deterministic", {}), self.rules),
        }
        pack.ats = self.ats_report(offer, analysis, match, cv=cv, validation=cv_report, scan=pack.pdf_qa.get("ats_scan"))
        pack.ats["passes"] = pack.pdf_qa.get("ats_passes", [])
        pack.scores["pai_score"] = pack.ats["score"]["value"]
        pack.scores["pai_score_complete"] = pack.ats["score"]["complete"]
        if isinstance(extra["critique"].get("ai"), dict):
            pack.scores["judges"] = {k: v.get("score") for k, v in (extra["critique"]["ai"].get("scores") or {}).items() if isinstance(v, dict)}
        perfect = cv_report.perfect and letter_report.perfect
        pdf_ok = pack.pdf_qa.get("ok", True) if pack.pdf_qa else True
        pack.status = "FINAL" if (self.profile.validated and perfect and pdf_ok) else "DRAFT"
        pack.risks = [r["text"] for r in match.risks] + strategy.best.risks
        pack.next_action = ("Relire puis postuler vous-même (PAI n'envoie rien)." if pack.status == "FINAL"
                            else "Valider le Master Profile (onglet Profil) pour passer les documents en FINAL, puis relire et postuler vous-même.")
        pack.missing_profile_data = missing_data(self.profile)
        pack.log, pack.cost_eur = self.log, self.provider.spent_eur
        self._step("pack", f"statut {pack.status}")
        event("stage", stage="pack", duration_ms=int((time.monotonic() - self._stage_t) * 1000), success=True,
              generation_id=pack.id, score=pack.scores.get("pai_score"))
        return pack
