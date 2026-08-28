# OpenCV and SoftDog

## OpenCV

SmartPark **does not** use OpenCV for live video, SDK login, or gate pulses.

It is an **optional helper for FastALPR only**: `app/services/alpr.py` `_boost_contrast()` runs CLAHE on a JPEG if `cv2` imports. Native camera plates never go through OpenCV.

| | With OpenCV | Without OpenCV |
|---|---|---|
| HVX login / live JPEG / GPIO | Unchanged | Unchanged |
| Native plates | Unchanged | Unchanged |
| FastALPR button / Simulation OCR | Slightly better on dark or low-contrast photos | Still runs on Pillow → numpy BGR |
| RAM / USB kit size | `opencv-python-headless` is a large wheel | Smaller install |

If `cv2` is missing, contrast boost is skipped (`return None`) and FastALPR continues. Removing the package is safe for the parking engine; keep it if you rely on local OCR in poor light.

Default ALPR mode is `NATIVE_ONLY`. FastALPR is not run on every stream.

## SoftDog

Two different things share similar names:

### Vendor USB license (SoftDog / SuperDog / SenseShield)

Many QY / OcxConfig / NetSDK installations require a **USB license dongle** on the Windows PC. `NetSDK.dll` talks to that dongle. SmartPark does **not** implement or emulate SoftDog.

- Plug the dongle into the machine that runs the **32-bit HVX host**.
- If login fails with a license/dongle error, the SDK — not FastAPI — is refusing.
- Do not try to wrap SoftDog inside Python adapters.

You can use it here in that sense: it is a vendor requirement sitting **under** the host, same as `NetSDK.dll`.

### Linux `softdog` (kernel watchdog)

That is a timer that reboots a machine if software stops kicking it. SmartPark on Windows uses **scheduled-task restart** for Site Service and the HVX host instead. We do not use Linux softdog. A hardware watchdog on the parking PC is an operations choice, not part of the camera adapter layer.
