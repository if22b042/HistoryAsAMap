"""Maintenance commands: ``flask --app haam haam <command>``."""

import click
from flask import Flask
from flask.cli import AppGroup
from werkzeug.security import generate_password_hash

from haam import importer
from haam.models import Category

haam_cli = AppGroup("haam", help="History As A Map maintenance commands.")

CATEGORY = click.Choice([c.value for c in Category])


@haam_cli.command("seed-tags")
def seed_tags_command():
    """Add the curated tag list to the database (safe to re-run)."""
    click.echo(f"Added {importer.seed_tags()} tags.")


@haam_cli.command("hash-password")
@click.password_option()
def hash_password_command(password):
    """Print a hash to put in ADMIN_PASSWORD_HASH."""
    click.echo(generate_password_hash(password))


@haam_cli.command("import-titles")
@click.argument("titles", nargs=-1, required=True)
@click.option("--category", type=CATEGORY, default="other", show_default=True)
@click.option("--approve", is_flag=True, help="Publish immediately instead of queueing for review.")
def import_titles_command(titles, category, approve):
    """Import articles by title, e.g. "Battle of Hastings" "Treaty of Versailles"."""
    stats = importer.import_titles(titles, category=Category(category), approve=approve)
    click.echo(f"Done: {stats}")


@haam_cli.command("import-region")
@click.option("--lat", "lat_range", nargs=2, type=float, default=(35, 70), show_default=True,
              help="Minimum and maximum latitude.")
@click.option("--lon", "lon_range", nargs=2, type=float, default=(-10, 40), show_default=True,
              help="Minimum and maximum longitude.")
@click.option("--step", type=float, default=5, show_default=True, help="Grid spacing in degrees.")
@click.option("--radius", type=int, default=10000, show_default=True, help="Search radius in metres (max 10000).")
@click.option("--max-new", type=int, default=100, show_default=True, help="Stop after this many new events.")
@click.option("--approve", is_flag=True, help="Publish immediately instead of queueing for review.")
def import_region_command(lat_range, lon_range, step, radius, max_new, approve):
    """Find dated events on Wikipedia within a lat/lon box (default: Europe)."""
    titles = importer.region_titles(*lat_range, *lon_range, step=step, radius=radius)
    stats = importer.import_titles(titles, approve=approve, require_wikidata_date=True, max_new=max_new)
    click.echo(f"Done: {stats}")


@haam_cli.command("import-csv")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--approve", is_flag=True, help="Publish immediately instead of queueing for review.")
def import_csv_command(path, approve):
    """Import a CSV: url plus optional category,status,year,lat,lon,tags (see seed/events.csv)."""
    click.echo(f"Done: {importer.import_csv(path, approve=approve)}")


@haam_cli.command("import-legacy")
def import_legacy_command():
    """Copy events from the previous version's tables (entries/locations)."""
    importer.seed_tags()
    click.echo(f"Done: {importer.import_legacy()}")


def register(app: Flask) -> None:
    app.cli.add_command(haam_cli)
