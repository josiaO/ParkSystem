"""HTTP boundaries and the composed Site Service runtime.

``app.api_main`` remains the public ASGI compatibility path. New HTTP
subsystems belong in this package; the legacy implementation is partitioned
under ``runtime_parts`` while its module namespace remains patch-compatible.
"""
