from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Enum
from datetime import datetime
import enum

db = SQLAlchemy()


class EventCategory(enum.Enum):
    MILITARY = "military"
    DIPLOMATIC = "diplomatic"
    NAVAL = "naval"
    POLITICAL = "political"
    ECONOMIC = "economic"
    CULTURAL = "cultural"
    SCIENTIFIC = "scientific"
    OTHER = "other"


class Entry(db.Model):
    __tablename__ = 'entries'

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(nullable=False)
    modified: Mapped[bool] = mapped_column(nullable=False, default=False)
    dateString: Mapped[str] = mapped_column(db.String(100), nullable=False)
    firstParagraph: Mapped[str] = mapped_column(db.Text, nullable=False)
    title: Mapped[str] = mapped_column(db.Text, nullable=True)
    wikiLink: Mapped[str] = mapped_column(db.String(255), nullable=True, unique=True)
    used: Mapped[bool] = mapped_column(nullable=False, default=False)
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory), nullable=False)

    # 1:1 relation – each entry has exactly one location
    location: Mapped["Location"] = relationship(back_populates="entry", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "first_paragraph": self.firstParagraph,
            "link": self.wikiLink,
            "category": self.category.value if self.category else None,
            "location": self.location.to_dict() if self.location else None
        }


class Location(db.Model):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    coordinates: Mapped[str] = mapped_column(db.String(255), nullable=False)
    country: Mapped[str] = mapped_column(db.String(100), nullable=True)
    on_water: Mapped[bool] = mapped_column(nullable=False, default=False)



    # 1:1 relationship back to Entry
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id"), unique=False, nullable=False
    )
    entry: Mapped[Entry] = relationship(back_populates="location")

    def to_dict(self):
        return {
            "id": self.id,
            "coordinates": self.coordinates,
            "country": self.country,
            "on_water": self.on_water,
        }



