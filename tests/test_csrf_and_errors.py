from flask import abort

EXPIRED = "This page has expired – reload it and try again."


def _enable_csrf(app):
    app.config["WTF_CSRF_ENABLED"] = True


def test_csrf_tokens_do_not_expire_on_their_own(app):
    assert app.config["WTF_CSRF_TIME_LIMIT"] is None


def test_expired_form_shows_the_error_page(app, client):
    _enable_csrf(app)
    response = client.post("/admin/login", data={"username": "admin", "password": "x"})
    assert response.status_code == 400
    assert EXPIRED.encode() in response.data
    assert b"Back to the map" in response.data


def test_expired_form_answers_json_when_json_is_asked_for(app, client):
    _enable_csrf(app)
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "x"},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": EXPIRED}


def _add_abort_route(app):
    def aborting(code):
        abort(code)

    app.add_url_rule("/_test/abort/<int:code>", "aborting", aborting)


def test_error_pages_for_400_403_405_and_429(app, client):
    _add_abort_route(app)
    messages = {
        400: b"The request could not be understood.",
        403: b"You are not allowed to do that.",
        405: b"This action is not supported here.",
        429: b"Too many requests.",
    }
    for code, message in messages.items():
        response = client.get(f"/_test/abort/{code}")
        assert response.status_code == code
        assert message in response.data
        assert f"<h1>{code}</h1>".encode() in response.data


def test_json_clients_get_json_errors_for_403(app, client):
    _add_abort_route(app)
    response = client.get("/_test/abort/403", headers={"Accept": "application/json"})
    assert response.status_code == 403
    assert response.get_json() == {"error": "You are not allowed to do that."}
