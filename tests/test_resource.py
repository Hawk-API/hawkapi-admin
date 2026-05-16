"""ModelResource defaults + customization."""

from __future__ import annotations

import pytest
from hawkapi_sqlalchemy import Base
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hawkapi_admin import Admin, ModelResource

from .conftest import User, _noop_auth


class Secret(Base):
    __tablename__ = "admin_secrets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")


def test_resource_defaults() -> None:
    r = ModelResource(model=User)
    assert r.name == "user"
    assert r.label == "User"
    assert r.label_plural == "Users"
    assert r.primary_key == "id"
    assert "email" in r.list_display
    assert "id" not in r.form_fields  # PK excluded by default


def test_resource_custom_list_display() -> None:
    r = ModelResource(model=User, list_display=("id", "email"))
    names = [f.name for f in r.display_fields()]
    assert names == ["id", "email"]


def test_resource_custom_form_fields() -> None:
    r = ModelResource(model=User, form_fields=("email",))
    names = [f.name for f in r.editable_fields()]
    assert names == ["email"]


def test_resource_field_lookup_raises_for_unknown() -> None:
    r = ModelResource(model=User)
    with pytest.raises(KeyError):
        r.field("ghost")


def test_readonly_fields_excluded_from_editable() -> None:
    r = ModelResource(model=User, form_fields=("email", "name"), readonly_fields=("name",))
    names = [f.name for f in r.editable_fields()]
    assert names == ["email"]


def test_sensitive_field_name_warns() -> None:
    with pytest.warns(UserWarning, match="looks sensitive"):
        ModelResource(model=Secret)


def test_sensitive_field_in_readonly_does_not_warn() -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ModelResource(model=Secret, readonly_fields=("password_hash",))


def test_duplicate_register_raises() -> None:
    a = Admin(title="t", auth=_noop_auth, csrf_enabled=False)
    a.register(ModelResource(model=User))
    with pytest.raises(ValueError, match="already registered"):
        a.register(ModelResource(model=User))
