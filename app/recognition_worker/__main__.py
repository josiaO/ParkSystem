"""Module entrypoint for ``python -m app.recognition_worker``."""

from __future__ import annotations

from . import main


if __name__ == "__main__":
    from app.services.runtime import run_service

    raise SystemExit(run_service(main))
