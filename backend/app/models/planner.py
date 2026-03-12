from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class SearchConstraints(BaseModel):
    category: str | None = None
    budget_max: float | None = Field(default=None, alias="budgetMax")
    min_rating: float | None = Field(default=None, alias="minRating")
    delivery_deadline: str | None = Field(default=None, alias="deliveryDeadline")
    must_have: list[str] = Field(default_factory=list, alias="mustHave")
    nice_to_have: list[str] = Field(default_factory=list, alias="niceToHave")
    exclude: list[str] = Field(default_factory=list)
    consent_autofill: bool = Field(default=False, alias="consentAutofill")
    visual_evidence: list[str] = Field(default_factory=list, alias="visualEvidence")

    @field_validator("min_rating")
    @classmethod
    def validate_rating(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 0 or value > 5:
            raise ValueError("minRating must be between 0 and 5.")
        return round(value, 1)

    @field_validator("budget_max")
    @classmethod
    def validate_budget(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("budgetMax must be greater than 0.")
        return round(value, 2)

    @field_validator("must_have", "nice_to_have", "exclude")
    @classmethod
    def sanitize_lists(cls, values: list[str]) -> list[str]:
        cleaned = []
        for item in values:
            text = item.strip()
            if text and "http://" not in text and "https://" not in text:
                cleaned.append(text)
        return cleaned

    @field_validator("visual_evidence")
    @classmethod
    def sanitize_visual_evidence(cls, values: list[str]) -> list[str]:
        cleaned = []
        for item in values:
            text = item.strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    @field_validator("consent_autofill", mode="before")
    @classmethod
    def normalize_consent(cls, value: bool | None) -> bool:
        if value is None:
            return False
        return bool(value)

    @model_validator(mode="after")
    def normalize_category(self) -> "SearchConstraints":
        if self.category:
            self.category = self.category.strip().lower()
            if "http://" in self.category or "https://" in self.category:
                self.category = None
        if self.delivery_deadline:
            self.delivery_deadline = self.delivery_deadline.strip()
        return self

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
