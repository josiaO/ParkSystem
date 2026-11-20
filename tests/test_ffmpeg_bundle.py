from pathlib import Path

from app.services import frame_grab


def test_windows_uses_bundled_decoder_without_path(monkeypatch, tmp_path):
    module = tmp_path / 'app' / 'services' / 'frame_grab.py'
    binary = tmp_path / 'vendor' / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'MZ')
    monkeypatch.setattr(frame_grab, '__file__', str(module))
    monkeypatch.setattr(frame_grab.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(frame_grab.shutil, 'which', lambda _: None)
    assert frame_grab.ffmpeg_bin() == str(binary)


def test_missing_bundle_keeps_path_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(frame_grab, '__file__', str(tmp_path / 'app/services/frame_grab.py'))
    monkeypatch.setattr(frame_grab.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(frame_grab.shutil, 'which', lambda name: 'C:/ffmpeg.exe' if name == 'ffmpeg.exe' else None)
    assert frame_grab.ffmpeg_bin() == 'C:/ffmpeg.exe'


def test_linux_ignores_windows_bundle(monkeypatch, tmp_path):
    module = tmp_path / 'app/services/frame_grab.py'
    binary = tmp_path / 'vendor/ffmpeg/bin/ffmpeg.exe'
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(frame_grab, '__file__', str(module))
    monkeypatch.setattr(frame_grab.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(frame_grab.shutil, 'which', lambda _: '/usr/bin/ffmpeg')
    assert frame_grab.ffmpeg_bin() == '/usr/bin/ffmpeg'


def test_installer_build_refuses_a_payload_without_decoder():
    build = (Path(__file__).resolve().parents[1] / 'packaging/installer/build.ps1').read_text(encoding='utf-8')
    assert 'vendor\\ffmpeg\\bin\\ffmpeg.exe") "FFmpeg' in build
