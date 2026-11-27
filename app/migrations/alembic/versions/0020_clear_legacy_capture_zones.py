"""Clear the legacy ZIRP detection zones; cameras start uncalibrated.

The old per-camera detection zone, detection zoom and capture distance
(``cameras.stream_profiles.FRAMING`` plus the older top-level
``detect_roi`` / ``alpr_detect_roi`` / ``detect_zoom`` keys) were replaced by
per-camera capture calibration (``site_settings`` rows
``capture_calibration:{camera_id}``). This data migration removes the old
values so nothing silently keeps using them. The recognition decode width
(``FRAMING.detect_width``) is kept.

Downgrade cannot restore the removed values; it is a no-op.
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0020_clear_legacy_capture_zones"
down_revision = "0019_capture_evidence_state"
branch_labels = None
depends_on = None

LEGACY_TOP_LEVEL = ("detect_roi", "alpr_detect_roi", "detect_zoom", "capture_plate_width")


def cleaned(profiles):
    """Return the profiles without legacy zone keys, or None when nothing changes."""
    if isinstance(profiles, str):
        try:
            profiles = json.loads(profiles)
        except ValueError:
            return None
    if not isinstance(profiles, dict):
        return None
    out = dict(profiles)
    changed = False
    for key in LEGACY_TOP_LEVEL:
        if key in out:
            out.pop(key)
            changed = True
    for key in ("FRAMING", "framing"):
        framing = out.get(key)
        if isinstance(framing, dict):
            keep = {"detect_width": framing["detect_width"]} if framing.get("detect_width") else {}
            if keep != framing:
                changed = True
                if keep and key == "FRAMING":
                    out[key] = keep
                else:
                    out.pop(key)
                    if keep:
                        out["FRAMING"] = keep
    return out if changed else None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cameras" not in inspector.get_table_names():
        return
    if "stream_profiles" not in {column["name"] for column in inspector.get_columns("cameras")}:
        return                      # nothing saved, so no old zones to clear
    cameras = sa.table("cameras", sa.column("id", sa.Integer), sa.column("stream_profiles", sa.JSON))
    rows = bind.execute(sa.select(cameras.c.id, cameras.c.stream_profiles)).fetchall()
    for camera_id, profiles in rows:
        new = cleaned(profiles)
        if new is not None:
            bind.execute(cameras.update().where(cameras.c.id == camera_id).values(stream_profiles=new))


def downgrade() -> None:
    pass
