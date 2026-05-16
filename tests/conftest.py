"""Shared fixtures: app + in-memory database + User model + Admin."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from hawkapi import HawkAPI
from hawkapi_sqlalchemy import Base, TimestampMixin, init_database
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hawkapi_admin import Admin, ModelResource


class User(Base, TimestampMixin):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")


@pytest.fixture
def app() -> HawkAPI:
    app = HawkAPI(openapi_url=None, docs_url=None, redoc_url=None, scalar_url=None)
    db = init_database(app, url="sqlite+aiosqlite:///:memory:")

    async def _create_schema() -> None:
        engine = db.get("primary").engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_create_schema())
    return app


async def _noop_auth(_request: Any) -> None:
    return None


@pytest.fixture
def admin(app: HawkAPI) -> Admin:
    a = Admin(title="Test Admin", auth=_noop_auth, csrf_enabled=False)
    a.register(ModelResource(model=User, list_search=("email",)))
    a.attach(app)
    return a


# Re-export Any so type checkers don't strip the import.
_ = Any
