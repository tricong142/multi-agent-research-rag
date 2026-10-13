"""One strict schema contract for training, inference and LangGraph state."""
from __future__ import annotations

from typing import Any, Literal, TypedDict
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class VerifiedClaim(StrictModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, allow_inf_nan=False)
    verification_status: Literal["verified"] = "verified"

    @field_validator("claim_id", "text", "evidence", "source_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank claim fields are not allowed")
        return value


class ReportSentence(StrictModel):
    sentence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_ids: list[str] = Field(min_length=1)


class ReportSchema(StrictModel):
    title: str = "Research report"
    sentences: list[ReportSentence]
    limitations: list[str] = Field(default_factory=list)


class SentenceCritique(StrictModel):
    sentence_id: str
    verdict: Literal["supported", "unsupported", "uncertain"]
    reason: str = Field(min_length=1)


class CritiqueResult(StrictModel):
    sentence_reviews: list[SentenceCritique]
    needs_more_evidence: bool = True
    summary: str = ""


class WriterAction(StrictModel):
    action: Literal["delete_sentence", "rewrite_sentence", "reselect_claims"]
    sentence_id: str
    claim_ids: list[str] = Field(default_factory=list)
    replacement_text: str | None = None
    reason: str = ""


class FactCheckerNodeOutput(StrictModel):
    """Input contract expected from an upstream adapter; never a routing signal.

    The existing 04_factchecker returns a single judgement, not this claim pool.
    An integration layer must populate claims after checking each against evidence.
    """
    verified_claims: list[VerifiedClaim]
    low_confidence_warning: bool = False


class WriterNodeOutput(StrictModel):
    final_report: ReportSchema
    low_confidence_warning: bool
    critique: CritiqueResult
    internal_retries: int = Field(ge=0)
    warning_reasons: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    intent: str
    verified_claims: list[dict[str, Any]]
    final_report: dict[str, Any]
    low_confidence_warning: bool
    writer_diagnostics: dict[str, Any]


class TrainingExample(StrictModel):
    example_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    split: Literal["train", "validation", "test"]
    task: Literal["report", "critic", "action"]
    verified_claims: list[VerifiedClaim]
    intent: str = Field(min_length=1)
    report: ReportSchema
    critique: CritiqueResult
    action: WriterAction | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    label_origin: str = "derived"
    human_reviewed: bool = False
