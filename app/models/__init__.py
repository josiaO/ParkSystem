"""SmartPark ORM models.

Ordinary modules (no exec() loader since Phase 6): ``base`` holds shared
types and enums; the others hold the tables by area. Everything is
re-exported here so ``from app.models import ParkingSession`` keeps working.
"""

from __future__ import annotations

from .base import *  # noqa: F401,F403
from .identity import *  # noqa: F401,F403
from .topology import *  # noqa: F401,F403
from .audit_billing import *  # noqa: F401,F403
from .parking import *  # noqa: F401,F403
from .access_capture import *  # noqa: F401,F403
from .alerts import *  # noqa: F401,F403
