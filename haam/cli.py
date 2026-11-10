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


@haam_cli.command("check-on-this-day")
def check_on_this_day_command():
    """Check that every calendar day (29 February too) has an "On this day" event."""
    from haam.welcome import MONTH_NAMES, days_without_events

    missing = days_without_events()
    if missing:
        click.echo("No event on: " + ", ".join(f"{d} {MONTH_NAMES[m - 1]}" for m, d in missing))
        raise SystemExit(1)
    click.echo("Every one of the 366 days has at least one event.")


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
@click.option("--out", default="seed/wikidata_events.csv", show_default=True, help="CSV of accepted events.")
@click.option("--rejected", default="seed/wikidata_rejected.csv", show_default=True,
              help="CSV of rejected candidates with the reason.")
@click.option("--type", "type_ids", multiple=True, help="Only these Wikidata types (e.g. --type Q178561).")
@click.option("--limit", type=int, default=None, help="At most this many candidates per type (for trial runs).")
@click.option("--status", type=click.Choice(["approved", "pending"]), default="approved", show_default=True,
              help="Status written into the CSV for every accepted event.")
def export_wikidata_command(out, rejected, type_ids, limit, status):
    """Export validated historical events from Wikidata to a CSV (no database changes).

    Load the result into a database with: flask --app haam haam sync-wikidata
    """
    from flask import current_app
    from sqlalchemy import select

    from haam.extensions import db
    from haam.models import Tag
    from haam.wikidata import WikidataClient, export

    client = WikidataClient(current_app.config["HAAM_USER_AGENT"])
    tag_names = db.session.scalars(select(Tag.name)).all()
    click.echo("Discovering candidates on Wikidata…")
    stats = export(client, out, rejected, type_ids=list(type_ids) or None, limit_per_type=limit,
                   status=status, tag_names=tag_names, report=click.echo)
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


@haam_cli.command("sync-wikidata")
@click.argument("path", default="seed/wikidata_events.csv", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, help="Only show what would change.")
def sync_wikidata_command(path, dry_run):
    """Make the database's imported Wikidata events match the final CSV.

    Adds events that are missing, removes imported events no longer in the file,
    and sets every imported event's tags to the file's. Offline and safe to re-run.
    Events submitted on the website, and events used in a collection, are never removed.
    """
    stats = importer.sync_wikidata(path, dry_run=dry_run, report=click.echo)
    prefix = "Would" if dry_run else "Done:"
    click.echo(f"{prefix} add {stats.added}, remove {stats.removed}, re-tag {stats.retagged}, "
               f"re-categorize {stats.recategorized} events "
               f"({stats.unchanged} already up to date; {stats.adopted} older rows linked to their Wikidata id)")
    if stats.kept_in_collections:
        click.echo("Kept although not in the file, because a collection uses them: "
                   + "; ".join(stats.kept_in_collections))


@haam_cli.command("recategorize")
@click.option("--csv", "csv_path", default="seed/wikidata_events.csv", show_default=True,
              help="Also update the category column of this exported CSV ('' to skip).")
@click.option("--dry-run", is_flag=True, help="Only show what would change.")
def recategorize_command(csv_path, dry_run):
    """Re-derive the categories of imported events from their Wikidata classes (P31).

    Splits "natural" into natural and human-made disasters and moves massacres and
    terrorist attacks out of "other" into "disaster". Events submitted on the
    website keep the category their author picked.
    """
    import os

    from flask import current_app

    from haam.recategorize import recategorize
    from haam.wikidata import WikidataClient

    if csv_path and not os.path.exists(csv_path):
        raise click.BadParameter(f"{csv_path} does not exist", param_hint="--csv")
    client = WikidataClient(current_app.config["HAAM_USER_AGENT"])
    stats = recategorize(client, csv_path=csv_path or None, dry_run=dry_run, report=click.echo)
    prefix = "Would move" if dry_run else "Moved"
    for (old, new), count in sorted(stats.moves.items(), key=lambda kv: -kv[1]):
        click.echo(f"  {prefix} {count:5d}  {old} -> {new}")
    if stats.missing:
        click.echo(f"  {stats.missing} events have no classes on Wikidata any more and were left alone")
    if csv_path:
        click.echo(f"  {'Would change' if dry_run else 'Changed'} {stats.csv_changed} rows of {csv_path}")
    if not dry_run:
        click.echo("Approved events per category (before -> after):")
        for category in Category:
            click.echo(f"  {category.value:11s} {stats.before.get(category.value, 0):6d} -> "
                       f"{stats.after.get(category.value, 0):6d}")


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


@haam_cli.command("build-part-of")
@click.argument("path", default="seed/wikidata_events.csv", type=click.Path(exists=True, dir_okay=False))
def build_part_of_command(path):
    """Fetch the "part of" chains of the CSV's tagged events into haam/data/part_of.json.

    The map's tag trees (World War II > Eastern Front > Operation Barbarossa > ...) are
    built from this file. Run it again after export-wikidata or retag-csv, then commit it.
    """
    from flask import current_app

    from haam.tag_tree import GRAPH_PATH, build_graph_file
    from haam.wikidata import WikidataClient

    client = WikidataClient(current_app.config["HAAM_USER_AGENT"])
    graph = build_graph_file(client, path, report=click.echo)
    click.echo(f"{len(graph.parents)} items with a part-of link, {len(graph.labels)} labels, "
               f"{len(graph.tag_items)} tags found on chains -> {GRAPH_PATH}")


@haam_cli.command("import-legacy")
def import_legacy_command():
    """Copy events from the previous version's tables (entries/locations)."""
    importer.seed_tags()
    click.echo(f"Done: {importer.import_legacy()}")


def register(app: Flask) -> None:
    app.cli.add_command(haam_cli)
