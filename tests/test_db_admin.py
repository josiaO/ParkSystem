"""Factory reset of the site database: guards and table drop."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect

from app import db_admin
from app.db import Base


def facts(**overrides):
    base = {"configured": True, "role": "SITE_SERVER", "engine": "POSTGRESQL", "postgres": True,
            "database": "smartpark", "host": "10.0.0.5", "media_dir": "x", "shared_media": False,
            "local_photos_referenced_externally": True, "may_reset_database": True}
    return {**base, **overrides}


def test_drop_all_tables_empties_the_database(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'site.db').as_posix()}")
    Base.metadata.create_all(engine)
    assert len(inspect(engine).get_table_names()) > 10
    dropped = db_admin.drop_all_tables(engine)
    assert dropped and inspect(engine).get_table_names() == []


@pytest.mark.parametrize("override, words", [
    ({"role": "EDGE_NODE", "may_reset_database": False}, "whole site's data"),
    ({"role": "OPERATOR_CLIENT", "may_reset_database": False}, "whole site's data"),
    ({"engine": "SQLITE", "postgres": False, "may_reset_database": False}, "does not use PostgreSQL"),
])
def test_reset_refuses_where_the_database_is_not_this_pcs_to_reset(override, words):
    with patch.object(db_admin, "status", return_value=facts(**override)), \
         patch.object(db_admin, "drop_all_tables") as drop:
        with pytest.raises(PermissionError, match=words):
            db_admin.reset("smartpark")
        drop.assert_not_called()


def test_reset_needs_the_exact_database_name():
    with patch.object(db_admin, "status", return_value=facts()), patch.object(db_admin, "drop_all_tables") as drop:
        for wrong in ("", "SMARTPARK", "smartpark ", "yes"):
            with pytest.raises(PermissionError, match="exactly"):
                db_admin.reset(wrong)
        drop.assert_not_called()
