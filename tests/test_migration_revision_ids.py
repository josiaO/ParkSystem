"""Alembic revision ids must fit alembic_version.version_num (VARCHAR(32)).

SQLite ignores VARCHAR lengths, so a too-long id passes every SQLite test and
only fails on the PostgreSQL production database, where the Site Service then
cannot start (seen with "0021_vehicle_authorization_groups", 33 characters).
"""

from __future__ import annotations

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "app" / "migrations" / "alembic" / "versions"


def test_every_revision_id_fits_the_postgresql_version_column():
    ids = {}
    for path in sorted(VERSIONS.glob("*.py")):
        match = re.search(r'^revision\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.M)
        assert match, f"{path.name} has no revision id"
        ids[path.name] = match.group(1)
    too_long = {name: rid for name, rid in ids.items() if len(rid) > 32}
    assert not too_long, f"revision ids longer than 32 characters: {too_long}"


def test_revision_chain_is_linear():
    revs, downs = set(), []
    for path in VERSIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        revs.add(re.search(r'^revision\s*=\s*"([^"]+)"', text, re.M).group(1))
        down = re.search(r'^down_revision\s*=\s*"([^"]+)"', text, re.M)
        if down:
            downs.append(down.group(1))
    assert len(downs) == len(set(downs)), "two migrations share a parent (branch)"
    assert set(downs) <= revs, "a down_revision points at a missing migration"
