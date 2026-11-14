"""Phase 3.4: post-boot recovery checker."""

from __future__ import annotations

from tools import boot_health_check as check


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_passes_once_services_and_health_are_green():
    clock = _Clock()
    answers = iter([0, 0, 200, 503, 200, 200])

    result = check.run(
        base_url="http://127.0.0.1:8760", timeout_seconds=300, poll_seconds=10,
        get_status=lambda url: next(answers),
        get_services=lambda: {"SmartParkSiteService": "RUNNING", "SmartParkMediaService": "RUNNING",
                              "SmartParkRecognitionWorker": "RUNNING", "SmartParkHvxHost": None},
        sleep=clock.sleep, clock=clock,
    )
    assert result["verdict"] == "PASS"
    assert result["seconds_to_green"] == 20
    assert "hvx_host" not in result["checks"]  # HVX host is a logon task here


def test_fails_after_timeout_when_a_service_stays_stopped():
    clock = _Clock()
    result = check.run(
        base_url="http://127.0.0.1:8760", timeout_seconds=60, poll_seconds=15,
        get_status=lambda url: 200,
        get_services=lambda: {"SmartParkSiteService": "RUNNING", "SmartParkRecognitionWorker": "STOPPED",
                              "SmartParkMediaService": None, "SmartParkHvxHost": None},
        sleep=clock.sleep, clock=clock,
    )
    assert result["verdict"] == "FAIL"
    assert result["checks"]["services_running"] is False


def test_hvx_service_must_answer_when_installed():
    result = check.evaluate({"SmartParkSiteService": "RUNNING", "SmartParkHvxHost": "RUNNING"}, 200, 200, 0)
    assert result["ok"] is False and result["checks"]["hvx_host"] is False


def test_no_services_installed_is_a_failure():
    result = check.evaluate({name: None for name in check.SERVICES}, 200, 200, None)
    assert result["ok"] is False
