"""Native plate recovery must not restart live video or require an open UI."""
import threading
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.hvx_sdk_host.hvx_sdk import HVXSDK


class NativeReconnectTests(unittest.TestCase):
    def make_sdk(self):
        sdk = HVXSDK.__new__(HVXSDK)
        sdk._lock = threading.Lock()
        sdk._recognition_sessions = {7: {
            'lock': threading.Lock(), 'closed': False, 'state': 2,
            'pending': False, 'image_recv_rc': 0, 'next_check': 0.,
            'retry_at': 0., 'backoff': 1., 'rearms': 0, 'last_error': '',
        }}
        sdk._pending_events = {7: deque([{'plate': 'ABC123'}])}
        sdk._last_capture = {}
        sdk._report_cbs = {}
        sdk._image_cbs = {}
        sdk._FGetReportCBEx = lambda fn: fn
        sdk._FGetImageCbEx = lambda fn: fn
        sdk.dll = SimpleNamespace(
            Net_QueryConnState=Mock(return_value=2),
            Net_RegReportMessEx=Mock(return_value=0),
            Net_RegImageRecvEx=Mock(return_value=0),
            Net_StartVideo=Mock(), Net_ImageSnap=Mock(), Net_GateSetup=Mock(),
        )
        return sdk

    def test_background_events_rearm_after_disconnect_without_restarting_video(self):
        sdk = self.make_sdk()
        sdk.dll.Net_QueryConnState.side_effect = [3, 2, 2]
        with patch('tools.hvx_sdk_host.hvx_sdk.time.monotonic', side_effect=[10., 11., 12.]):
            self.assertEqual(sdk.drain_events(7), [{'plate': 'ABC123'}])
            sdk.drain_events(7)
            sdk.drain_events(7)
        sdk.dll.Net_RegImageRecvEx.assert_called_once()
        sdk.dll.Net_RegReportMessEx.assert_called_once()
        sdk.dll.Net_StartVideo.assert_not_called()
        sdk.dll.Net_ImageSnap.assert_not_called()
        sdk.dll.Net_GateSetup.assert_not_called()
        self.assertEqual(sdk._recognition_sessions[7]['rearms'], 1)

    def test_failed_registration_retries_with_backoff(self):
        sdk = self.make_sdk()
        sdk._recognition_sessions[7]['pending'] = True
        sdk.dll.Net_RegImageRecvEx.side_effect = [7, 7, 0]
        with patch('tools.hvx_sdk_host.hvx_sdk.time.monotonic') as now:
            for stamp in [10., 11., 12.]:
                now.return_value = stamp
                sdk.drain_events(7)
            self.assertEqual(sdk.dll.Net_RegImageRecvEx.call_count, 2)
            now.return_value = 13.
            sdk.drain_events(7)
        self.assertFalse(sdk._recognition_sessions[7]['pending'])
        self.assertEqual(sdk.dll.Net_RegImageRecvEx.call_count, 3)

    def test_polling_is_bounded_and_does_not_wait_for_plate(self):
        sdk = self.make_sdk()
        with patch('tools.hvx_sdk_host.hvx_sdk.time.monotonic', return_value=10.):
            for _ in range(100):
                sdk.drain_events(7)
        sdk.dll.Net_QueryConnState.assert_called_once()
        sdk.dll.Net_RegImageRecvEx.assert_not_called()

    def test_callback_objects_survive_reregistration(self):
        sdk = self.make_sdk()
        sdk._register_image(7)
        sdk._register_report(7)
        image = sdk._image_cbs[7]
        report = sdk._report_cbs[7]
        sdk._register_image(7)
        sdk._register_report(7)
        self.assertIs(sdk._image_cbs[7], image)
        self.assertIs(sdk._report_cbs[7], report)

    def test_query_failure_does_not_lose_queued_events(self):
        sdk = self.make_sdk()
        sdk.dll.Net_QueryConnState.side_effect = RuntimeError('offline')
        self.assertEqual(sdk.drain_events(7), [{'plate': 'ABC123'}])
        self.assertTrue(sdk._recognition_sessions[7]['pending'])

    def test_recognition_failure_is_visible_even_when_connection_is_up(self):
        sdk = self.make_sdk()
        sdk._recognition_sessions[7]['pending'] = True
        sdk.dll.Net_RegImageRecvEx.return_value = 7
        health = sdk.state(7)
        self.assertEqual(health['state'], 2)
        self.assertFalse(health['recognition']['ready'])
        self.assertTrue(health['recognition']['retry_pending'])
