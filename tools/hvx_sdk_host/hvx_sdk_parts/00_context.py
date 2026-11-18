from __future__ import annotations

import ctypes

from collections import deque

from contextlib import contextmanager

from io import BytesIO

import os

from pathlib import Path

import queue

import struct

import threading

import hashlib

import logging

import time

import uuid

try:
    # Standard-library-only tracer shared with the 64-bit app. hvx_host.py
    # puts the install root on sys.path; without it tracing is just off.
    from app.core import latency_trace as _latency
except Exception:  # pragma: no cover - exercised only on a stripped install
    _latency = None


class _NullMetrics:
    def observe(self, *args, **kwargs): pass
    def incr(self, *args, **kwargs): pass
    def gauge(self, *args, **kwargs): pass
    def adjust(self, *args, **kwargs): return 0
    def snapshot(self): return {"histograms_ms": {}, "counters": {}, "gauges": {}, "unavailable": True}


HOST_METRICS = _latency.MetricsRegistry() if _latency is not None else _NullMetrics()
# Window for the callback / JPEG frame-rate diagnostics (a rolling rate, not lifetime).
FPS_WINDOW_SECONDS = 60.0


def _trace(stage: str, **fields):
    """Emit one host latency record; never raises."""
    if _latency is None:
        return None
    try:
        return _latency.get_tracer().emit(stage, **fields)
    except Exception:
        return None


def _trace_sample(key) -> bool:
    if _latency is None:
        return False
    try:
        return _latency.get_tracer().sample_frame(key)
    except Exception:
        return False


class HVXSDKError(RuntimeError):
    pass

DC_NO_ERROR = 0

DC_HANDLE_INVALID = 1

DC_CONN_FAIL = 2

DC_CMD_INVALID = 5

DC_PARA_INVALID = 6

DC_REQ_TIMEOUT = 7

DC_NOT_CONN = 12

DC_CONNECT_AUTH = 18

DC_USER_NOT_EXIST = 19

DC_PASSWD_ERROR = 20

HANDLE_INVALID = -1

CONN_STATE_CONNECTED = 0

CONN_STATE_UNKNOW = 0

CONN_STATE_TRYING = 1

CONN_STATE_SUCC = 2

CONN_STATE_DIS = 3

CONN_STATE_CONNECTED_VALUES = frozenset({CONN_STATE_CONNECTED, CONN_STATE_SUCC})

RETURN_CODES = {
    0: "DC_NO_ERROR",
    1: "DC_HANDLE_INVALID",
    2: "DC_CONN_FAIL",
    3: "DC_OBJ_BUSY",
    4: "DC_OBJ_UNEXIST",
    5: "DC_CMD_INVALID",
    6: "DC_PARA_INVALID",
    7: "DC_REQ_TIMEOUT",
    8: "DC_MEMORY_LACK",
    9: "DC_SEND_FAIL",
    10: "DC_RECV_FAIL",
    11: "DC_OPT_FAIL",
    12: "DC_NOT_CONN",
    13: "DC_BEYOND_MAX_CLIENT",
    18: "DC_CONNECT_AUTH",
    19: "DC_USER_NOT_EXIST",
    20: "DC_PASSWD_ERROR",
    -1: "DC_UNDEFINED_ERROR",
    1000: "DC_CONN_PORT_NEGO_FAIL",
    1006: "DC_CONN_SERVER_ERROR",
    1007: "DC_CONN_RESPONSE_CODE_AUTHORITY_LIMIT",
}

CONN_STATES = {
    0: "CONN_STATE_SUCC",
    1: "CONN_STATE_TRYING",
    2: "CONN_STATE_SUCC",
    3: "CONN_STATE_DIS",
}

FUNCTION_LIST_BYTES = 800

FUNCTION_LIST_FLAGS_OFFSET = 4

STREAM_TYPE_FLAGS = (
    (4, 0x20000),
    (3, 0x8000),
    (2, 0x10000),
    (1, 0x200),
)

SDK_CONNECT_SEQUENCE = [
    "Net_Init()",
    "Net_AddCamera(ip)",
    "Net_RegReportMessEx(handle, cb)  # before connect",
    "Net_ConnCameraEx(handle, port=30000, timeout_seconds as unsigned short, user, pass)",
    "Net_ConnCamera(handle, port, timeout_seconds)  # fallback if Ex fails",
    "Net_QueryConnState(handle)  # 0 = connected in this NetSDK build",
    "Net_FuntionListRsp(handle, 800-byte buffer)  # choose stream type from +0x04 flags",
    "Net_RegOffLineClient(handle)",
    "Net_StartVideo(handle, selected stream type, HWND)  # OcxConfig PlaySdk path",
    "Net_ShowPlateRegion(handle, show)  # native plate/stop/prefix overlay",
    "Net_AddPlayWindow(handle, HWND)  # OcxConfig display ordering",
    "Net_SetDrawDataOut(handle, decoded bitmap callback)  # primary decoded-frame delivery",
    "Net_RegImageRecvEx2(handle, cb)  # native plate + JPEG",
    "Net_GetJpgBuffer(handle, ptr, size)  # compatibility delivery if draw callback is unavailable",
]

GATE_STATE_OPEN = 1

GATE_STATE_CLOSE = 2

GATE_STATE_STOP = 3

GPIO_OPEN_CIRCUIT = 0

GPIO_SHORT = 1

REPORT_LPRINFO_EXT = 20

IMAGE_USER_INFO_BYTES = 0x44

EVENT_MEDIA_MAX_BYTES = 64 * 1024 * 1024
