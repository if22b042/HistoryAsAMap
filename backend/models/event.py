import enum

from sqlalchemy import Enum, ForeignKey, Float, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.extensions import db


# Association table for many-to-many relationship between Entry and Tag
entry_tags = Table(
    'entry_tags',
    db.Model.metadata,
    Column('entry_id', ForeignKey('entries.id'), primary_key=True),
    Column('tag_id', ForeignKey('tags.id'), primary_key=True)
)


class EventCategory(enum.Enum):
    MILITARY = "military"
    DIPLOMATIC = "diplomatic"
    NAVAL = "naval"
    POLITICAL = "political"
    ECONOMIC = "economic"
    CULTURAL = "cultural"
    SCIENTIFIC = "scientific"
    OTHER = "other"


class EntryStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Entry(db.Model):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(nullable=False)
    modified: Mapped[bool] = mapped_column(nullable=False, default=False)
    dateString: Mapped[str] = mapped_column(db.String(100), nullable=False)
    firstParagraph: Mapped[str] = mapped_column(db.Text, nullable=False)
    title: Mapped[str] = mapped_column(db.Text, nullable=True)
    wikiLink: Mapped[str] = mapped_column(db.String(255), nullable=True, unique=True)
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory), nullable=False)
    status: Mapped[EntryStatus] = mapped_column(
        Enum(EntryStatus), nullable=False, default=EntryStatus.PENDING
    )

    location: Mapped["Location"] = relationship(
        back_populates="entry", uselist=False, cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary=entry_tags, back_populates="entries"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "date": self.dateString,
            "first_paragraph": self.firstParagraph,
            "link": self.wikiLink,
            "category": self.category.value if self.category else None,
            "status": self.status.value if self.status else None,
            "modified": self.modified,
            "location": self.location.to_dict() if self.location else None,
            "tags": [tag.name for tag in self.tags] if self.tags else [],
        }


class Location(db.Model):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    country: Mapped[str] = mapped_column(db.String(100), nullable=True)
    on_water: Mapped[bool] = mapped_column(nullable=False, default=False)

    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id"), unique=True, nullable=False
    )
    entry: Mapped[Entry] = relationship(back_populates="location")

    @property
    def google_maps_link(self) -> str:
        return f"https://www.google.com/maps?q={self.lat},{self.lon}"

    def to_dict(self):
        return {
            "id": self.id,
            "lat": self.lat,
            "lon": self.lon,
            "country": self.country,
            "on_water": self.on_water,
            "google_maps_link": self.google_maps_link,
        }


class Tag(db.Model):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(255), nullable=False, unique=True)
    start_year: Mapped[int] = mapped_column(nullable=True)
    end_year: Mapped[int] = mapped_column(nullable=True)

    entries: Mapped[list["Entry"]] = relationship(
        "Entry", secondary=entry_tags, back_populates="tags"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "start_year": self.start_year,
            "end_year": self.end_year,
        }
