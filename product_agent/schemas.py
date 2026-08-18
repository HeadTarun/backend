from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ProductInput(BaseModel):
    manufacturer_part_number: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    supporting_urls: list[HttpUrl] = Field(default_factory=list)
    supporting_text: str | None = None
    custom_image_url: str | None = None


class ProductSpec(BaseModel):
    name: str
    value: str
    unit: str | None = None
    source: str | None = None


class SourceEvidence(BaseModel):
    source_type: str
    locator: str
    excerpt: str
    confidence: Confidence = Confidence.medium


class ProductIntelligence(BaseModel):
    manufacturer_part_number: str
    brand: str
    title: str
    category: str
    commerce_description: str
    image_url: str | None = None
    images: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    specifications: list[ProductSpec] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    compatible_products: list[str] = Field(default_factory=list)
    normalized_attributes: dict[str, str] = Field(default_factory=dict)
    source_evidence: list[SourceEvidence] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.medium
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BatchRequest(BaseModel):
    products: list[ProductInput]


class ComponentStatus(BaseModel):
    name: str
    linked: bool
    detail: str


class RetrievalMatch(BaseModel):
    score: float
    match_type: str
    product: ProductIntelligence


class EvaluationRequest(BaseModel):
    product_input: ProductInput
    output: ProductIntelligence


class EvaluationScore(BaseModel):
    key: str
    score: float
    comment: str
