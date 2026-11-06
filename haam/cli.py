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


@haam_cli.command("export-wikidata")
@click.option("--out", default=None, help="CSV of accepted events.  [default: seed/wikidata_events_places.csv, "
                                           "or seed/wikidata_events_undated.csv with --undated]")
@click.option("--rejected", default=None, help="CSV of rejected candidates with the reason.  "
                                               "[default: seed/wikidata_rejected_places.csv, or …_undated.csv]")
@click.option("--type", "type_ids", multiple=True, help="Only these Wikidata types (e.g. --type Q178561).")
@click.option("--limit", type=int, default=None, help="At most this many candidates per type (for trial runs).")
@click.option("--status", type=click.Choice(["approved", "pending"]), default="approved", show_default=True,
              help="Status written into the CSV for every accepted event.")
@click.option("--undated", is_flag=True,
              help="Only items without a point in time / start time on Wikidata; their date comes from "
                   "their end time, inception, or the year in their Wikipedia title or first paragraph.")
def export_wikidata_command(out, rejected, type_ids, limit, status, undated):
    """Export validated historical events from Wikidata to a CSV (no database changes).

    Load the result with: flask --app haam haam import-csv seed/wikidata_events_places.csv
    """
    suffix = "undated" if undated else "places"
    out = out or f"seed/wikidata_events_{suffix}.csv"
    rejected = rejected or f"seed/wikidata_rejected_{suffix}.csv"
    from flask import current_app
    from sqlalchemy import select

    from haam.extensions import db
    from haam.models import Tag
    from haam.wikidata import WikidataClient, export

    client = WikidataClient(current_app.config["HAAM_USER_AGENT"])
    tag_names = db.session.scalars(select(Tag.name)).all()
    click.echo("Discovering candidates on Wikidata…")
    stats = export(client, out, rejected, type_ids=list(type_ids) or None, limit_per_type=limit,
                   status=status, tag_names=tag_names, undated=undated, report=click.echo)
    click.echo()
    click.echo(f"Accepted {stats.accepted} of {stats.candidates} candidates -> {out}")
    click.echo(f"Rejected {stats.rejected} -> {rejected}")
    for reason, count in sorted(stats.reasons.items(), key=lambda kv: -kv[1]):
        click.echo(f"  {count:6d}  {reason}")
    if stats.failed_types:
        click.echo(err=True)
        click.echo("INCOMPLETE – discovery failed for: " + ", ".join(stats.failed_types), err=True)
        click.echo("Re-run just those with --type, e.g. --type " + stats.failed_types[0].split("(")[-1].rstrip(")"),
                   err=True)
        raise SystemExit(1)


@haam_cli.command("remove-events")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--reason", default="", help="Only rows whose reason column starts with this text.")
@click.option("--dry-run", is_flag=True, help="Only count what would be removed.")
def remove_events_command(path, reason, dry_run):
    """Delete the events whose wikidata_id is listed in a CSV (e.g. a rejected file).

    Example – the events placed at a country or region:
    flask --app haam haam remove-events seed/wikidata_rejected_places.csv --reason "location is a country"
    """
    stats = importer.remove_listed(path, reason=reason, dry_run=dry_run, report=click.echo)
    click.echo(f"Done: {stats}")
    if stats.kept_in_collections:
        click.echo("Kept because they are used in a collection: " + "; ".join(stats.kept_in_collections))


@haam_cli.command("retag-csv")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
def retag_csv_command(paths):
    """Recompute the tags column of exported CSVs from Wikidata's "part of" chains (in place)."""
    from flask import current_app

    from haam.tagging import retag_csv
    from haam.wikidata import WikidataClient

    client = WikidataClient(current_app.config["HAAM_USER_AGENT"])
    for path in paths:
        click.echo(f"{path}:")
        stats = retag_csv(client, path, report=click.echo)
        click.echo(f"  tagged {stats['tagged_before']} -> {stats['tagged_after']} of {stats['rows']} rows "
                   f"({stats['changed']} changed)")


@haam_cli.command("retag-events")
@click.option("--dry-run", is_flag=True, help="Only count what would change.")
@click.option("--replace", is_flag=True,
              help="Also remove tags the rules no longer give (imported events only; website submissions untouched).")
def retag_events_command(dry_run, replace):
    """Re-apply the tag rules to imported events with a Wikidata id (adds missing tags; --replace also removes)."""
    from flask import current_app

    from haam.tagging import retag_database
    from haam.wikidata import WikidataClient

    client = WikidataClient(current_app.config["HAAM_USER_AGENT"])
    stats = retag_database(client, dry_run=dry_run, replace=replace, report=click.echo)
    prefix = "Would change" if dry_run else "Changed"
    click.echo(f"{prefix} {stats['events_changed']} events: +{stats['links_added']} tags, "
               f"-{stats['links_removed']} tags; events with a tag: "
               f"{stats['tagged_before']} -> {stats['tagged_after']} of {stats['events']}")


@haam_cli.command("import-legacy")
def import_legacy_command():
    """Copy events from the previous version's tables (entries/locations)."""
    importer.seed_tags()
    click.echo(f"Done: {importer.import_legacy()}")


def register(app: Flask) -> None:
    app.cli.add_command(haam_cli)
