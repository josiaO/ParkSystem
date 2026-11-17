"""``python -m app.cli env``: safe edits of the Zirp .env file."""

from __future__ import annotations

import pytest

from app import env_tool


@pytest.fixture()
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# site settings\nSMARTPARK_SITE_NAME=Old\n\n# keep me\nOTHER_TOOL=1\n", encoding="utf-8")
    return path


def test_set_validates_keeps_comments_and_backs_up(env_file):
    assert env_tool.cmd_set(env_file, ["site_name=Rock City Mall", "SMARTPARK_PAYMENTS_RECONCILE_SECONDS=45"]) == 0
    text = env_file.read_text(encoding="utf-8")
    assert 'SMARTPARK_SITE_NAME="Rock City Mall"' in text and "# keep me" in text and "OTHER_TOOL=1" in text
    assert text.index("SMARTPARK_SITE_NAME") < text.index("# keep me")       # updated in place
    assert env_file.with_name(".env.bak").read_text(encoding="utf-8").count("Old") == 1
    assert env_tool.read_env(env_file)["SMARTPARK_SITE_NAME"] == "Rock City Mall"


def test_bad_values_and_unknown_names_change_nothing(env_file):
    before = env_file.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        env_tool.cmd_set(env_file, ["payments_reconcile_seconds=abc"])
    with pytest.raises(KeyError):
        env_tool.cmd_set(env_file, ["clickpesa_base_ulr=http://x"])
    assert env_file.read_text(encoding="utf-8") == before


def test_unset_falls_back_to_default(env_file):
    env_tool.cmd_unset(env_file, ["SITE_NAME"])
    assert "SMARTPARK_SITE_NAME" not in env_tool.read_env(env_file)


def test_mock_payment_preset_is_mock_and_keeps_its_credentials(env_file):
    env_tool.cmd_preset_mock_payments(env_file, lan_ip="192.168.1.240")
    first = env_tool.read_env(env_file)
    assert first["SMARTPARK_PAYMENTS_MOBILE_PROVIDER"] == "clickpesa"
    assert first["SMARTPARK_CLICKPESA_BASE_URL"] == "http://192.168.1.240:9100/third-parties"
    assert first["SMARTPARK_CLICKPESA_CHECKSUM_KEY"].startswith("mock-checksum-")
    env_tool.cmd_preset_mock_payments(env_file, lan_ip="192.168.1.240")
    assert env_tool.read_env(env_file)["SMARTPARK_CLICKPESA_API_KEY"] == first["SMARTPARK_CLICKPESA_API_KEY"]

    from app.config import Settings

    summary = env_tool.payment_summary(Settings(_env_file=str(env_file)))
    assert (summary["mode"], summary["real_money"]) == ("MOCK", False)


def test_secrets_are_masked_but_flags_and_urls_are_not(capsys, env_file):
    env_tool.cmd_set(env_file, ["clickpesa_api_key=super-secret-value-123", "clickpesa_live_enabled=false"])
    out = capsys.readouterr().out
    assert "super-secret-value-123" not in out and "ends ...23" in out
    assert env_tool.mask("flutterwave_allow_live_keys", True) == "True"
    assert env_tool.mask("clickpesa_base_url", "http://x") == "http://x"


def test_template_lists_every_setting_without_secret_defaults(capsys):
    env_tool.cmd_template()
    out = capsys.readouterr().out
    assert "# SMARTPARK_CLICKPESA_BASE_URL=https://api.clickpesa.com/third-parties" in out
    assert out.count("# SMARTPARK_") == len(env_tool.field_names())
