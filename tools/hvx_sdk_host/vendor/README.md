Optional extra copies of the vendor SDK on a Windows test PC.

The camera manufacturer's SDK (QY NetSDK, `NetSDK.dll` and its matched x86 DLLs) lives here for kit builds and developer runs. It is never taken from the legacy ParkWatch package. Installed kits load it from `<install>\vendor` (`SMARTPARK_HVX_VENDOR_DIR`).

Expected main file if you use this fallback: `NetSDK.dll`.

The SDK is x86: run `hvx_host.py` with 32-bit Python.
