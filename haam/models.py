"""Database models.

Tables are prefixed with ``haam_`` so they never collide with the tables of the
previous version of the app (``entries``, ``locations``, ``tags``). Data from those
tables can be copied over with ``flask haam import-legacy``.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Enum, ForeignKey, Index, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from haam.extensions import db
from haam.dates import format_year, month_day


EXCERPT_LENGTH = 140


def make_excerpt(text: str | None) -> str:
    """The first ``EXCERPT_LENGTH`` characters, cut at a word, with "…" when shortened."""
    text = text or ""
    if len(text) <= EXCERPT_LENGTH:
        return text
    return text[:EXCERPT_LENGTH].rsplit(" ", 1)[0] + "…"


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
    NATURAL = "natural"  # earthquakes, eruptions, storms, floods, fires
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
    __table_args__ = (
        Index("ix_haam_events_status_year", "status", "year"),
        Index("ix_haam_events_month_day", "month", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    year: Mapped[int]  # negative = BC
    date_label: Mapped[str] = mapped_column(String(120), default="")
    # Month and day of a day-precise ``date_label`` ("On this day"); set from it, else None.
    month: Mapped[int | None]
    day: Mapped[int | None]
    summary: Mapped[str] = mapped_column(Text)
    wiki_url: Mapped[str] = mapped_column(String(500), unique=True)
    wiki_page_id: Mapped[int | None] = mapped_column(unique=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(20), unique=True)

    lat: Mapped[float]
    lon: Mapped[float]
    country: Mapped[str | None] = mapped_column(String(100))

    category: Mapped[Category] = mapped_column(_enum_column(Category), default=Category.OTHER)
    status: Mapped[Status] = mapped_column(_enum_column(Status), default=Status.PENDING)
    # True when the submitter changed data extracted from Wikipedia.
    modified: Mapped[bool] = mapped_column(default=False)
    # True for events submitted through "Add event"; False for imports (CLI, CSV, Wikidata).
    from_website: Mapped[bool] = mapped_column(default=False, server_default=false())

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    tags: Mapped[list[Tag]] = relationship(secondary=event_tags, order_by=Tag.start_year)
    # Deleting an event also removes it from every collection that used it.
    collection_entries: Mapped[list["CollectionEntry"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    @validates("date_label")
    def _set_month_day(self, _key: str, label: str | None) -> str | None:
        self.month, self.day = month_day(label) or (None, None)
        return label

    @property
    def display_year(self) -> str:
        return format_year(self.year)

    @property
    def google_maps_url(self) -> str:
        return f"https://www.google.com/maps?q={self.lat},{self.lon}"

    EXCERPT_LENGTH = EXCERPT_LENGTH

    @property
    def excerpt(self) -> str:
        return make_excerpt(self.summary)

    def to_list_dict(self) -> dict:
        """One event as an object: the old /api/events format (the map now uses haam.feed)."""
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "display_year": self.display_year,
            "date": self.date_label,
            "excerpt": self.excerpt,
            "wiki_url": self.wiki_url,
            "lat": self.lat,
            "lon": self.lon,
            "category": self.category.value,
            "tags": [tag.id for tag in self.tags],
        }

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


class Collection(db.Model):
    """A personal map of entries, shared through secret links (no accounts).

    ``view_token`` is part of the public share link. The edit link contains a
    second, longer token of which only a SHA-256 hash is stored.
    """

    __tablename__ = "haam_collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    view_token: Mapped[str] = mapped_column(String(40), unique=True)
    edit_token_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(default=False)  # listed on the Collections page
    is_hidden: Mapped[bool] = mapped_column(default=False)  # hidden by an editor after reports
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    entries: Mapped[list["CollectionEntry"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="(CollectionEntry.position, CollectionEntry.id)",
    )
    reports: Mapped[list["CollectionReport"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan", order_by="CollectionReport.created_at.desc()"
    )

    @property
    def all_wikipedia(self) -> bool:
        """Every entry is backed by an English Wikipedia article."""
        return bool(self.entries) and all(entry.has_wikipedia for entry in self.entries)

    @property
    def all_confirmed(self) -> bool:
        """Every entry is an approved event from the main map."""
        return bool(self.entries) and all(entry.is_confirmed for entry in self.entries)

    @property
    def year_span(self) -> str:
        years = [entry.year for entry in self.entries]
        if not years:
            return ""
        low, high = min(years), max(years)
        return format_year(low) if low == high else f"{format_year(low)} – {format_year(high)}"


class CollectionEntry(db.Model):
    """One point in a collection: either a main-map event or a custom entry.

    Custom entries live only inside their collection and are not reviewed.
    For main-map events the event's own data is shown; only ``note`` is stored
    here – and, optionally, other coordinates for this collection (``custom_lat``
    / ``custom_lon``), which never change the event itself.
    """

    __tablename__ = "haam_collection_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("haam_collections.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("haam_events.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(default=0)
    note: Mapped[str] = mapped_column(Text, default="")

    # Custom entries (and, for main-map events, only custom_lat/custom_lon as a moved place):
    custom_title: Mapped[str | None] = mapped_column(String(300))
    custom_year: Mapped[int | None]
    custom_date_label: Mapped[str | None] = mapped_column(String(120))
    custom_summary: Mapped[str | None] = mapped_column(Text)
    custom_lat: Mapped[float | None]
    custom_lon: Mapped[float | None]
    custom_category: Mapped[Category | None] = mapped_column(_enum_column(Category))
    link: Mapped[str | None] = mapped_column(String(500))
    # True when ``link`` points to an existing English Wikipedia article (checked on save).
    wiki_verified: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    collection: Mapped[Collection] = relationship(back_populates="entries")
    event: Mapped[Event | None] = relationship(back_populates="collection_entries")

    @property
    def is_event(self) -> bool:
        return self.event is not None

    @property
    def is_confirmed(self) -> bool:
        return self.event is not None and self.event.status == Status.APPROVED

    @property
    def has_wikipedia(self) -> bool:
        return self.event is not None or self.wiki_verified

    @property
    def title(self) -> str:
        return self.event.title if self.event else (self.custom_title or "")

    @property
    def year(self) -> int:
        return self.event.year if self.event else (self.custom_year or 0)

    @property
    def display_year(self) -> str:
        return format_year(self.year)

    @property
    def date_label(self) -> str:
        return self.event.date_label if self.event else (self.custom_date_label or "")

    @property
    def summary(self) -> str:
        return self.event.summary if self.event else (self.custom_summary or "")

    @property
    def moved(self) -> bool:
        """A main-map event shown at other coordinates in this collection."""
        return self.event is not None and self.custom_lat is not None and self.custom_lon is not None

    @property
    def lat(self) -> float:
        return self.custom_lat if self.moved or not self.event else self.event.lat

    @property
    def lon(self) -> float:
        return self.custom_lon if self.moved or not self.event else self.event.lon

    @property
    def category(self) -> Category:
        return self.event.category if self.event else (self.custom_category or Category.OTHER)

    @property
    def url(self) -> str | None:
        return self.event.wiki_url if self.event else self.link

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "display_year": self.display_year,
            "date": self.date_label,
            "summary": self.summary,
            "note": self.note,
            "lat": self.lat,
            "lon": self.lon,
            "category": self.category.value,
            "url": self.url,
            "is_event": self.is_event,
            "is_confirmed": self.is_confirmed,
            "has_wikipedia": self.has_wikipedia,
            "moved": self.moved,
        }

    def to_map_dict(self) -> dict:
        """The shape of ``Event.to_list_dict`` (the main map's data), plus the full text and note."""
        summary = self.summary
        excerpt = make_excerpt(summary)
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "display_year": self.display_year,
            "date": self.date_label,
            "excerpt": excerpt,
            "summary": summary,
            "note": self.note,
            "wiki_url": self.url if self.has_wikipedia else None,
            "link": None if self.has_wikipedia else self.link,
            "lat": self.lat,
            "lon": self.lon,
            "category": self.category.value,
            "tags": [tag.id for tag in self.event.tags] if self.event else [],
            "moved": self.moved,
        }


class CollectionReport(db.Model):
    """A visitor's report about an inappropriate public collection."""

    __tablename__ = "haam_collection_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("haam_collections.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    collection: Mapped[Collection] = relationship(back_populates="reports")
