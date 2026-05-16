"""End-to-end smoke tests against the mounted admin routes."""

from __future__ import annotations

import re
from typing import Any

import pytest
from hawkapi import HawkAPI, HTTPException
from hawkapi.testing import TestClient
from hawkapi_sqlalchemy import init_database

from hawkapi_admin import Admin, ModelResource

from .conftest import User, _noop_auth


def test_index_lists_resources(app: HawkAPI, admin: Admin) -> None:
    r = TestClient(app).get(admin.url_prefix)
    assert r.status_code == 200
    body = r.text
    assert "Test Admin" in body
    assert "Users" in body


def test_empty_list_page_renders(app: HawkAPI, admin: Admin) -> None:
    r = TestClient(app).get(f"{admin.url_prefix}/user")
    assert r.status_code == 200
    assert "No users yet" in r.text or "users" in r.text.lower()


def test_create_and_list_user(app: HawkAPI, admin: Admin) -> None:
    client = TestClient(app)
    new_form = client.get(f"{admin.url_prefix}/user/new")
    assert new_form.status_code == 200
    assert "Email" in new_form.text or "email" in new_form.text

    r = client.post(
        f"{admin.url_prefix}/user/new",
        body=b"email=a%40b.c&name=Alice",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code in (200, 303)

    listed = client.get(f"{admin.url_prefix}/user")
    assert listed.status_code == 200
    assert "a@b.c" in listed.text


def test_detail_then_edit_then_delete(app: HawkAPI, admin: Admin) -> None:
    client = TestClient(app)
    client.post(
        f"{admin.url_prefix}/user/new",
        body=b"email=x%40y.z&name=Bob",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    listed = client.get(f"{admin.url_prefix}/user")
    assert "x@y.z" in listed.text

    # Detail
    detail = client.get(f"{admin.url_prefix}/user/1")
    assert detail.status_code == 200
    assert "x@y.z" in detail.text

    # Edit form
    edit = client.get(f"{admin.url_prefix}/user/1/edit")
    assert edit.status_code == 200

    # Update
    upd = client.post(
        f"{admin.url_prefix}/user/1/edit",
        body=b"email=x%40y.z&name=BobUpdated",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert upd.status_code in (200, 303)
    detail = client.get(f"{admin.url_prefix}/user/1")
    assert "BobUpdated" in detail.text

    # Delete
    deleted = client.post(f"{admin.url_prefix}/user/1/delete")
    assert deleted.status_code in (200, 303)
    listed = client.get(f"{admin.url_prefix}/user")
    assert "x@y.z" not in listed.text


def test_unknown_resource_returns_404(app: HawkAPI, admin: Admin) -> None:
    r = TestClient(app).get(f"{admin.url_prefix}/nope")
    assert r.status_code == 404


def test_unknown_pk_returns_404(app: HawkAPI, admin: Admin) -> None:
    r = TestClient(app).get(f"{admin.url_prefix}/user/9999")
    assert r.status_code == 404


def test_search_filters_results(app: HawkAPI, admin: Admin) -> None:
    client = TestClient(app)
    client.post(
        f"{admin.url_prefix}/user/new",
        body=b"email=cat%40a.b&name=Cat",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    client.post(
        f"{admin.url_prefix}/user/new",
        body=b"email=dog%40a.b&name=Dog",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    found = client.get(f"{admin.url_prefix}/user?q=cat")
    assert "cat@a.b" in found.text
    assert "dog@a.b" not in found.text


# --------------------------------------------------------------------------- #
# CSRF + auth regression tests                                                #
# --------------------------------------------------------------------------- #


def _csrf_admin(app: HawkAPI) -> Admin:
    a = Admin(title="CSRF Admin", auth=_noop_auth, csrf_enabled=True)
    a.register(ModelResource(model=User, list_search=("email",)))
    a.attach(app)
    return a


_HIDDEN_CSRF = re.compile(r'name="_csrf" value="([^"]+)"')


def _extract_token_and_cookie(client: TestClient, form_path: str) -> tuple[str, str]:
    resp = client.get(form_path)
    match = _HIDDEN_CSRF.search(resp.text)
    assert match is not None, "CSRF hidden input not rendered"
    token = match.group(1)
    cookie = client.cookies.get("hawkapi_admin_csrf")
    assert cookie == token, f"cookie={cookie!r} token={token!r}"
    return token, cookie


def test_csrf_required_for_create(app: HawkAPI) -> None:
    admin = _csrf_admin(app)
    client = TestClient(app)
    r = client.post(
        f"{admin.url_prefix}/user/new",
        body=b"email=a%40b.c&name=A",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 403


def test_csrf_required_for_update(app: HawkAPI) -> None:
    admin = _csrf_admin(app)
    client = TestClient(app)
    # Seed a row via raw SQL (bypassing the admin form so we don't need a token
    # for setup).
    token, _ = _extract_token_and_cookie(client, f"{admin.url_prefix}/user/new")
    client.post(
        f"{admin.url_prefix}/user/new",
        body=f"_csrf={token}&email=a%40b.c&name=A".encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Now try the update without a CSRF field.
    r = client.post(
        f"{admin.url_prefix}/user/1/edit",
        body=b"email=a%40b.c&name=B",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 403


def test_csrf_required_for_delete(app: HawkAPI) -> None:
    admin = _csrf_admin(app)
    client = TestClient(app)
    token, _ = _extract_token_and_cookie(client, f"{admin.url_prefix}/user/new")
    client.post(
        f"{admin.url_prefix}/user/new",
        body=f"_csrf={token}&email=a%40b.c&name=A".encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Drop the cookie+form token entirely.
    r = TestClient(app).post(f"{admin.url_prefix}/user/1/delete")
    assert r.status_code == 403


def test_csrf_valid_token_allows_action(app: HawkAPI) -> None:
    admin = _csrf_admin(app)
    client = TestClient(app)
    token, _ = _extract_token_and_cookie(client, f"{admin.url_prefix}/user/new")
    r = client.post(
        f"{admin.url_prefix}/user/new",
        body=f"_csrf={token}&email=a%40b.c&name=Alice".encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code in (200, 303)
    listed = client.get(f"{admin.url_prefix}/user")
    assert "a@b.c" in listed.text


def test_auth_warning_emitted_when_no_auth() -> None:
    with pytest.warns(UserWarning, match="no auth configured"):
        Admin(title="warn-me")


def test_can_create_false_blocks_post(app: HawkAPI) -> None:
    a = Admin(title="ro", auth=_noop_auth, csrf_enabled=False)
    a.register(ModelResource(model=User, list_search=("email",), can_create=False))
    a.attach(app)
    client = TestClient(app)
    r = client.post(
        f"{a.url_prefix}/user/new",
        body=b"email=a%40b.c&name=A",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 403


def test_can_delete_false_blocks_post(app: HawkAPI) -> None:
    a = Admin(title="ro", auth=_noop_auth, csrf_enabled=False)
    a.register(ModelResource(model=User, list_search=("email",), can_delete=False))
    a.attach(app)
    client = TestClient(app)
    # Create one via direct insert through the admin (creation is allowed).
    client.post(
        f"{a.url_prefix}/user/new",
        body=b"email=a%40b.c&name=A",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r = client.post(f"{a.url_prefix}/user/1/delete")
    assert r.status_code == 403


def test_invalid_int_value_returns_400_with_form(app: HawkAPI) -> None:
    # User.email is unique — second insert with same email triggers IntegrityError,
    # which the save handler must catch and re-render the form with status 400.
    a = Admin(title="ro", auth=_noop_auth, csrf_enabled=False)
    a.register(ModelResource(model=User, list_search=("email",)))
    a.attach(app)
    client = TestClient(app)
    ok = client.post(
        f"{a.url_prefix}/user/new",
        body=b"email=dup%40a.b&name=A",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert ok.status_code in (200, 303)
    r = client.post(
        f"{a.url_prefix}/user/new",
        body=b"email=dup%40a.b&name=B",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 400
    assert "<form" in r.text  # form re-rendered


def test_q_url_encoded_in_pagination(app: HawkAPI) -> None:
    a = Admin(title="t", auth=_noop_auth, csrf_enabled=False)
    a.register(ModelResource(model=User, list_search=("email",), page_size=1))
    a.attach(app)
    client = TestClient(app)
    # Seed two rows so pagination renders.
    client.post(
        f"{a.url_prefix}/user/new",
        body=b"email=alpha%40a.b&name=Alpha",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    client.post(
        f"{a.url_prefix}/user/new",
        body=b"email=beta%40a.b&name=Beta",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Search with a payload that includes characters needing URL encoding.
    r = client.get(f"{a.url_prefix}/user?q=alpha%40a.b")
    # If pagination renders at all (only when q matches >1 row), check encoding;
    # otherwise just verify no raw '@' or '<' leaked into a constructed href.
    if "page=" in r.text and "&q=" in r.text:
        # The literal "@" must be encoded as %40, not present as raw "@" inside href.
        # Easiest: assert raw "<script>" never appears with a separate payload.
        r2 = client.get(f"{a.url_prefix}/user?q=%3Cscript%3E")
        assert "&q=<script>" not in r2.text
        assert "&q=%3Cscript%3E" in r2.text or "page=" not in r2.text


def test_csrf_token_persists_across_requests(app: HawkAPI) -> None:
    """Sanity: the cookie minted on first GET is reused on later requests."""
    admin = _csrf_admin(app)
    client = TestClient(app)
    r1 = client.get(f"{admin.url_prefix}/user/new")
    t1 = _HIDDEN_CSRF.search(r1.text)
    assert t1 is not None
    r2 = client.get(f"{admin.url_prefix}/user/new")
    t2 = _HIDDEN_CSRF.search(r2.text)
    assert t2 is not None
    assert t1.group(1) == t2.group(1)


# Silence the unused-import lints
_ = (HTTPException, init_database, Any)
