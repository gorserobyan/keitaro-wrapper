from pydantic import BaseModel, Field, field_validator

from app.countries import COUNTRY_CODES


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: list[str] = Field(description='Country codes, e.g. ["AU"] or "MX,AU,RO"')
    offer_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be empty")
        return v

    @field_validator("geo", mode="before")
    @classmethod
    def _normalize_geo(cls, v):
        if isinstance(v, str):
            v = v.replace(";", ",").replace(" ", ",").split(",")
        codes: list[str] = []
        for raw in v or []:
            code = str(raw).strip().upper()
            if code and code not in codes:
                codes.append(code)
        if not codes:
            raise ValueError("At least one country code is required")
        unknown = [c for c in codes if c not in COUNTRY_CODES]
        if unknown:
            raise ValueError(f"Unknown country code(s): {', '.join(unknown)}")
        return codes


class OfferIn(BaseModel):
    offer_id: int = Field(gt=0)


class OfferShare(BaseModel):
    offer_id: int = Field(gt=0)
    share: int = Field(ge=0, le=100)
    state: str = Field(default="active", pattern="^(active|disabled)$")


class SharesUpdate(BaseModel):
    offers: list[OfferShare]
