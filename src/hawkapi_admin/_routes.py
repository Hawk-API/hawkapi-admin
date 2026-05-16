"""Route handlers — list / detail / create / edit / delete."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hawkapi import HTTPException, Request
from hawkapi.responses import HTMLResponse, RedirectResponse, Response
from hawkapi_sqlalchemy import resolve_database
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import String as SAString
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from ._csrf import (
    COOKIE_NAME,
    SCOPE_NEW_KEY,
    build_set_cookie_header,
    ensure_csrf_token,
    validate_csrf,
)
from ._inspect import coerce_value, widget_for
from ._resource import ModelResource

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        enable_async=True,
    )
    env.globals["widget_for"] = widget_for  # type: ignore[assignment]
    return env


_env = _build_env()


def _resource(admin: Any, name: str) -> ModelResource:
    found = admin.resources.get(name)
    if found is None:
        raise HTTPException(404, detail=f"Unknown resource {name!r}")
    return found


def _session_factory(request: Request) -> Any:
    db = resolve_database(request.scope.get("app"))
    if db is None:
        raise HTTPException(
            500, detail="Database not configured — call init_database(app, ...) first"
        )
    return db.session


def _attach_csrf_cookie(request: Any, response: Response, admin: Any) -> Response:
    """Attach Set-Cookie header to the response if a new CSRF token was minted."""
    if not getattr(admin, "csrf_enabled", True):
        return response
    if not request.scope.get(SCOPE_NEW_KEY):
        return response
    token = request.scope.get("admin_csrf_token")
    if not isinstance(token, str) or not token:
        return response
    cookie_value = build_set_cookie_header(token, path=admin.url_prefix)
    # Stash on headers dict — Response will emit it. If a Set-Cookie already
    # exists, append rather than overwrite.
    existing = response.headers.get("set-cookie")
    if existing:
        response.headers["set-cookie"] = f"{existing}, {cookie_value}"
    else:
        response.headers["set-cookie"] = cookie_value
    return response


async def _render(
    request: Any,
    _admin: Any,
    template: str,
    *,
    status_code: int = 200,
    **context: Any,
) -> Response:
    csrf_token = ensure_csrf_token(request) if getattr(_admin, "csrf_enabled", True) else ""
    tpl = _env.get_template(template)
    body = await tpl.render_async(csrf_token=csrf_token, **context)
    resp = HTMLResponse(body, status_code=status_code)
    return _attach_csrf_cookie(request, resp, _admin)


async def index(request: Request, *, admin: Any) -> Response:
    return await _render(
        request,
        admin,
        "index.html",
        admin=admin,
        resources=list(admin.resources.values()),
    )


async def list_resource(request: Request, *, admin: Any) -> Response:
    name = str(request.path_params["resource"])
    res = _resource(admin, name)
    q = request.query_params.get("q", "")
    page = max(1, int(request.query_params.get("page", "1") or 1))
    sessions = _session_factory(request)

    stmt = select(res.model)
    count_stmt = select(func.count()).select_from(res.model)
    if q and res.list_search:
        conditions = []
        for col_name in res.list_search:
            col = getattr(res.model, col_name)
            conditions.append(col.cast(SAString).ilike(f"%{q}%"))
        stmt = stmt.where(or_(*conditions))
        count_stmt = count_stmt.where(or_(*conditions))
    stmt = stmt.offset((page - 1) * res.page_size).limit(res.page_size)

    async with sessions(commit=False) as sess:
        rows = (await sess.execute(stmt)).scalars().all()
        total = int((await sess.execute(count_stmt)).scalar() or 0)
    return await _render(
        request,
        admin,
        "list.html",
        admin=admin,
        resource=res,
        rows=rows,
        page=page,
        page_size=res.page_size,
        total=total,
        q=q,
        pages=(total + res.page_size - 1) // res.page_size,
    )


async def detail(request: Request, *, admin: Any) -> Response:
    name = str(request.path_params["resource"])
    res = _resource(admin, name)
    pk = request.path_params["pk"]
    sessions = _session_factory(request)
    async with sessions(commit=False) as sess:
        obj = await sess.get(res.model, pk)
        if obj is None:
            raise HTTPException(404)
    return await _render(request, admin, "detail.html", admin=admin, resource=res, obj=obj)


async def edit_form(request: Request, *, admin: Any) -> Response:
    name = str(request.path_params["resource"])
    res = _resource(admin, name)
    pk = request.path_params.get("pk")
    sessions = _session_factory(request)
    obj = None
    if pk is not None:
        if not res.can_update:
            raise HTTPException(403)
        async with sessions(commit=False) as sess:
            obj = await sess.get(res.model, pk)
            if obj is None:
                raise HTTPException(404)
    else:
        if not res.can_create:
            raise HTTPException(403)
    values: dict[str, Any] = (
        {f.name: getattr(obj, f.name, "") for f in res.editable_fields()} if obj else {}
    )
    return await _render(
        request,
        admin,
        "form.html",
        admin=admin,
        resource=res,
        obj=obj,
        values=values,
        errors={},
    )


def _coerce_form_values(res: ModelResource, form: Any, *, creating: bool) -> dict[str, Any]:
    """Translate raw form values into model field values.

    A field that is *not present* in the form is skipped — preserving the existing
    value on update, falling through to the column default on insert. A field that
    *is present and empty* is coerced to None when the column allows it.
    """
    values: dict[str, Any] = {}
    for fs in res.editable_fields():
        if fs.name not in form:
            # Boolean fields use checkboxes that don't submit when unchecked —
            # treat absence as False on create, leave alone on update.
            if fs.python_type is bool and creating:
                values[fs.name] = False
            continue
        raw = form.get(fs.name)
        raw_str = raw if isinstance(raw, str) else None
        coerced = coerce_value(fs, raw_str)
        if coerced is None and not fs.nullable and creating and fs.has_default:
            # Empty value for a not-null column with a server default during CREATE:
            # skip so the default kicks in.
            continue
        values[fs.name] = coerced
    return values


async def save(request: Request, *, admin: Any) -> Response:
    name = str(request.path_params["resource"])
    res = _resource(admin, name)
    pk = request.path_params.get("pk")
    sessions = _session_factory(request)
    form = await request.form()
    if getattr(admin, "csrf_enabled", True):
        validate_csrf(request, form)

    # Authorization first — fail fast.
    if pk is None and not res.can_create:
        raise HTTPException(403)
    if pk is not None and not res.can_update:
        raise HTTPException(403)

    creating = pk is None
    values = _coerce_form_values(res, form, creating=creating)

    try:
        async with sessions() as sess:
            if pk is not None:
                obj = await sess.get(res.model, pk)
                if obj is None:
                    raise HTTPException(404)
                for k, v in values.items():
                    setattr(obj, k, v)
            else:
                obj = res.model(**values)
                sess.add(obj)
            await sess.flush()
            new_pk = getattr(obj, res.primary_key)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        # Render the form again with a short error message. Keep the message
        # bounded so we don't leak full driver tracebacks.
        detail_msg = str(getattr(exc, "orig", None) or exc).splitlines()[0][:200]
        return await _render(
            request,
            admin,
            "form.html",
            status_code=400,
            admin=admin,
            resource=res,
            obj=None if creating else await _safe_get(request, res, pk),
            values=values,
            errors={"_form": detail_msg},
        )
    except (ValueError, TypeError) as exc:
        detail_msg = str(exc).splitlines()[0][:200]
        return await _render(
            request,
            admin,
            "form.html",
            status_code=400,
            admin=admin,
            resource=res,
            obj=None if creating else await _safe_get(request, res, pk),
            values=values,
            errors={"_form": detail_msg},
        )
    return RedirectResponse(f"{admin.url_prefix}/{name}/{new_pk}", status_code=303)


async def _safe_get(request: Request, res: ModelResource, pk: Any) -> Any:
    """Best-effort fetch of the object being edited for the re-render path."""
    try:
        sessions = _session_factory(request)
        async with sessions(commit=False) as sess:
            return await sess.get(res.model, pk)
    except Exception:
        return None


async def delete(request: Request, *, admin: Any) -> Response:
    name = str(request.path_params["resource"])
    res = _resource(admin, name)
    if not res.can_delete:
        raise HTTPException(403)
    if getattr(admin, "csrf_enabled", True):
        form = await request.form()
        validate_csrf(request, form)
    pk = request.path_params["pk"]
    sessions = _session_factory(request)
    async with sessions() as sess:
        obj = await sess.get(res.model, pk)
        if obj is None:
            raise HTTPException(404)
        await sess.delete(obj)
    return RedirectResponse(f"{admin.url_prefix}/{name}", status_code=303)


__all__ = ["delete", "detail", "edit_form", "index", "list_resource", "save", "COOKIE_NAME"]
