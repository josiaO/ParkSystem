Optional extra copies of the vendor SDK on a Windows test PC.

SmartPark loads `OcxConfig/` at the repo root first (`NetSDK.dll` and its x86 dependencies). This folder is only a fallback.

Expected main file if you use this fallback: `NetSDK.dll`.

The SDK is x86: run `hvx_host.py` with 32-bit Python.
