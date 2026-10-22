"""Live camera pictures must not inflate their own layout."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QGridLayout, QScrollArea, QWidget

from app.desktop.main import CameraLivePane


def _jpeg(width=1280, height=720) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(0x203040)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buf, "JPEG")
    return bytes(buf.data())


def test_camera_view_stays_the_same_size_across_frames():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet("QLabel#video { background:#070B10; border-radius:10px; padding:8px; }")
    host = QWidget()
    grid = QGridLayout(host)
    left = CameraLivePane("Left")
    right = CameraLivePane("Right")
    grid.addWidget(left, 0, 0)
    grid.addWidget(right, 0, 1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(host)
    scroll.resize(900, 600)
    scroll.show()
    app.processEvents()

    jpeg = _jpeg()
    sizes = []
    for _ in range(12):
        assert left._set_pixmap(left.video, jpeg)
        assert right._set_pixmap(right.video, jpeg)
        app.processEvents()
        sizes.append((left.video.width(), left.video.height(), right.video.width(), right.video.height()))

    assert len(set(sizes)) == 1, sizes
    width, height, _, _ = sizes[0]
    assert width > 200 and height > 180
    # The pixmap fits inside the padded label, so it cannot request a bigger box.
    pix = left.video.image_rect()
    assert pix.width() <= left.video.contentsRect().width()
    assert pix.height() <= left.video.contentsRect().height()
    scroll.close()


def test_expired_server_evidence_is_not_held_by_desktop():
    from unittest.mock import patch

    app = QApplication.instance() or QApplication([])
    pane = CameraLivePane("Lane 2")
    pane._held_car = {"plate": "T319DCU", "crop_url": "/media/crops/old.jpg"}
    with patch.object(pane, "_load_evidence") as request:
        pane._show_alpr({"vehicle_present": False, "last_car": None, "clear_last_car": True})
    assert "T319DCU" not in pane.plate.text()
    assert all(call.args[1] is None for call in request.call_args_list)
    pane.shutdown()
