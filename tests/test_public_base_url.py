"""The site's public base URL feeds every receipt QR code and alert photo link."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Site, SiteSetting
from app.services.site_policy import save_site_policy, site_policy, validate_public_base_url


@pytest.mark.parametrize("value, expected", [
    ("", ""),
    ("  ", ""),
    ("http://192.168.10.240:8760", "http://192.168.10.240:8760"),
    ("http://192.168.10.240:8760/", "http://192.168.10.240:8760"),
    ("https://pay.example.test", "https://pay.example.test"),
    ("https://example.test/zirp", "https://example.test/zirp"),  # reverse-proxy prefix is fine
])
def test_valid_public_base_urls(value, expected):
    assert validate_public_base_url(value) == expected


def test_mistyped_port_is_rejected_with_the_correction():
    with pytest.raises(ValueError) as err:
        validate_public_base_url("http://192.168.10.240/8760")
    assert "http://192.168.10.240:8760" in str(err.value)


@pytest.mark.parametrize("value", [
    "192.168.10.240:8760",               # no scheme
    "ftp://host",
    "http://",
    "http://user:pw@host",
    "http://host/?x=1",
    "http://host:99999",
])
def test_invalid_public_base_urls(value):
    with pytest.raises(ValueError):
        validate_public_base_url(value)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(Site(id=1, name="Site", currency="TZS"))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def test_save_rejects_bad_url_and_keeps_the_old_value(db):
    save_site_policy(db, {"public_base_url": "http://192.168.10.240:8760"})
    with pytest.raises(ValueError):
        save_site_policy(db, {"public_base_url": "http://192.168.10.240/8760"})
    assert site_policy(db)["public_base_url"] == "http://192.168.10.240:8760"


def test_a_stored_bad_value_does_not_block_other_settings(db):
    """Older installs may already hold a malformed URL; saving the timezone must still work."""
    db.add(SiteSetting(key="site", value={"public_base_url": "http://192.168.10.240/8760"}))
    db.commit()
    saved = save_site_policy(db, {"timezone": "Africa/Dar_es_Salaam"})
    assert saved["timezone"] == "Africa/Dar_es_Salaam"
    fixed = save_site_policy(db, {"public_base_url": "http://192.168.10.240:8760"})
    assert fixed["public_base_url"] == "http://192.168.10.240:8760"
