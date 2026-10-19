from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_single_lane_defaults_to_local_server():
    settings = Settings(_env_file=None)
    assert settings.node_role == "SERVER"
    assert settings.resolved_database_url.startswith("sqlite")


def test_client_requires_shared_database_assignment_and_evidence(tmp_path):
    config = {"node_role": "CLIENT", "database_url": "postgresql+psycopg://server/parking",
              "recognition_gate_id": 2, "shared_media_dir": tmp_path}
    assert Settings(_env_file=None, **config).media_dir == tmp_path
    for field in ("database_url", "recognition_gate_id", "shared_media_dir"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{**config, field: None})
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**config, "database_url": "sqlite:///shared.db"})


def test_model_warmup_initializes_detector_and_ocr_without_publishing():
    from app.services.alpr import warmup_engine

    engine = Mock()
    with patch("app.services.alpr._load_engine", return_value=engine):
        warmup_engine()
    engine.detector.predict.assert_called_once()
    engine.ocr.predict.assert_called_once()
    assert engine.detector.predict.call_args.args[0].shape == (540, 960, 3)
