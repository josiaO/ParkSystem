"""Database startup ordering regressions."""

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Site, Tariff
from app.services.fee_engine import ensure_car1_tariff
from app.services.topology import ensure_default_site


def test_default_site_is_created_before_postgres_style_tariff_foreign_key(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'site.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        assert db.scalar(select(Site).where(Site.id == 1)) is None
        ensure_default_site(db)
        ensure_car1_tariff(db)
        assert db.scalar(select(Tariff).where(Tariff.site_id == 1, Tariff.name == "Car1")) is not None

    engine.dispose()


def test_startup_source_orders_site_before_tariff():
    from pathlib import Path

    source = Path("app/api_main.py").read_text(encoding="utf-8")
    assert source.index("ensure_default_site(db)") < source.index("ensure_car1_tariff(db)")
