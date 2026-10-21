from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ItemEdit(StrictModel):
    version: int = Field(ge=1)
    title: str = Field(default="Untitled garment", max_length=200)
    brand: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=100)
    size: str = Field(default="", max_length=80)
    era: str = Field(default="", max_length=100)
    condition: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=4000)
    cost: float | None = Field(default=None, ge=0, le=1000000)
    asking_price: float | None = Field(default=None, gt=0, le=1000000)
    status: Literal["draft", "ready", "sold"] = "draft"


class Attribute(StrictModel):
    value: str | None = Field(max_length=500)
    evidence: str = Field(max_length=1000)
    certainty: Literal["low", "medium", "high"]


class Identification(StrictModel):
    title: str = Field(max_length=200)
    brand: Attribute
    model: Attribute
    category: Attribute
    size: Attribute
    era: Attribute
    condition: Attribute
    visible_text: list[str] = Field(max_length=30)
    concerns: list[str] = Field(max_length=15)
    missing_photos: list[str] = Field(max_length=10)
    search_queries: list[str] = Field(min_length=1, max_length=3)


class RoughEstimate(StrictModel):
    low: float | None = Field(ge=0, le=1000000)
    high: float | None = Field(ge=0, le=1000000)
    explanation: str = Field(max_length=2000)

    @model_validator(mode="after")
    def range_valid(self):
        if (self.low is None) != (self.high is None):
            raise ValueError("Both ends of the range must be present or null")
        if self.low is not None and self.high < self.low:
            raise ValueError("Range is reversed")
        return self


class ResearchRequest(StrictModel):
    query: str = Field(min_length=3, max_length=300)


class CompInput(StrictModel):
    title: str = Field(min_length=2, max_length=500)
    url: str = Field(max_length=2000)
    price: float = Field(gt=0, le=1000000)
    shipping: float | None = Field(default=None, ge=0, le=100000)
    currency: Literal["USD", "CAD", "GBP", "EUR", "AUD"] = "USD"
    sold_date: date | None = None
    evidence_type: Literal["unknown", "asking", "provider_reported", "manually_verified"] = "unknown"
    notes: str = Field(default="", max_length=2000)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("A public HTTPS source link is required")
        return value

    @model_validator(mode="after")
    def sale_date_valid(self):
        if self.sold_date and self.sold_date > date.today():
            raise ValueError("Sale date cannot be in the future")
        if self.evidence_type in ("provider_reported", "manually_verified") and not self.sold_date:
            raise ValueError("A sold date is required for sale evidence")
        return self


class CompReview(StrictModel):
    version: int = Field(ge=1)
    matched: bool
    verified: bool

