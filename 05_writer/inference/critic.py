"""Sentence-level checking with a conservative, deterministic offline baseline."""

from __future__ import annotations

from ..prompts import critic_messages
from ..report_schema_validator import parse_claims, parse_critique, validate_report
from ..schemas import CritiqueResult, ReportSchema, SentenceCritique, VerifiedClaim
from .backend import JsonGenerationBackend, parse_json_object


def _normalize(text: str) -> str:
    # Preserve punctuation and letter case: this is exact-copy checking, not NLI.
    return " ".join(text.split())


def exact_copy_reviews(claims: list[VerifiedClaim], report: ReportSchema) -> list[SentenceCritique]:
    by_id = {claim.claim_id: claim for claim in claims}
    reviews: list[SentenceCritique] = []
    for sentence in report.sentences:
        expected = " ".join(by_id[claim_id].text for claim_id in sentence.claim_ids)
        supported = bool(sentence.claim_ids) and _normalize(sentence.text) == _normalize(expected)
        reviews.append(SentenceCritique(
            sentence_id=sentence.sentence_id,
            verdict="supported" if supported else "uncertain",
            reason=(
                "The sentence exactly reproduces its cited verified claims."
                if supported
                else "Exact-copy checking cannot establish support for this wording; semantic review is required."
            ),
        ))
    return reviews


class Critic:
    def __init__(self, backend: JsonGenerationBackend | None = None) -> None:
        self.backend = backend

    def review(self, claims: list[VerifiedClaim], intent: str, report: ReportSchema) -> CritiqueResult:
        claims = parse_claims(claims)
        report = validate_report(report, claims)
        baseline = exact_copy_reviews(claims, report)
        if self.backend is None:
            return parse_critique(CritiqueResult(
                sentence_reviews=baseline,
                needs_more_evidence=True,
                summary="coverage_not_assessed: deterministic exact-copy review cannot establish intent coverage.",
            ), report)
        critique = parse_critique(
            parse_json_object(self.backend.generate(critic_messages(claims, intent, report))), report
        )
        # Exact copying is useful evidence, but never overrides an adverse semantic
        # review (e.g. a claim does not answer the question or qualifiers conflict).
        direct = {review.sentence_id: review for review in baseline}
        combined = []
        for review in critique.sentence_reviews:
            copied = direct[review.sentence_id]
            if copied.verdict != "supported" and review.verdict == "supported":
                # Current SFT labels only establish verbatim support. Until a
                # semantic critic is validated, a non-copy cannot pass alone.
                review = review.model_copy(update={
                    "verdict": "uncertain",
                    "reason": copied.reason + " " + review.reason,
                })
            elif copied.verdict == "supported" and review.verdict == "supported":
                review = review.model_copy(update={"reason": copied.reason + " " + review.reason})
            combined.append(review)
        return parse_critique(critique.model_copy(update={
            "sentence_reviews": combined,
            "needs_more_evidence": critique.needs_more_evidence or not claims or not report.sentences,
        }), report)
