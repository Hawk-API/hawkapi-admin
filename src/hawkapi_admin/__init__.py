"""hawkapi-admin — auto-generated admin UI for SQLAlchemy models.

Drop your models into a :class:`ModelResource` (or pass them directly to
``admin.register(...)``), call :func:`init_admin(app)`, and you get list /
detail / create / edit / delete views mounted under ``/admin`` with no
extra boilerplate.
"""

from __future__ import annotations

from ._admin import Admin, init_admin
from ._inspect import FieldSpec, coerce_value, list_fields, primary_key_column, widget_for
from ._resource import ModelResource

__version__ = "0.2.0"

__all__ = [
    "Admin",
    "FieldSpec",
    "ModelResource",
    "__version__",
    "coerce_value",
    "init_admin",
    "list_fields",
    "primary_key_column",
    "widget_for",
]
