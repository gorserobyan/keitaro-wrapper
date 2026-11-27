from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    """A campaign created through the wrapper (local mirror of the Keitaro entity)."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(64))
    geo: Mapped[list[str]] = mapped_column(JSON)
    geo_stream_id: Mapped[int | None] = mapped_column(Integer)
    offers_stream_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    operations: Mapped[list["Operation"]] = relationship(
        back_populates="campaign", order_by="Operation.id.desc()"
    )


class Operation(Base):
    """Audit log of every change the wrapper made in Keitaro."""

    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, index=True)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(32))  # create_campaign / add_offer / ...
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaign: Mapped[Campaign | None] = relationship(back_populates="operations")
