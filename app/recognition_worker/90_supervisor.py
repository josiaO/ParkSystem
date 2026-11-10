from __future__ import annotations

def main() -> int:
    from app.services.logging_setup import configure_logging
    from app.services.runtime import acquire_instance_lock, install_crash_hooks, set_process_name

    install_crash_hooks("SmartParkRecognitionWorker")
    configure_logging("recognition-worker")
    set_process_name("SmartParkRecognitionWorker")
    if not acquire_instance_lock("recognition-worker"):
        print("SmartPark Recognition Worker is already running.", file=sys.stderr)
        return 0
    if not _configure_worker_runtime():
        return 2
    print("Recognition worker reads MediaMTX cam{id}_detect when fastalpr_new_pipeline_enabled=true.")
    asyncio.run(_loop())
    return 0
