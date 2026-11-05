"""Single administrator account, configured through environment variables."""

import hmac
from functools import wraps

from flask import current_app, redirect, request, session, url_for
from werkzeug.security import check_password_hash

SESSION_KEY = "is_admin"


def check_credentials(username: str, password: str) -> bool:
    expected_user = current_app.config["ADMIN_USERNAME"]
    password_hash = current_app.config.get("ADMIN_PASSWORD_HASH")
    if not password_hash:
        return False  # admin login disabled until a hash is configured
    user_ok = hmac.compare_digest(username.encode(), expected_user.encode())
    # Always check the password too, so timing doesn't reveal the username.
    password_ok = check_password_hash(password_hash, password)
    return user_ok and password_ok


def log_in() -> None:
    session.clear()
    session[SESSION_KEY] = True
    session.permanent = True


def log_out() -> None:
    session.clear()


def is_admin() -> bool:
    return bool(session.get(SESSION_KEY))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped
