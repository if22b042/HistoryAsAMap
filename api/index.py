"""Vercel entry point: the Python runtime serves the WSGI ``app`` defined here."""

from haam import create_app

app = create_app()
