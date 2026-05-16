# Changelog

## 0.2.0 — 2026-05-16

Security hardening — **breaking**.

- CSRF tokens required on all admin POSTs by default (`Admin(csrf_enabled=...)` to opt out for tests / behind-auth deployments). Token stored in `hawkapi_admin_csrf` cookie (Secure, SameSite=Lax) and echoed via hidden `_csrf` form field.
- Optional `auth` callable on `Admin`/`init_admin` — invoked at the top of every route, raises `HTTPException` to reject. A `UserWarning` is emitted at construction and a `logger.warning` at `attach()` when no auth is configured.
- `save()` catches `SQLAlchemyError`/`ValueError`/`TypeError` and re-renders the form with a `400` plus a short `errors["_form"]` message instead of leaking a 500.
- Clear-to-NULL semantics — a field that is present-but-empty in the form is now coerced to `None` (when nullable) instead of being silently skipped.
- Pagination links URL-encode the `?q=` parameter.
- `ModelResource.__post_init__` warns when an editable field name looks sensitive (`password`/`secret`/`token`/`key`/`hash`) and isn't in `readonly_fields`.
- `Admin.register()` raises `ValueError` on duplicate resource names.

## 0.1.1 — 2026-05-16

Fix wheel build: drop the empty `static/` force-include entry that broke `uv build` in CI.

## 0.1.0 — 2026-05-16

Initial release.

- `Admin` orchestrator + `init_admin(app)` — mounts index / list / detail / create / edit / delete routes under `/admin`.
- `ModelResource` — declarative wrapper over a SQLAlchemy model with knobs for `list_display`, `list_search`, `form_fields`, `readonly_fields`, `page_size`, `can_create/update/delete`, custom `label`, `icon`.
- Type-driven widget picker (checkbox / number / date / datetime / textarea / enum / text), automatic from each column's SQLAlchemy type.
- Search on the list page (`?q=`) backed by ILIKE against the configured columns.
- Pagination.
- Light + dark mode CSS, ~60 lines inline in `_base.html`.
- Built on top of hawkapi-sqlalchemy — picks up the session factory from `init_database(app, ...)`.
