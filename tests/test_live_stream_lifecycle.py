"""Startup cancellation must release the viewer owned by that stream only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.api_main import camera_live


def test_cancelled_live_startup_releases_its_camera_lease():
    acquire = Mock()
    release = Mock()
    with patch("app.api_main._camera_live_spec", return_value=SimpleNamespace(id=2)), \
         patch("app.api_main.acquire_live", acquire), \
         patch("app.api_main.release_live", release), \
         patch("app.api_main.get_state", return_value=SimpleNamespace(jpeg=b"")), \
         patch("app.api_main.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(camera_live(2))
    acquire.assert_called_once()
    release.assert_called_once_with(2)
