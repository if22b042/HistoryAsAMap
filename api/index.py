"""Vercel entry point: the Python runtime serves the WSGI ``app`` defined here.

vercel.json rewrites every URL to ``/api/index?__path=<original path>``, because
the runtime hands Flask the rewritten path. ``_restore_path`` puts the original
path back before Flask routes the request.
"""

from urllib.parse import parse_qsl, urlencode

from haam import create_app

PATH_PARAM = "__path"


def _restore_path(wsgi_app):
    def app(environ, start_response):
        query = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        paths = [value for key, value in query if key == PATH_PARAM]
        if paths:
            environ["PATH_INFO"] = "/" + paths[0].lstrip("/")
            environ["QUERY_STRING"] = urlencode([(k, v) for k, v in query if k != PATH_PARAM])
        elif environ.get("PATH_INFO") == "/api/index":
            environ["PATH_INFO"] = "/"
        return wsgi_app(environ, start_response)

    return app


app = create_app()
app.wsgi_app = _restore_path(app.wsgi_app)
