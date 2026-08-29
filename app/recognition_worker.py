"""SmartParkRecognitionWorker — optional FastALPR consumer of DETECT frames.

Default is off. The Site Service camera-event loop remains authoritative until
fastalpr_new_pipeline_enabled is turned on after shadow soak tests.
"""

from __future__ import annotations

import asyncio
import sys
import time


async def _loop() -> None:
    from app.services.flags import flags
    from app.services.media_gateway import gateway
    from app.infrastructure.recognition import recognition_provider_for

    provider = recognition_provider_for("fastalpr")
    last_seq: dict[int, int] = {}
    while True:
        cfg = flags()
        if not cfg.get("fastalpr_new_pipeline_enabled"):
            await asyncio.sleep(2.0)
            continue
        for row in gateway.live_metrics():
            camera_id = int(row.get("camera_id") or 0)
            if not camera_id:
                continue
            sample = gateway.peek_detect(camera_id) or gateway.peek_live(camera_id)
            if sample is None or sample.jpeg[:2] != b"\xff\xd8":
                continue
            if last_seq.get(camera_id) == sample.seq:
                continue
            if sample.age_ms() > 1500:
                gateway.note_ai_sample(camera_id, dropped=True)
                continue
            started = time.monotonic()
            try:
                await provider.process({"jpeg": sample.jpeg, "camera_id": camera_id, "camera_label": f"worker-{camera_id}"})
                gateway.note_ai_sample(camera_id, infer_ms=(time.monotonic() - started) * 1000.0)
                last_seq[camera_id] = sample.seq
            except Exception:
                gateway.note_ai_sample(camera_id, dropped=True)
        await asyncio.sleep(0.2)


def main() -> int:
    from app.services.logging_setup import configure_logging
    from app.services.runtime import acquire_instance_lock, install_crash_hooks, set_process_name

    install_crash_hooks("SmartParkRecognitionWorker")
    configure_logging("recognition-worker")
    set_process_name("SmartParkRecognitionWorker")
    if not acquire_instance_lock("recognition-worker"):
        print("SmartPark Recognition Worker is already running.", file=sys.stderr)
        return 0
    print("Recognition worker idle until fastalpr_new_pipeline_enabled=true. Legacy FastALPR stays in Site Service.")
    asyncio.run(_loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
