"""ModelResource — declarative wrapper around a SQLAlchemy model."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import DeclarativeBase

from ._inspect import FieldSpec, list_fields, primary_key_column

_SENSITIVE_NAME_RE = re.compile(r"(password|secret|token|key|hash)$", re.IGNORECASE)


@dataclass
class ModelResource:
    """A descriptor that tells the admin how to render and edit a model.

    The only required argument is ``model``. Everything else has a sensible
    default derived from the SQLAlchemy mapper.
    """

    model: type[DeclarativeBase]
    name: str = ""
    """Short identifier used in URLs. Defaults to lowercased class name."""

    label: str = ""
    """Human-readable label. Defaults to class name."""

    label_plural: str = ""
    """Plural form for the list page."""

    icon: str = ""
    """Emoji or short string shown next to the resource link."""

    list_display: tuple[str, ...] = ()
    """Column names shown on the list page. Defaults to every column."""

    list_search: tuple[str, ...] = ()
    """Columns searchable via ``?q=`` query parameter."""

    form_fields: tuple[str, ...] = ()
    """Column names shown in the create/edit form. Defaults to every non-PK column."""

    readonly_fields: tuple[str, ...] = ()
    """Columns that are rendered but cannot be edited."""

    page_size: int = 50
    can_create: bool = True
    can_update: bool = True
    can_delete: bool = True

    _fields: list[FieldSpec] = field(default_factory=list, init=False)
    _pk_name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.model.__name__.lower()
        if not self.label:
            self.label = self.model.__name__
        if not self.label_plural:
            self.label_plural = self.label + "s"
        self._fields = list_fields(self.model)
        self._pk_name = primary_key_column(self.model)
        if not self.list_display:
            self.list_display = tuple(f.name for f in self._fields)
        if not self.form_fields:
            self.form_fields = tuple(f.name for f in self._fields if not f.primary_key)
        for name in self.form_fields:
            if name in self.readonly_fields:
                continue
            if _SENSITIVE_NAME_RE.search(name):
                warnings.warn(
                    f"hawkapi-admin: field {self.model.__name__}.{name} looks "
                    f"sensitive but is not in readonly_fields",
                    UserWarning,
                    stacklevel=2,
                )

    @property
    def fields(self) -> list[FieldSpec]:
        return list(self._fields)

    def field(self, name: str) -> FieldSpec:
        for f in self._fields:
            if f.name == name:
                return f
        raise KeyError(name)

    @property
    def primary_key(self) -> str:
        return self._pk_name

    def display_fields(self) -> list[FieldSpec]:
        return [self.field(n) for n in self.list_display]

    def editable_fields(self) -> list[FieldSpec]:
        return [self.field(n) for n in self.form_fields if n not in self.readonly_fields]

    def render_value(self, obj: Any, field_name: str) -> str:
        value = getattr(obj, field_name, "")
        if value is None:
            return ""
        return str(value)


__all__ = ["ModelResource"]
