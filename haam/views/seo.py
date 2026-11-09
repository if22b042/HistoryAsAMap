"""Files for search engines and browsers: sitemap, robots.txt and icons."""

from flask import Blueprint, Response, abort, current_app

from haam import seo

bp = Blueprint("seo", __name__)

CACHE_SECONDS = 3600


def _text(body: str, mimetype: str) -> Response:
    response = Response(body, mimetype=mimetype)
    response.cache_control.public = True
    response.cache_control.max_age = CACHE_SECONDS
    return response


@bp.get("/sitemap.xml")
def sitemap():
    """One sitemap while everything fits in 50,000 URLs, otherwise an index of several."""
    if seo.fits_one_sitemap():
        return _text(seo.urlset_xml(seo.static_urls() + seo.event_urls()), "application/xml")
    pages = [seo.external_url("seo.sitemap_part", part="pages")]
    pages += [seo.external_url("seo.sitemap_part", part=f"events-{n}")
              for n in range(1, seo.sitemap_page_count() + 1)]
    return _text(seo.sitemap_index_xml(pages), "application/xml")


@bp.get("/sitemap-<part>.xml")
def sitemap_part(part: str):
    if seo.fits_one_sitemap():
        abort(404)
    if part == "pages":
        return _text(seo.urlset_xml(seo.static_urls()), "application/xml")
    prefix, _, number = part.partition("-")
    if prefix != "events" or not number.isdigit() or not 1 <= int(number) <= seo.sitemap_page_count():
        abort(404)
    offset = (int(number) - 1) * seo.SITEMAP_LIMIT
    return _text(seo.urlset_xml(seo.event_urls(offset, seo.SITEMAP_LIMIT)), "application/xml")


@bp.get("/robots.txt")
def robots():
    return _text(seo.robots_txt(), "text/plain")


@bp.get("/favicon.ico")
def favicon():
    return current_app.send_static_file("img/favicon.ico")


@bp.get("/apple-touch-icon.png")
@bp.get("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    return current_app.send_static_file("img/apple-touch-icon.png")
