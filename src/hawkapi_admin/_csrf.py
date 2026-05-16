"""CSRF token subsystem for admin form POSTs.

Per-session double-submit cookie pattern:
  * On every render of a page that contains a form, ensure a cookie
    ``hawkapi_admin_csrf`` is set (or reused) with a 32-byte URL-safe token.
  * Templates render the same token as a hidden ``<input name="_csrf">``.
  * POST handlers compare cookie and form value via ``hmac.compare_digest``.

The cookie is intentionally NOT ``HttpOnly`` so Jinja-rendered server-side
templates can echo it back without needing JavaScript — but the template
reads it from the request scope, not the cookie itself, so the lack of
HttpOnly is purely a defense-in-depth concern (an attacker who can run JS
on the admin origin has already lost).
"""

from __future__ import annotations

import hmac
import secrets
from typing import Any

COOKIE_NAME = "hawkapi_admin_csrf"
FORM_FIELD = "_csrf"
SCOPE_KEY = "admin_csrf_token"
SCOPE_NEW_KEY = "admin_csrf_token_is_new"


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_token(request: Any) -> str:
    """Return the per-session CSRF token, reading the cookie or generating a new one.

    The token is cached on ``request.scope`` so multiple template renders within
    the same request return the same value, and so the response builder can
    decide whether to emit a ``Set-Cookie`` header.
    """
    cached = request.scope.get(SCOPE_KEY)
    if isinstance(cached, str) and cached:
        return cached
    token = request.cookies.get(COOKIE_NAME)
    is_new = False
    if not isinstance(token, str) or not token:
        token = _generate_token()
        is_new = True
    request.scope[SCOPE_KEY] = token
    request.scope[SCOPE_NEW_KEY] = is_new
    return token


def build_set_cookie_header(token: str, *, path: str) -> str:
    """Build a Set-Cookie header value for the CSRF cookie."""
    return f"{COOKIE_NAME}={token}; Path={path}; Secure; SameSite=Lax"


def validate_csrf(request: Any, form: Any) -> None:
    """Validate that the form-supplied token matches the cookie token.

    Raises ``HTTPException(403)`` on mismatch. Imported here lazily to avoid
    a hard module-level dependency on hawkapi when this file is exercised
    in isolation.
    """
    from hawkapi import HTTPException

    cookie_token = request.cookies.get(COOKIE_NAME) or ""
    form_token_raw = form.get(FORM_FIELD)
    form_token = form_token_raw if isinstance(form_token_raw, str) else ""
    if not cookie_token or not form_token:
        raise HTTPException(403, detail="CSRF token mismatch")
    if not hmac.compare_digest(cookie_token, form_token):
        raise HTTPException(403, detail="CSRF token mismatch")


__all__ = [
    "COOKIE_NAME",
    "FORM_FIELD",
    "SCOPE_KEY",
    "SCOPE_NEW_KEY",
    "build_set_cookie_header",
    "ensure_csrf_token",
    "validate_csrf",
]
