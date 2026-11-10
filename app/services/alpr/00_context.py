from __future__ import annotations

"""Local FastALPR boundary.

A plate event is the only thing the rest of SmartPark should see. This module
never invents plates: if FastALPR is missing, it reports that instead of
substituting a simulated reading on a real camera frame.
"""

import os

import re

import statistics

import sys

import threading

import time

import uuid

import hashlib

from dataclasses import dataclass, field

from pathlib import Path

from app.config import settings

from app.core.consensus import detect_coverage

from app.core.plate import (
    assess_plate,
    is_empty_scene_ocr,
    normalize_plate,
    plate_shape_score,
)

from app.services.camera_lpr import camera_contract

_lock = threading.Lock()

_engine = None

_warm_engine = None

_fastalpr_error = ""

_engine_error = ""

_dll_directory_handles = []

_native_runtime_prepared = False

DETECTOR_MODEL = "yolo-v9-t-384-license-plate-end2end"

DETECTOR_ONNX = "yolo-v9-t-384-license-plates-end2end.onnx"

OCR_MODEL = "cct-xs-v2-global-model"

OCR_ONNX = "cct_xs_v2_global.onnx"

OCR_CONFIG = "cct_xs_v2_global_plate_config.yaml"

MIN_PLATE_CHARS = 5

MIN_PLATE_ASPECT = 1.35

MAX_PLATE_ASPECT = 8.0

MIN_PLATE_WIDTH_PX = 24

MIN_PLATE_HEIGHT_PX = 8
