from __future__ import annotations

def bundled_alpr_dir() -> Path | None:
    """USB/install folder: SMARTPARK_HOME/models/fastalpr, else repo models/fastalpr."""
    candidates = []
    home = os.environ.get("SMARTPARK_HOME")
    if home:
        candidates.append(Path(home) / "models" / "fastalpr")
    extra = os.environ.get("SMARTPARK_ALPR_MODEL_DIR")
    if extra:
        candidates.append(Path(extra))
    candidates.append(Path(__file__).resolve().parents[2] / "models" / "fastalpr")
    for path in candidates:
        if (path / DETECTOR_ONNX).is_file() or (path / "detector" / DETECTOR_ONNX).is_file():
            return path
    return None

def _copy_if_needed(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size == src.stat().st_size and dest.stat().st_mtime >= src.stat().st_mtime:
        return True
    dest.write_bytes(src.read_bytes())
    return dest.is_file()

def ensure_alpr_model_cache() -> dict:
    """Copy bundled ONNX files into FastALPR's user cache so Windows has no internet download."""
    src = bundled_alpr_dir()
    detector_src = None
    ocr_src = None
    cfg_src = None
    if src is not None:
        detector_src = next((p for p in (src / DETECTOR_ONNX, src / "detector" / DETECTOR_ONNX) if p.is_file()), None)
        ocr_src = next((p for p in (src / OCR_ONNX, src / "ocr" / OCR_ONNX) if p.is_file()), None)
        cfg_src = next((p for p in (src / OCR_CONFIG, src / "ocr" / OCR_CONFIG) if p.is_file()), None)
    # A scheduled Windows service may run as a different account from the
    # desktop. Keep the model cache in the installation's shared data folder
    # when the launcher provides one, instead of splitting models across user
    # profiles and reporting detector-unavailable on the service account.
    cache_home = Path(os.environ.get("SMARTPARK_ALPR_CACHE_DIR") or (Path.home() / ".cache"))
    detector_dest = cache_home / "open-image-models" / DETECTOR_MODEL / DETECTOR_ONNX
    ocr_dest = cache_home / "fast-plate-ocr" / OCR_MODEL / OCR_ONNX
    cfg_dest = cache_home / "fast-plate-ocr" / OCR_MODEL / OCR_CONFIG
    ok_det = _copy_if_needed(detector_src, detector_dest) if detector_src else detector_dest.is_file()
    ok_ocr = _copy_if_needed(ocr_src, ocr_dest) if ocr_src else ocr_dest.is_file()
    ok_cfg = _copy_if_needed(cfg_src, cfg_dest) if cfg_src else cfg_dest.is_file()
    return {
        "bundled_dir": str(src) if src else None,
        "detector": ok_det,
        "ocr": ok_ocr and ok_cfg,
        "detector_path": str(detector_dest) if ok_det else None,
        "ocr_path": str(ocr_dest) if ok_ocr else None,
        "ocr_config_path": str(cfg_dest) if ok_cfg else None,
    }

def prepare_native_runtime() -> None:
    """Make bundled Windows native dependencies visible before importing ORT.

    Scheduled tasks do not go through the desktop launcher's DLL setup. Python
    3.8+ therefore needs the ONNX Runtime ``capi`` directory registered
    explicitly, otherwise Windows can find the extension but fail while
    initializing one of its dependent DLLs.
    """
    global _native_runtime_prepared
    if _native_runtime_prepared or os.name != "nt":
        return
    _native_runtime_prepared = True
    install_root = Path(os.environ.get("SMARTPARK_HOME") or Path(sys.executable).resolve().parent)
    python_root = Path(sys.prefix).resolve()
    site_packages = python_root / "Lib" / "site-packages"
    candidates = (
        python_root,
        install_root / "python64",
        site_packages / "onnxruntime" / "capi",
        install_root / "python64" / "Lib" / "site-packages" / "onnxruntime" / "capi",
        site_packages / "numpy.libs",
        install_root / "python64" / "Lib" / "site-packages" / "numpy.libs",
        install_root / "vendor",
    )
    add_dll_directory = getattr(os, "add_dll_directory", None)
    for folder in candidates:
        if not folder.is_dir():
            continue
        text = str(folder)
        path_parts = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
        if text not in path_parts:
            os.environ["PATH"] = text + os.pathsep + os.environ.get("PATH", "")
        if add_dll_directory is not None:
            try:
                _dll_directory_handles.append(add_dll_directory(text))
            except OSError:
                pass

def fastalpr_installed() -> bool:
    global _fastalpr_error
    prepare_native_runtime()
    if _fastalpr_error:
        return False
    try:
        import fast_alpr  # noqa: F401

        _fastalpr_error = ""
        return True
    except Exception as exc:
        # Native DLL/ONNX Runtime load failures are not always ImportError.
        # Keep the actionable part visible to the technician and live pane.
        _fastalpr_error = f"{type(exc).__name__}: {str(exc)[:240]}"
        return False

def _remember_engine_error(exc: BaseException) -> str:
    global _engine_error
    from app.services.redaction import redact_text

    _engine_error = redact_text(f"{type(exc).__name__}: {str(exc)}")[:320]
    return _engine_error

def _availability_detail(models: dict | None = None) -> str:
    if _fastalpr_error:
        return f"FastALPR could not load: {_fastalpr_error}"
    if _engine_error:
        return f"FastALPR model startup failed: {_engine_error}"
    models = models or {}
    missing = []
    if not models.get("detector"):
        missing.append(DETECTOR_ONNX)
    if not models.get("ocr"):
        missing.append(f"{OCR_ONNX} and {OCR_CONFIG}")
    if missing:
        return "FastALPR model files are missing: " + ", ".join(missing)
    return "FastALPR detector is not available. Check the Site Service log and /alpr/status."

def _configure_model_cache(models: dict) -> None:
    """Point the third-party model hubs at the offline SmartPark model cache."""
    detector_path = models.get("detector_path")
    ocr_path = models.get("ocr_path")
    try:
        if detector_path:
            from open_image_models.detection.core import hub as detector_hub

            detector_hub.MODEL_CACHE_DIR = Path(detector_path).parent.parent
        if ocr_path:
            from fast_plate_ocr.inference import hub as ocr_hub

            ocr_hub.MODEL_CACHE_DIR = Path(ocr_path).parent.parent
    except Exception as exc:
        _remember_engine_error(exc)

def status() -> dict:
    installed = fastalpr_installed()
    models = ensure_alpr_model_cache()
    ready = bool(installed and models.get("detector") and models.get("ocr"))
    contract = camera_contract()
    return {
        "backend": "fastalpr" if installed else "none",
        "installed": installed,
        "loaded": _engine is not None,
        "available": ready,
        "ready": ready,
        "models": models,
        "country": settings.alpr_country or None,
        "csf": settings.alpr_csf,
        "native_engine": "qy_Net_RegImageRecvEx",
        "local_engine": "fastalpr" if installed else "none",
        "camera": contract,
        "detect": detect_coverage(
            fps=float(getattr(settings, "detect_fps", 5.0) or 5.0),
            dwell_seconds=1.0,
            min_frames=2,
        ),
        "engine_id": "fastalpr",
        "detail": (
            "The camera snaps the JPEG. FastALPR detects the plate, crops it with padding, "
            "then reads only that crop. Country profile: "
            f"{_country_name() or 'neutral'}. "
            "Replace the ONNX pack to retrain, or register another PlateEngine to change libraries."
            if ready
            else _availability_detail(models)
        ),
    }

def _load_engine():
    global _engine, _engine_error
    with _lock:
        if _engine is None:
            try:
                prepare_native_runtime()
                from fast_alpr import ALPR

                models = ensure_alpr_model_cache()
                if not models.get("detector") or not models.get("ocr"):
                    raise FileNotFoundError(_availability_detail(models))
                _configure_model_cache(models)
                kwargs = {
                    "detector_model": DETECTOR_MODEL,
                    "detector_conf_thresh": float(getattr(settings, "alpr_detector_confidence", 0.26) or 0.26),
                    "ocr_device": "cpu",
                    "detector_providers": ["CPUExecutionProvider"],
                    "ocr_providers": ["CPUExecutionProvider"],
                }
                import onnxruntime as ort

                options = ort.SessionOptions()
                workers = max(1, int(settings.recognition_max_concurrency))
                automatic = max(1, min(2, ((os.cpu_count() or 2) - 1) // workers))
                options.intra_op_num_threads = settings.recognition_model_threads or automatic
                options.inter_op_num_threads = 1
                options.add_session_config_entry("session.intra_op.allow_spinning", "0")
                options.add_session_config_entry("session.inter_op.allow_spinning", "0")
                kwargs["detector_sess_options"] = options
                kwargs["ocr_sess_options"] = options
                if models.get("ocr_path") and models.get("ocr_config_path"):
                    kwargs["ocr_model"] = None
                    kwargs["ocr_model_path"] = models["ocr_path"]
                    kwargs["ocr_config_path"] = models["ocr_config_path"]
                else:
                    kwargs["ocr_model"] = OCR_MODEL
                _engine = ALPR(**kwargs)
                _engine_error = ""
            except Exception as exc:
                _remember_engine_error(exc)
                raise
        return _engine

def warmup_engine() -> None:
    """Initialize both models before accepting live recognition frames."""
    import numpy as np

    engine = _load_engine()
    engine.detector.predict(np.zeros((540, 960, 3), dtype=np.uint8))
    engine.ocr.predict(_prepare_ocr_crop(np.zeros((80, 320, 3), dtype=np.uint8)))

def unload_engine() -> None:
    """Drop the loaded reader so the next frame picks up a new model pack."""
    global _engine, _warm_engine
    with _lock:
        _engine = None
        _warm_engine = None

def warmup() -> dict:
    """Initialize and exercise both models without publishing or saving evidence."""
    global _warm_engine
    import numpy as np

    started = time.monotonic()
    engine = _load_engine()
    if _warm_engine is engine:
        return {"ready": True, "cached": True, "warmup_ms": 0.0}
    engine.detector.predict(np.zeros((360, 640, 3), dtype=np.uint8))
    engine.ocr.predict(np.zeros((64, 320, 3), dtype=np.uint8))
    _warm_engine = engine
    return {"ready": True, "warmup_ms": round((time.monotonic() - started) * 1000, 1)}
