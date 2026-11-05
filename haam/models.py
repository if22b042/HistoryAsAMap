"""Database models.

Tables are prefixed with ``haam_`` so they never collide with the tables of the
previous version of the app (``entries``, ``locations``, ``tags``). Data from those
tables can be copied over with ``flask haam import-legacy``.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from haam.extensions import db
from haam.dates import format_year


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_column(enum_cls: type[enum.Enum]) -> Enum:
    """Store enums as their lowercase *value* in a plain VARCHAR (portable)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class Category(enum.Enum):
    MILITARY = "military"
    DIPLOMATIC = "diplomatic"
    NAVAL = "naval"
    SCIENTIFIC = "scientific"
    OTHER = "other"

    @property
    def label(self) -> str:
        return self.value.capitalize()


class Status(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


event_tags = db.Table(
    "haam_event_tags",
    db.Column("event_id", ForeignKey("haam_events.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", ForeignKey("haam_tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(db.Model):
    """A historical period or conflict events can be grouped under."""

    __tablename__ = "haam_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    start_year: Mapped[int | None]
    end_year: Mapped[int | None]  # None = still ongoing

    @property
    def display_range(self) -> str:
        start = format_year(self.start_year) if self.start_year is not None else "?"
        end = format_year(self.end_year) if self.end_year is not None else "present"
        return f"{start} – {end}"

    @property
    def sort_year(self) -> float:
        years = [y for y in (self.start_year, self.end_year) if y is not None]
        return sum(years) / len(years) if years else 0

    def covers(self, year: int) -> bool:
        start = self.start_year if self.start_year is not None else -10**6
        end = self.end_year if self.end_year is not None else 10**6
        return start <= year <= end

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "display_range": self.display_range,
        }


class Event(db.Model):
    """A historical event shown on the map."""

    __tablename__ = "haam_events"
    __table_args__ = (Index("ix_haam_events_status_year", "status", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    year: Mapped[int]  # negative = BC
    date_label: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text)
    wiki_url: Mapped[str] = mapped_column(String(500), unique=True)
    wiki_page_id: Mapped[int | None] = mapped_column(unique=True)

    lat: Mapped[float]
    lon: Mapped[float]
    country: Mapped[str | None] = mapped_column(String(100))

    category: Mapped[Category] = mapped_column(_enum_column(Category), default=Category.OTHER)
    status: Mapped[Status] = mapped_column(_enum_column(Status), default=Status.PENDING)
    # True when the submitter changed data extracted from Wikipedia.
    modified: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    tags: Mapped[list[Tag]] = relationship(secondary=event_tags, order_by=Tag.start_year)

    @property
    def display_year(self) -> str:
        return format_year(self.year)

    @property
    def google_maps_url(self) -> str:
        return f"https://www.google.com/maps?q={self.lat},{self.lon}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "display_year": self.display_year,
            "date": self.date_label,
            "summary": self.summary,
            "wiki_url": self.wiki_url,
            "lat": self.lat,
            "lon": self.lon,
            "country": self.country,
            "category": self.category.value,
            "tags": [tag.id for tag in self.tags],
        }
