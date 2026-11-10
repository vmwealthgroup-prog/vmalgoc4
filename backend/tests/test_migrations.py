import os, pathlib
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from app.config import get_settings
from app.db import Base

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def migrated_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/mig.db"
    monkeypatch.setenv("DATABASE_URL", url); get_settings.cache_clear()
    yield url
    monkeypatch.undo(); get_settings.cache_clear()


def cfg():
    c = Config(str(ROOT / "alembic.ini")); c.set_main_option("script_location", str(ROOT / "alembic")); return c


def test_upgrade_matches_models_exactly_and_downgrades(migrated_url):
    command.upgrade(cfg(), "head")
    eng = create_engine(migrated_url)
    tables = set(inspect(eng).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)                                  # every model table exists
    with eng.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata) == [], "models changed without a migration: run alembic revision --autogenerate"
    command.downgrade(cfg(), "base")
    assert set(inspect(eng).get_table_names()) - {"alembic_version"} == set()
