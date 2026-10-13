"""Generate a report from the supplied verified-claim pool only."""

from __future__ import annotations

from ..prompts import report_messages
from ..report_schema_validator import parse_claims, validate_report
from ..schemas import ReportSchema, ReportSentence, VerifiedClaim
from .backend import JsonGenerationBackend, parse_json_object


class ReportGenerator:
    def __init__(self, backend: JsonGenerationBackend | None = None) -> None:
        self.backend = backend

    def generate(self, claims: list[VerifiedClaim], intent: str) -> ReportSchema:
        claims = parse_claims(claims)
        if self.backend is not None:
            payload = parse_json_object(self.backend.generate(report_messages(claims, intent)))
            report = validate_report(payload, claims)
            # Equivalent evidence excerpts add latency without adding coverage.
            # Keep the first occurrence and its citation; never synthesize text.
            seen, sentences = set(), []
            for sentence in report.sentences:
                key = " ".join(sentence.text.split()).casefold()
                if key not in seen:
                    seen.add(key)
                    sentences.append(sentence)
            return validate_report(report.model_copy(update={"sentences": sentences}), claims)
        # An inspectable offline baseline; this does not claim semantic synthesis.
        seen, sentences = set(), []
        for claim in claims:
            key = " ".join(claim.text.split()).casefold()
            if key in seen:
                continue
            seen.add(key)
            sentences.append(ReportSentence(
                sentence_id=f"s{len(sentences) + 1}", text=claim.text, claim_ids=[claim.claim_id],
            ))
        report = ReportSchema(
            title="Research report",
            sentences=sentences,
            limitations=(
                ["Insufficient verified claims to answer the intent."]
                if not claims
                else ["The available claims may not fully answer the intent."]
            ),
        )
        return validate_report(report, claims)
