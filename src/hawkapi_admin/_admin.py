"""Admin orchestrator — mount under HawkAPI, register resources."""

from __future__ import annotations

import logging
import warnings
from collections.abc import Awaitable, Callable
from typing import Any

from ._resource import ModelResource
from ._routes import delete, detail, edit_form, index, list_resource, save

_logger = logging.getLogger("hawkapi_admin")

AuthCallable = Callable[[Any], Awaitable[None]]


class Admin:
    """Top-level admin object. Build one per HawkAPI app and register resources."""

    def __init__(
        self,
        *,
        title: str = "Admin",
        url_prefix: str = "/admin",
        auth: AuthCallable | None = None,
        csrf_enabled: bool = True,
    ) -> None:
        self.title = title
        self.url_prefix = url_prefix.rstrip("/") or "/admin"
        self.resources: dict[str, ModelResource] = {}
        self.auth: AuthCallable | None = auth
        self.csrf_enabled: bool = csrf_enabled
        if auth is None:
            warnings.warn(
                "hawkapi-admin: no auth configured; all admin endpoints are publicly accessible",
                UserWarning,
                stacklevel=2,
            )

    def register(self, resource: ModelResource | type[Any], **kwargs: Any) -> ModelResource:
        """Register ``resource`` with the admin. Accepts a SQLAlchemy model class
        directly for the simple case::

            admin.register(User)

        or a fully customized :class:`ModelResource`::

            admin.register(ModelResource(model=User, list_display=("id", "email"),
                                         list_search=("email",)))
        """
        if not isinstance(resource, ModelResource):
            resource = ModelResource(model=resource, **kwargs)
        if resource.name in self.resources:
            raise ValueError(f"resource {resource.name!r} already registered")
        self.resources[resource.name] = resource
        return resource

    async def _check_auth(self, request: Any) -> None:
        if self.auth is not None:
            await self.auth(request)

    def attach(self, app: Any) -> None:
        """Wire the admin routes onto ``app``."""
        prefix = self.url_prefix
        admin = self
        if self.auth is None:
            _logger.warning(
                "hawkapi-admin: no auth configured; all admin endpoints are publicly accessible"
            )

        async def _index(request: Any) -> Any:
            await admin._check_auth(request)
            return await index(request, admin=admin)

        async def _list(request: Any) -> Any:
            await admin._check_auth(request)
            return await list_resource(request, admin=admin)

        async def _detail(request: Any) -> Any:
            await admin._check_auth(request)
            return await detail(request, admin=admin)

        async def _new_form(request: Any) -> Any:
            await admin._check_auth(request)
            return await edit_form(request, admin=admin)

        async def _edit_form(request: Any) -> Any:
            await admin._check_auth(request)
            return await edit_form(request, admin=admin)

        async def _save_new(request: Any) -> Any:
            await admin._check_auth(request)
            return await save(request, admin=admin)

        async def _save_existing(request: Any) -> Any:
            await admin._check_auth(request)
            return await save(request, admin=admin)

        async def _delete(request: Any) -> Any:
            await admin._check_auth(request)
            return await delete(request, admin=admin)

        app.get(prefix)(_index)
        app.get(f"{prefix}/{{resource}}")(_list)
        app.get(f"{prefix}/{{resource}}/new")(_new_form)
        app.post(f"{prefix}/{{resource}}/new")(_save_new)
        app.get(f"{prefix}/{{resource}}/{{pk}}")(_detail)
        app.get(f"{prefix}/{{resource}}/{{pk}}/edit")(_edit_form)
        app.post(f"{prefix}/{{resource}}/{{pk}}/edit")(_save_existing)
        app.post(f"{prefix}/{{resource}}/{{pk}}/delete")(_delete)


def init_admin(
    app: Any,
    *,
    admin: Admin | None = None,
    title: str = "Admin",
    url_prefix: str = "/admin",
    auth: AuthCallable | None = None,
    csrf_enabled: bool = True,
) -> Admin:
    """Create an :class:`Admin`, attach it to ``app``, and return it for further registrations."""
    admin = admin or Admin(title=title, url_prefix=url_prefix, auth=auth, csrf_enabled=csrf_enabled)
    admin.attach(app)
    return admin


__all__ = ["Admin", "init_admin"]
