from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class CandidateProduct(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl = Field(alias="sourceUrl")
    price: float = Field(gt=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    shipping_eta: str = Field(alias="shippingETA", min_length=1, max_length=100)
    return_policy: str = Field(alias="returnPolicy", min_length=1, max_length=200)
    checkout_ready: bool = Field(alias="checkoutReady")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    constraint_tier: str = Field(
        default="strict",
        alias="constraintTier",
        description="Constraint match tier: strict, soft_5, soft_10, soft_15.",
    )
    constraint_relaxed: bool = Field(
        default=False,
        alias="constraintRelaxed",
        description="True when candidate required constraint relaxation.",
    )

    @field_validator("evidence_refs")
    @classmethod
    def sanitize_refs(cls, refs: list[str]) -> list[str]:
        cleaned: list[str] = []
        for ref in refs:
            item = ref.strip()
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned


class ExecutionTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step: str = Field(min_length=1, max_length=120)
    status: Literal["ok", "warning", "blocked", "skipped", "error"]
    detail: str = Field(min_length=1, max_length=400)


class PriceLogisticsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    candidates: list[CandidateProduct] = Field(default_factory=list)
    execution_trace: list[ExecutionTraceEvent] = Field(
        default_factory=list, alias="executionTrace"
    )
    blockers: list[str] = Field(default_factory=list)
    consent_autofill: bool = Field(alias="consentAutofill")
    stop_before_pay: bool = Field(alias="stopBeforePay")

    @field_validator("blockers")
    @classmethod
    def sanitize_blockers(cls, blockers: list[str]) -> list[str]:
        return [item.strip() for item in blockers if item.strip()]

    @model_validator(mode="after")
    def enforce_stop_before_pay(self) -> "PriceLogisticsOutput":
        if not self.stop_before_pay:
            raise ValueError("stopBeforePay must be true to satisfy checkout safety policy.")
        return self


class VisualInsight(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: Literal["OK", "NEED_MORE_EVIDENCE"]
    authenticity_score: int = Field(alias="authenticityScore", ge=0, le=100)
    mismatch_flags: list[str] = Field(default_factory=list, alias="mismatchFlags")
    visual_risks: list[str] = Field(default_factory=list, alias="visualRisks")
    confidence: float = Field(ge=0, le=1)
    required_evidence: list[str] = Field(default_factory=list, alias="requiredEvidence")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")

    @model_validator(mode="after")
    def enforce_evidence_requirement(self) -> "VisualInsight":
        if self.status == "NEED_MORE_EVIDENCE" and len(self.required_evidence) == 0:
            raise ValueError(
                "requiredEvidence must be provided when status is NEED_MORE_EVIDENCE."
            )
        return self
