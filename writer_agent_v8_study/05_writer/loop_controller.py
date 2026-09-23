"""A fixed claim pool and at most N local revisions. No graph commands/tools."""
from __future__ import annotations

from .actions.delete_sentence import delete_sentence
from .actions.reselect_claims import reselect_claims
from .actions.rewrite_sentence import rewrite_sentence
from .config import MAX_INTERNAL_RETRY
from .inference.action_selector import ActionSelector
from .inference.critic import Critic
from .inference.report_generator import ReportGenerator
from .report_schema_validator import parse_claims, parse_critique, validate_action, validate_report
from .schemas import CritiqueResult, ReportSchema, SentenceCritique, WriterNodeOutput


class WriterLoopController:
    def __init__(self, generator=None, critic=None, action_selector=None, *, max_internal_retry=MAX_INTERNAL_RETRY):
        if type(max_internal_retry) is not int or max_internal_retry < 0:
            raise ValueError("max_internal_retry must be a non-negative integer")
        self.generator = generator if generator is not None else ReportGenerator()
        self.critic = critic if critic is not None else Critic()
        self.action_selector = action_selector if action_selector is not None else ActionSelector()
        self.max_internal_retry = max_internal_retry

    @staticmethod
    def _unknown(report, reason):
        return CritiqueResult(
            sentence_reviews=[SentenceCritique(sentence_id=s.sentence_id, verdict="uncertain", reason=reason)
                              for s in report.sentences],
            needs_more_evidence=True, summary=reason,
        )

    @staticmethod
    def _score(report, critique):
        """Prefer no known falsehood, then support ratio and supported content.

        This ranks only local critic judgements; it is not a correctness proof.
        Stable ties preserve the earlier candidate.
        """
        supported = sum(r.verdict == "supported" for r in critique.sentence_reviews)
        unsupported = sum(r.verdict == "unsupported" for r in critique.sentence_reviews)
        uncertain = sum(r.verdict == "uncertain" for r in critique.sentence_reviews)
        return (unsupported == 0, supported / max(1, len(report.sentences)), supported, -uncertain,
                not critique.needs_more_evidence)

    def run(self, verified_claims, intent: str, *, upstream_warning: bool = False) -> WriterNodeOutput:
        trace, warning_reasons = [], []
        if upstream_warning:
            warning_reasons.append("upstream_low_confidence")
        try:
            claims = parse_claims(verified_claims)
            if not isinstance(intent, str) or not intent.strip():
                raise ValueError("intent must be non-empty text")
        except (ValueError, TypeError) as exc:
            report = ReportSchema(sentences=[], limitations=["Writer input or model output could not be validated."])
            return WriterNodeOutput(final_report=report, low_confidence_warning=True,
                                    critique=self._unknown(report, "invalid_input"), internal_retries=0,
                                    warning_reasons=warning_reasons + ["invalid_input"],
                                    trace=[{"stage": "input", "error_type": type(exc).__name__}])
        if not claims:
            report = ReportSchema(sentences=[], limitations=["Insufficient verified claims to answer the intent."])
            return WriterNodeOutput(final_report=report, low_confidence_warning=True,
                                    critique=self._unknown(report, "empty_claim_pool"), internal_retries=0,
                                    warning_reasons=warning_reasons + ["empty_claim_pool"])

        # Fresh models passed to each component prevent accidental pool mutation.
        pool = [c.model_dump(mode="json") for c in claims]
        current, best_report, best_critique = None, None, None
        revisions = 0
        last_failure = None
        for attempt in range(self.max_internal_retry + 1):
            revisions = attempt
            if current is None:
                try:
                    current = validate_report(self.generator.generate(parse_claims(pool), intent), claims)
                    trace.append({"attempt": attempt, "stage": "generate", "ok": True})
                except Exception as exc:  # model boundary: fail soft, including malformed JSON
                    trace.append({"attempt": attempt, "stage": "generate", "ok": False,
                                  "error_type": type(exc).__name__})
                    last_failure = "generation_failed"
                    continue
            try:
                critique = parse_critique(self.critic.review(parse_claims(pool), intent, current.model_copy(deep=True)), current)
                trace.append({"attempt": attempt, "stage": "critic", "ok": True})
                last_failure = None
            except Exception as exc:
                trace.append({"attempt": attempt, "stage": "critic", "ok": False,
                              "error_type": type(exc).__name__})
                critique = self._unknown(current, "critic_failed")
                last_failure = "critic_failed"
            # A fresh successful review supersedes a failed/stale review of the
            # same text even when it discovers a worse factuality verdict.
            if best_report == current and last_failure is None:
                best_critique = critique.model_copy(deep=True)
            if best_report is None or self._score(current, critique) > self._score(best_report, best_critique):
                best_report, best_critique = current.model_copy(deep=True), critique.model_copy(deep=True)
            passed = bool(current.sentences) and all(r.verdict == "supported" for r in critique.sentence_reviews)
            if passed and not critique.needs_more_evidence and last_failure is None:
                return WriterNodeOutput(final_report=current, low_confidence_warning=bool(warning_reasons),
                                        critique=critique, internal_retries=attempt,
                                        warning_reasons=warning_reasons, trace=trace)
            if attempt == self.max_internal_retry:
                break
            if last_failure == "critic_failed":
                continue  # next globally budgeted attempt retries critic, not a blind edit
            try:
                try:
                    action = self.action_selector.select(parse_claims(pool), intent, current.model_copy(deep=True), critique.model_copy(deep=True))
                    if action is not None:
                        action = validate_action(action, current, claims)
                        review = next(r for r in critique.sentence_reviews if r.sentence_id == action.sentence_id)
                        if review.verdict == "supported":
                            raise ValueError("action must target an unsupported or uncertain sentence")
                except Exception as exc:  # invalid model action; preserve a warning even if local repair succeeds
                    trace.append({"attempt": attempt + 1, "stage": "action_selection", "ok": False,
                                  "error_type": type(exc).__name__})
                    warning_reasons.append("action_selection_failed")
                    action = ActionSelector().select(parse_claims(pool), intent, current.model_copy(deep=True),
                                                     critique.model_copy(deep=True))
                    # An exact-copy rewrite is the only fallback whose content
                    # is fully determined by the existing cited claims.
                    if action is None or action.action != "rewrite_sentence":
                        warning_reasons.append("no_local_repair_available")
                        break
                if action is None:
                    warning_reasons.append("no_local_repair_available")
                    break
                action = validate_action(action, current, claims)
                revisions = attempt + 1
                handler = {"delete_sentence": delete_sentence, "rewrite_sentence": rewrite_sentence,
                           "reselect_claims": reselect_claims}[action.action]
                revised = validate_report(handler(current.model_copy(deep=True), action, parse_claims(pool)), claims)
                trace.append({"attempt": attempt + 1, "stage": "repair", "action": action.action,
                              "sentence_id": action.sentence_id, "claim_ids": action.claim_ids, "ok": True})
                if revised == current:
                    warning_reasons.append("local_repair_made_no_change")
                    break
                current = revised
            except Exception as exc:
                trace.append({"attempt": attempt + 1, "stage": "repair", "ok": False,
                              "error_type": type(exc).__name__})
                last_failure = "repair_failed"
                # Reassess the same candidate on the next globally bounded attempt.

        if best_report is None:
            # The model never produced a valid draft. Return an inspectable report
            # copied only from the fixed verified-claim pool instead of discarding
            # all available evidence. This remains low confidence because copying
            # claims cannot establish that they answer the intent.
            best_report = ReportGenerator().generate(parse_claims(pool), intent)
            best_critique = Critic().review(parse_claims(pool), intent, best_report)
            warning_reasons.append("deterministic_claim_copy_fallback")
            trace.append({"stage": "deterministic_fallback", "ok": True,
                          "sentence_count": len(best_report.sentences)})
        if last_failure:
            warning_reasons.append(last_failure)
        if not best_report.sentences:
            warning_reasons.append("empty_report")
        if best_critique.needs_more_evidence:
            warning_reasons.append("insufficient_claims_or_unassessed_coverage")
        if any(r.verdict != "supported" for r in best_critique.sentence_reviews):
            warning_reasons.append("unresolved_sentence_reviews")
        if revisions == self.max_internal_retry:
            warning_reasons.append("internal_retry_budget_exhausted")
        limitation = "Some statements could not be verified within the internal retry budget."
        if limitation not in best_report.limitations:
            best_report.limitations.append(limitation)
        return WriterNodeOutput(final_report=best_report, low_confidence_warning=True,
                                critique=best_critique, internal_retries=revisions,
                                warning_reasons=list(dict.fromkeys(warning_reasons)), trace=trace)
