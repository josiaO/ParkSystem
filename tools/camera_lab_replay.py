"""Local replay and measurement facility for SmartPark TestingData.

The lab starts a realtime FFmpeg publisher and an isolated MediaMTX instance,
then exercises the production LocalMediaGateway/latest-frame/FastALPR seams.
Recognition results terminate in a dry-run sink: no parking or gate service is
started. Source media is read-only; generated evidence goes to results/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MEDIA_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".ts", ".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = MEDIA_EXTENSIONS - {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_PATH = "test-gate-entry"


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:100] or "item"


def _dump(path: Path, body: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _which(name: str) -> str:
    from shutil import which

    value = which(name)
    if not value:
        raise RuntimeError(f"{name} is required for the camera lab")
    return value


def _percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    return round(ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))], 2)


def _ffprobe(path: Path) -> dict[str, Any]:
    command = [_which("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-show_frames", "-select_streams", "v:0", "-show_entries", "frame=key_frame,best_effort_timestamp_time", "-of", "json", str(path)]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout or "{}")


def _video_row(path: Path) -> dict[str, Any]:
    try:
        probe = _ffprobe(path)
        stream = next((row for row in probe.get("streams", []) if row.get("codec_type") == "video"), {})
        frames = probe.get("frames") or []
        key_times = [float(row["best_effort_timestamp_time"]) for row in frames if int(row.get("key_frame") or 0) == 1 and row.get("best_effort_timestamp_time") is not None]
        gaps = [b - a for a, b in zip(key_times, key_times[1:]) if b >= a]
        fmt = probe.get("format") or {}
        return {
            "filename": str(path), "kind": "video", "size_bytes": path.stat().st_size,
            "duration_seconds": float(fmt.get("duration") or 0), "container": fmt.get("format_name", ""),
            "bitrate_bps": int(float(fmt.get("bit_rate") or stream.get("bit_rate") or 0)),
            "codec": stream.get("codec_name", ""), "profile": stream.get("profile", ""),
            "resolution": {"width": int(stream.get("width") or 0), "height": int(stream.get("height") or 0)},
            "fps": stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "",
            "pixel_format": stream.get("pix_fmt", ""), "has_b_frames": stream.get("has_b_frames"),
            "keyframes": {"count": len(key_times), "first_seconds": key_times[:10], "interval_avg_seconds": round(statistics.mean(gaps), 3) if gaps else None, "interval_max_seconds": round(max(gaps), 3) if gaps else None},
        }
    except Exception as exc:
        return {"filename": str(path), "kind": "video", "size_bytes": path.stat().st_size, "probe_error": f"{type(exc).__name__}: {exc}"}


def _image_row(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"filename": str(path), "kind": "image", "size_bytes": path.stat().st_size}
    try:
        from PIL import Image

        with Image.open(path) as image:
            row.update({"resolution": {"width": image.width, "height": image.height}, "format": image.format or ""})
    except Exception as exc:
        row["probe_error"] = f"{type(exc).__name__}: {exc}"
    return row


def inventory(root: Path) -> dict[str, Any]:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS and not ({"results", "output", "generated"} & set(path.parts)))
    videos = [_video_row(path) for path in files if path.suffix.lower() in VIDEO_EXTENSIONS]
    images = [_image_row(path) for path in files if path.suffix.lower() not in VIDEO_EXTENSIONS]
    return {"root": str(root), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "videos": videos, "images": images, "counts": {"videos": len(videos), "images": len(images)}}


def _inventory_md(body: dict[str, Any]) -> str:
    lines = ["# TestingData inventory", "", f"Root: `{body['root']}`", "", "## Videos", "", "| file | duration | resolution | codec | FPS | bitrate | pixel format | keyframes |", "|---|---:|---|---|---|---:|---|---:|"]
    for row in body["videos"]:
        res, keys = row.get("resolution") or {}, row.get("keyframes") or {}
        lines.append(f"| `{Path(row['filename']).name}` | {row.get('duration_seconds', 0):.3f}s | {res.get('width', 0)}x{res.get('height', 0)} | {row.get('codec', '')} | {row.get('fps', '')} | {row.get('bitrate_bps', 0)} | {row.get('pixel_format', '')} | {keys.get('count', 'n/a')} |")
    lines.extend(["", "## Images", "", "| file | resolution | format |", "|---|---|---|"])
    for row in body["images"]:
        res = row.get("resolution") or {}
        lines.append(f"| `{Path(row['filename']).name}` | {res.get('width', 0)}x{res.get('height', 0)} | {row.get('format', '')} |")
    return "\n".join(lines) + "\n"


def run_inspect(args: argparse.Namespace) -> int:
    root = Path(args.dataset).resolve()
    if not root.is_dir():
        print(f"FAIL: dataset directory not found: {root}")
        return 1
    body = inventory(root)
    output = Path(args.output).resolve() if args.output else root / "results" / "inventory"
    _dump(output / "inventory.json", body)
    (output / "inventory.md").write_text(_inventory_md(body), encoding="utf-8")
    print(f"PASS: {body['counts']['videos']} video(s), {body['counts']['images']} image(s)")
    for row in body["videos"]:
        res = row.get("resolution") or {}
        print(f"  VIDEO {Path(row['filename']).name}: {row.get('duration_seconds', 0):.3f}s {res.get('width', 0)}x{res.get('height', 0)} {row.get('codec', '')} {row.get('fps', '')} bitrate={row.get('bitrate_bps', 0)}")
    for row in body["images"]:
        res = row.get("resolution") or {}
        print(f"  IMAGE {Path(row['filename']).name}: {res.get('width', 0)}x{res.get('height', 0)} {row.get('format', '')}")
    print(f"Reports: {output}")
    return 0


def _truth(dataset: Path) -> dict[str, Any]:
    path = dataset / "ground_truth.json"
    if not path.is_file():
        return {"video": [], "images": {}}
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        return body if isinstance(body, dict) else {"video": [], "images": {}}
    except (OSError, json.JSONDecodeError):
        return {"video": [], "images": {}}


def _label(dataset: Path, image: Path, truth: dict[str, Any]) -> str:
    labels = truth.get("images") or {}
    return str(labels.get(image.name) or labels.get(str(image.relative_to(dataset))) or "UNLABELED")


def _save_bgr(array, path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array[:, :, ::-1]).save(path, quality=95)


def _annotate(source: Path, boxes: list[dict[str, Any]], result: dict[str, Any], path: Path) -> None:
    from PIL import Image, ImageDraw

    with Image.open(source).convert("RGB") as image:
        draw = ImageDraw.Draw(image)
        best = result.get("best") if isinstance(result.get("best"), dict) else {}
        for index, box in enumerate(boxes):
            xy = [int(box["x1"]), int(box["y1"]), int(box["x2"]), int(box["y2"])]
            chosen = isinstance(best.get("bbox"), dict) and best["bbox"].get("x1") == xy[0]
            color = "#22c55e" if chosen else "#f59e0b"
            draw.rectangle(xy, outline=color, width=max(3, image.width // 500))
            text = f"{index + 1} det={float(box.get('confidence') or 0):.2f}"
            if chosen:
                text += f" OCR={best.get('plate_raw') or best.get('plate_normalized') or 'none'}"
            draw.text((xy[0], max(0, xy[1] - 18)), text, fill=color)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, quality=90)


def _one_image(image: Path, dataset: Path, output: Path) -> dict[str, Any]:
    started = time.monotonic()
    row: dict[str, Any] = {"image": str(image), "ground_truth": _label(dataset, image, _truth(dataset)), "status": "NOT TESTED", "failure_class": "", "detector": {}, "ocr": {}, "artifacts": {}}
    try:
        from app.services.alpr import _crop_bgr, _prepare_ocr_crop, decode_alpr_image, locate_plate_boxes, recognize_arrival_bytes

        jpeg = image.read_bytes()
        boxes, detector_meta = locate_plate_boxes(jpeg)
        row["detector"] = {"available": bool(detector_meta.get("available")), "boxes": boxes, "latency_ms": detector_meta.get("detector_ms"), "detail": detector_meta.get("reason") or ""}
        if not detector_meta.get("available"):
            row["failure_class"] = "detector-unavailable"
            return row
        if not boxes:
            row["status"], row["failure_class"] = "WARNING", "detector"
            return row
        bgr = decode_alpr_image(jpeg)
        raw_paths, prepared_paths = [], []
        from types import SimpleNamespace

        for index, box in enumerate(boxes):
            bbox = SimpleNamespace(x1=box["x1"], y1=box["y1"], x2=box["x2"], y2=box["y2"])
            crop, _used = _crop_bgr(bgr, bbox)
            raw = output / "crops" / "raw" / f"{_safe(image.stem)}-{index + 1}.jpg"
            prepared = output / "crops" / "prepared" / f"{_safe(image.stem)}-{index + 1}.jpg"
            _save_bgr(crop, raw)
            _save_bgr(_prepare_ocr_crop(crop), prepared)
            raw_paths.append(str(raw))
            prepared_paths.append(str(prepared))
        result = recognize_arrival_bytes(jpeg, camera_label=f"camera-lab-{image.stem}", save_evidence=False, detected_boxes=boxes)
        best = result.get("best") if isinstance(result.get("best"), dict) else None
        row["ocr"] = {"backend": result.get("backend"), "raw_text": best.get("plate_raw", "") if best else "", "normalized_text": best.get("plate_normalized", "") if best else "", "confidence": best.get("confidence") if best else None, "detail": result.get("detail", ""), "timings": best.get("timings", {}) if best else {}}
        row["latency_ms"] = result.get("latency_ms")
        row["artifacts"] = {"detection": str(output / "detections" / f"{_safe(image.stem)}.jpg"), "raw_crops": raw_paths, "prepared_crops": prepared_paths}
        _annotate(image, boxes, result, Path(row["artifacts"]["detection"]))
        if best:
            label = row["ground_truth"]
            row["status"] = "PASS" if label == "UNLABELED" or best.get("plate_normalized") == label else "FAIL"
            row["failure_class"] = "" if row["status"] == "PASS" else "ocr"
            row["ground_truth_match"] = label != "UNLABELED" and best.get("plate_normalized") == label
        else:
            row["status"], row["failure_class"] = "WARNING", "ocr"
    except Exception as exc:
        row["status"], row["failure_class"] = "NOT TESTED", "runtime"
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["total_wall_ms"] = round((time.monotonic() - started) * 1000, 2)
    return row


def run_test_image(args: argparse.Namespace) -> int:
    dataset = Path(args.dataset).resolve()
    output = Path(args.output).resolve() if args.output else dataset / "results" / "images"
    source = Path(args.image)
    if str(source) in {".", ""}:
        source = dataset
    elif not source.is_absolute() and not source.exists():
        source = dataset / source
    images = sorted(source.rglob("*") if source.is_dir() else [source])
    images = [path for path in images if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and not ({"results", "output", "generated"} & set(path.parts))]
    if not images:
        print("FAIL: no images matched")
        return 1
    rows = [_one_image(path, dataset, output) for path in images]
    counts = {state: sum(row.get("status") == state for row in rows) for state in ("PASS", "WARNING", "FAIL", "NOT TESTED")}
    status = "PASS" if counts["PASS"] else "NOT TESTED"
    body = {"status": status, "images": rows, "counts": counts}
    _dump(output / "image-results.json", body)
    print(f"{status}: {len(rows)} image(s); counts={counts}")
    for row in rows:
        ocr = row.get("ocr") or {}
        print(f"  {Path(row['image']).name}: {row['status']} boxes={len((row.get('detector') or {}).get('boxes') or [])} OCR={ocr.get('normalized_text') or 'none'} latency_ms={row.get('latency_ms')}")
    print(f"Results: {output}")
    return 0 if status in {"PASS", "NOT TESTED"} else 2


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http(url: str, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                return 200 <= response.status < 500
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.1)
    return False


def _wait_path(api_port: int, path_name: str, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{api_port}/v3/paths/list", timeout=0.5) as response:
                body = json.loads(response.read().decode("utf-8"))
            for row in body.get("items", []) if isinstance(body, dict) else []:
                if row.get("name") == path_name and bool(row.get("ready")):
                    return True
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
        time.sleep(0.1)
    return False


@dataclass
class VirtualCamera:
    media_path: Path
    path: str
    rtsp_port: int
    api_port: int
    webrtc_port: int
    workdir: Path
    media_process: subprocess.Popen | None = None
    publisher: subprocess.Popen | None = None
    path_count: int = 1

    @property
    def rtsp_url(self) -> str:
        return f"rtsp://127.0.0.1:{self.rtsp_port}/{self.path}"

    @property
    def whep_url(self) -> str:
        return f"http://127.0.0.1:{self.webrtc_port}/{self.path}/whep"

    def _publisher_command(self, path: str | None = None) -> list[str]:
        return [_which("ffmpeg"), "-hide_banner", "-loglevel", "warning", "-re", "-stream_loop", "-1", "-i", str(self.media_path), "-map", "0:v:0", "-an", "-c:v", "copy", "-rtsp_transport", "tcp", "-muxdelay", "0.1", "-f", "rtsp", f"rtsp://127.0.0.1:{self.rtsp_port}/{path or self.path}"]

    def start(self) -> None:
        mediamtx = Path(os.environ.get("SMARTPARK_MEDIAMTX") or "vendor/mediamtx/mediamtx").resolve()
        if not mediamtx.is_file():
            raise RuntimeError(f"MediaMTX binary not found: {mediamtx}")
        self.workdir.mkdir(parents=True, exist_ok=True)
        config = self.workdir / f"mediamtx-{_safe(self.path)}.yml"
        path_blocks = "".join(f"  {self.path if index == 1 else f'{self.path}-{index}'}:\n    source: publisher\n" for index in range(1, max(1, self.path_count) + 1))
        config.write_text(f"logLevel: warn\nlogDestinations: [stdout]\napi: yes\napiAddress: 127.0.0.1:{self.api_port}\nmetrics: yes\nmetricsAddress: 127.0.0.1:{_free_port()}\nrtsp: yes\nrtspAddress: 127.0.0.1:{self.rtsp_port}\nwebrtc: yes\nwebrtcAddress: 127.0.0.1:{self.webrtc_port}\nwebrtcLocalUDPAddress: 127.0.0.1:{_free_port()}\npaths:\n{path_blocks}", encoding="utf-8")
        self.media_process = subprocess.Popen([str(mediamtx), str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        if not _wait_http(f"http://127.0.0.1:{self.api_port}/v3/paths/list"):
            self.stop()
            raise RuntimeError("MediaMTX control API did not become ready")
        self.publisher = subprocess.Popen(self._publisher_command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not _wait_path(self.api_port, self.path):
            self.stop()
            raise RuntimeError("FFmpeg publisher did not make the MediaMTX path ready")

    def restart_publisher(self) -> None:
        self.stop_publisher()
        self.publisher = subprocess.Popen(self._publisher_command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop_publisher(self) -> None:
        if self.publisher is not None and self.publisher.poll() is None:
            self.publisher.terminate()
            try:
                self.publisher.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.publisher.kill()
        self.publisher = None

    def stop(self) -> None:
        self.stop_publisher()
        if self.media_process is not None and self.media_process.poll() is None:
            self.media_process.terminate()
            try:
                self.media_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.media_process.kill()
        self.media_process = None


def _proc_sample(pid: int | None) -> dict[str, Any]:
    if not pid or os.name == "nt":
        return {"pid": pid, "rss_kb": None, "cpu_seconds": None}
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        rss = next((int(line.split()[1]) for line in status.splitlines() if line.startswith("VmRSS:")), None)
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        cpu = (int(stat[13]) + int(stat[14])) / float(ticks)
        return {"pid": pid, "rss_kb": rss, "cpu_seconds": round(cpu, 3)}
    except (OSError, IndexError, ValueError, KeyError):
        return {"pid": pid, "rss_kb": None, "cpu_seconds": None}


async def _recognize_loop(engine, camera_id: int, stop: asyncio.Event, rows: list[dict[str, Any]], delay_ms: float) -> None:
    from app.services.alpr import recognize_bytes

    last_seq = 0
    while not stop.is_set():
        sample = engine.peek_detect(camera_id) or engine.peek_live(camera_id)
        if sample is None or sample.seq <= last_seq:
            await asyncio.sleep(0.01)
            continue
        last_seq = sample.seq
        started = time.monotonic()
        start_age = sample.age_ms(started)
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)
        result = await asyncio.to_thread(recognize_bytes, sample.jpeg, camera_label=f"camera-lab-{camera_id}", save_evidence=False)
        completed = time.monotonic()
        newest = engine.peek_detect(camera_id) or engine.peek_live(camera_id)
        best = result.get("best") if isinstance(result.get("best"), dict) else {}
        rows.append({"camera_id": camera_id, "frame_seq": sample.seq, "latest_seq_at_complete": newest.seq if newest else None, "frame_seq_lag": (newest.seq - sample.seq) if newest else None, "input_frame_age_ms": start_age, "completed_frame_age_ms": sample.age_ms(completed), "latency_ms": round((completed - started) * 1000, 2), "plate_raw": best.get("plate_raw", ""), "plate_normalized": best.get("plate_normalized", ""), "confidence": best.get("confidence"), "detector_confidence": best.get("detector_confidence"), "timings": best.get("timings", {}), "detail": result.get("detail", "")})


async def _measure(engine, media: VirtualCamera, duration: float, recognition: bool, delay_ms: float, cameras: int) -> dict[str, Any]:
    from app.services.media_gateway import CameraLiveSpec
    from app.infrastructure.media.service import MediaService

    service = MediaService(engine)
    for camera_id in range(1, cameras + 1):
        path = media.path if camera_id == 1 else f"{media.path}-{camera_id}"
        spec = CameraLiveSpec(id=camera_id, ip="127.0.0.1", username="", password="", rtsp_url=f"rtsp://127.0.0.1:{media.rtsp_port}/{path}", sdk_handle=None, need_detect=recognition)
        service.register_camera(camera_id, spec)
        engine.acquire_live(spec)
    stop = asyncio.Event()
    recognition_rows: list[dict[str, Any]] = []
    tasks = [asyncio.create_task(_recognize_loop(engine, camera_id, stop, recognition_rows, delay_ms)) for camera_id in range(1, cameras + 1)] if recognition else []
    health_samples, resources = [], []
    started = time.monotonic()
    try:
        while time.monotonic() - started < duration:
            await asyncio.sleep(0.25)
            health_samples.extend(engine.live_metrics())
            resources.append({"at": time.time(), "self": _proc_sample(os.getpid()), "media": _proc_sample(media.media_process.pid if media.media_process else None), "publisher": _proc_sample(media.publisher.pid if media.publisher else None)})
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        producer_tasks = [row.producer for row in engine._sessions.values() if row.producer is not None]
        engine.stop_all()
        await asyncio.gather(*producer_tasks, return_exceptions=True)
    per_camera = []
    for camera_id in range(1, cameras + 1):
        samples = [row for row in health_samples if int(row.get("camera_id") or 0) == camera_id]
        recs = [row for row in recognition_rows if row["camera_id"] == camera_id]
        ages = [float(row["live_frame_age_ms"]) for row in samples if row.get("live_frame_age_ms") is not None]
        per_camera.append({"camera_id": camera_id, "samples": len(samples), "final_health": samples[-1] if samples else {}, "live_video": {"received_fps": samples[-1].get("live_fps") if samples else None, "frame_age_avg_ms": round(statistics.mean(ages), 2) if ages else None, "frame_age_p95_ms": _percentile(ages, 0.95), "frame_interval_p95_ms": _percentile([row["frame_interval_p95_ms"] for row in samples if row.get("frame_interval_p95_ms") is not None], 0.95), "reconnects": samples[-1].get("reconnects", 0) if samples else None, "frozen": any(bool(row.get("frozen")) for row in samples)}, "recognition": {"attempts": len(recs), "fps": round(len(recs) / max(duration, 0.001), 2) if recognition else None, "input_frame_age_avg_ms": round(statistics.mean([row["input_frame_age_ms"] for row in recs]), 2) if recs else None, "input_frame_age_p95_ms": _percentile([row["input_frame_age_ms"] for row in recs], 0.95), "latency_avg_ms": round(statistics.mean([row["latency_ms"] for row in recs]), 2) if recs else None, "latency_p95_ms": _percentile([row["latency_ms"] for row in recs], 0.95), "max_frame_seq_lag": max([row["frame_seq_lag"] or 0 for row in recs], default=None), "stale_frame_failures": sum(1 for row in recs if float(row["completed_frame_age_ms"]) > 2000)}, "timeline": recs[-200:]})
    healthy = per_camera and all(row["live_video"]["received_fps"] or row["final_health"].get("frames_received", 0) for row in per_camera) and all(not row["live_video"]["frozen"] for row in per_camera)
    return {"status": "PASS" if healthy else "WARNING", "mode": "recognition-on" if recognition else "recognition-off", "duration_seconds": duration, "source": str(media.media_path), "virtual_camera": {"rtsp": media.rtsp_url, "whep": media.whep_url, "timestamp_pacing": "ffmpeg -re", "publisher_codec": "stream-copy"}, "per_camera": per_camera, "resource_usage": {"sample_count": len(resources), "samples": resources, "max_self_rss_kb": max((row["self"]["rss_kb"] or 0 for row in resources), default=None), "max_publisher_rss_kb": max((row["publisher"]["rss_kb"] or 0 for row in resources), default=None)}, "recognition_records": recognition_rows[-1000:]}


def _start_extra_publishers(media: VirtualCamera, count: int) -> list[subprocess.Popen]:
    publishers = []
    for camera_id in range(2, count + 1):
        publishers.append(subprocess.Popen(media._publisher_command(f"{media.path}-{camera_id}"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    return publishers


def _stop_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def _source_path(args: argparse.Namespace) -> tuple[Path, Path]:
    dataset = Path(args.dataset).resolve()
    source = Path(args.video)
    if not source.is_absolute() and not source.exists():
        source = dataset / source
    return dataset, source


def run_test_video(args: argparse.Namespace) -> int:
    dataset, source = _source_path(args)
    if not source.is_file():
        print(f"FAIL: video not found: {source}")
        return 1
    output = Path(args.output).resolve() if args.output else dataset / "results" / "video"
    media = VirtualCamera(source, args.path, args.rtsp_port or _free_port(), args.api_port or _free_port(), args.webrtc_port or _free_port(), output / "runtime")
    media.path_count = max(1, int(args.cameras))
    extras: list[subprocess.Popen] = []
    try:
        media.start()
        if args.cameras > 1:
            extras = _start_extra_publishers(media, args.cameras)
            for camera_id in range(2, int(args.cameras) + 1):
                _wait_path(media.api_port, f"{media.path}-{camera_id}")
        from app.services.media_gateway import LocalMediaGateway

        body = asyncio.run(_measure(LocalMediaGateway(), media, float(args.duration), bool(args.recognition), float(args.recognition_delay_ms), int(args.cameras)))
        body["source_inventory"] = _video_row(source)
        body["failure_test"] = args.failure_test or ""
        _dump(output / f"video-{('on' if args.recognition else 'off')}-{args.cameras}c.json", body)
        print(f"{body['status']}: {args.duration:g}s {body['mode']} {args.cameras} camera(s)")
        for row in body["per_camera"]:
            print(f"  camera {row['camera_id']}: fps={row['live_video']['received_fps']} age_p95_ms={row['live_video']['frame_age_p95_ms']} reconnects={row['live_video']['reconnects']} recognition_attempts={row['recognition']['attempts']}")
        print(f"RTSP: {media.rtsp_url}\nWHEP: {media.whep_url}\nResults: {output}")
        return 0 if body["status"] == "PASS" else 2
    finally:
        _stop_processes(extras)
        media.stop()


def run_serve(args: argparse.Namespace) -> int:
    dataset, source = _source_path(args)
    output = Path(args.output).resolve() if args.output else dataset / "results" / "serve"
    media = VirtualCamera(source, args.path, args.rtsp_port, args.api_port, args.webrtc_port, output)
    try:
        media.start()
        print(f"PASS: realtime virtual camera serving {source}\nRTSP: {media.rtsp_url}\nWHEP: {media.whep_url}")
        if args.duration:
            time.sleep(float(args.duration))
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        media.stop()
    return 0


def run_multi_camera(args: argparse.Namespace) -> int:
    results = []
    for count in (1, 2, 4):
        child = argparse.Namespace(**vars(args))
        child.cameras = count
        code = run_test_video(child)
        results.append({"cameras": count, "exit_code": code})
    output = Path(args.output).resolve() if args.output else Path(args.dataset).resolve() / "results" / "multi-camera"
    _dump(output / "multi-camera.json", {"status": "PASS" if all(row["exit_code"] == 0 for row in results) else "WARNING", "results": results})
    return 0 if all(row["exit_code"] == 0 for row in results) else 2


def run_failure_test(args: argparse.Namespace) -> int:
    dataset, source = _source_path(args)
    output = Path(args.output).resolve() if args.output else dataset / "results" / "failure"
    media = VirtualCamera(source, args.path, args.rtsp_port or _free_port(), args.api_port or _free_port(), args.webrtc_port or _free_port(), output / "runtime")
    try:
        media.start()
        if args.scenario == "recognition-slowdown":
            args.recognition, args.recognition_delay_ms = True, max(float(args.recognition_delay_ms), 500.0)
            body = asyncio.run(_measure(__import__("app.services.media_gateway", fromlist=["LocalMediaGateway"]).LocalMediaGateway(), media, float(args.duration), True, args.recognition_delay_ms, 1))
        else:
            async def interrupted():
                task = asyncio.create_task(_measure(__import__("app.services.media_gateway", fromlist=["LocalMediaGateway"]).LocalMediaGateway(), media, float(args.duration), bool(args.recognition), float(args.recognition_delay_ms), 1))
                await asyncio.sleep(float(args.duration) / 2)
                media.stop_publisher()
                await asyncio.sleep(float(args.interruption_seconds))
                media.restart_publisher()
                return await task
            body = asyncio.run(interrupted())
        body["scenario"] = args.scenario
        body["status"] = "WARNING"
        _dump(output / f"{_safe(args.scenario)}.json", body)
        print(f"WARNING: recorded failure scenario {args.scenario}; inspect reconnect and stale-frame fields")
        return 2
    finally:
        media.stop()


def run_report(args: argparse.Namespace) -> int:
    results = Path(args.results).resolve()
    rows = []
    for path in sorted(results.rglob("*.json")):
        if path.name == "report.json":
            continue
        try:
            rows.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    observed_statuses = {str(row.get("status") or "") for _, row in rows}
    overall_status = "NOT TESTED" if not rows else "FAIL" if "FAIL" in observed_statuses else "WARNING" if "WARNING" in observed_statuses else "PASS"
    body = {"status": overall_status, "result_files": [str(path) for path, _ in rows], "categories": {"environment": {"python": sys.version, "platform": sys.platform}, "source_media": [], "live_video": [], "recognition": [], "per_camera": [], "failures": [], "resource_usage": []}}
    for path, row in rows:
        if "scenario" in row:
            body["categories"]["failures"].append({"file": str(path), "scenario": row.get("scenario"), "status": row.get("status")})
        elif "videos" in row or "images" in row:
            body["categories"]["source_media"].append(row)
        elif "per_camera" in row:
            body["categories"]["live_video"].append({"file": str(path), "status": row.get("status"), "mode": row.get("mode"), "duration_seconds": row.get("duration_seconds")})
            body["categories"]["per_camera"].extend(row.get("per_camera") or [])
            body["categories"]["recognition"].extend(row.get("recognition_records") or [])
        if "resource_usage" in row:
            body["categories"]["resource_usage"].append({"file": str(path), "resource_usage": row["resource_usage"]})
    output = Path(args.output).resolve() if args.output else results / "report.json"
    _dump(output, body)
    markdown = output.with_suffix(".md")
    lines = ["# SmartPark Camera Lab report", "", f"Overall: **{body['status']}**", "", "## Categories", ""]
    for category, values in body["categories"].items():
        lines.append(f"- {category}: {len(values)} record(s)")
    lines.extend(["", "Local dry-run only. This report does not claim vendor-HVX equivalence or labeled accuracy where ground truth is absent.", ""])
    markdown.write_text("\n".join(lines), encoding="utf-8")
    print(f"{body['status']}: {len(rows)} JSON result file(s)\nReport: {output}")
    return 0 if rows else 2


def run_ground_truth(args: argparse.Namespace) -> int:
    path = Path(args.dataset).resolve() / "ground_truth.json"
    if path.exists() and not args.force:
        print(f"WARNING: {path} already exists; use --force only to replace it")
        return 2
    _dump(path, {"video": [], "images": {}, "notes": "Fill labels from human review; do not copy OCR predictions as truth."})
    print(f"PASS: editable ground-truth template created at {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SmartPark recorded-footage camera lab")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="inventory source videos and images")
    inspect.add_argument("dataset", nargs="?", default="TestingData")
    inspect.add_argument("--output")
    inspect.set_defaults(func=run_inspect)

    image = sub.add_parser("test-image", help="run existing detector/crop/OCR on still images")
    image.add_argument("image", nargs="?", default=".")
    image.add_argument("--dataset", default="TestingData")
    image.add_argument("--output")
    image.set_defaults(func=run_test_image)

    def add_video(command):
        command.add_argument("video", nargs="?", default="Video Project.mp4")
        command.add_argument("--dataset", default="TestingData")
        command.add_argument("--duration", type=float, default=10.0)
        command.add_argument("--output")
        command.add_argument("--path", default=DEFAULT_PATH)
        command.add_argument("--rtsp-port", type=int, default=0)
        command.add_argument("--api-port", type=int, default=0)
        command.add_argument("--webrtc-port", type=int, default=0)
        command.add_argument("--recognition", action="store_true")
        command.add_argument("--recognition-delay-ms", type=float, default=0.0)
        command.add_argument("--cameras", type=int, default=1)
        command.add_argument("--failure-test", default="")

    video = sub.add_parser("test-video", help="replay through MediaMTX and measure live video")
    add_video(video)
    video.set_defaults(func=run_test_video)

    benchmark = sub.add_parser("benchmark", help="run a recognition-enabled video benchmark")
    add_video(benchmark)
    benchmark.set_defaults(func=run_test_video, recognition=True)

    serve = sub.add_parser("serve", help="serve a realtime looping RTSP virtual camera")
    serve.add_argument("video", nargs="?", default="Video Project.mp4")
    serve.add_argument("--dataset", default="TestingData")
    serve.add_argument("--duration", type=float, default=0.0)
    serve.add_argument("--output")
    serve.add_argument("--path", default=DEFAULT_PATH)
    serve.add_argument("--rtsp-port", type=int, default=8554)
    serve.add_argument("--api-port", type=int, default=9997)
    serve.add_argument("--webrtc-port", type=int, default=8889)
    serve.set_defaults(func=run_serve)

    multi = sub.add_parser("multi-camera", help="run one, two, and four virtual cameras")
    add_video(multi)
    multi.set_defaults(func=run_multi_camera)

    failure = sub.add_parser("failure-test", help="record controlled interruption or slowdown behavior")
    add_video(failure)
    failure.add_argument("--scenario", choices=("stream-interruption", "producer-restart", "recognition-slowdown"), default="stream-interruption")
    failure.add_argument("--interruption-seconds", type=float, default=3.0)
    failure.set_defaults(func=run_failure_test)

    report = sub.add_parser("report", help="combine local JSON results into a summary")
    report.add_argument("results", nargs="?", default="TestingData/results")
    report.add_argument("--output")
    report.set_defaults(func=run_report)

    truth = sub.add_parser("ground-truth", help="create an editable local annotation template")
    truth.add_argument("--dataset", default="TestingData")
    truth.add_argument("--force", action="store_true")
    truth.set_defaults(func=run_ground_truth)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
