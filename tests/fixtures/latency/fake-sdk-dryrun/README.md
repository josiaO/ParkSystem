# Sample latency trace (fake SDK, Ubuntu)

Produced by running the real host code on the fake NetSDK and the capture
driver against it, then thinning the per-frame records (one in six kept):

```bash
SMARTPARK_HVX_PORT=18765 python tools/hvx_sdk_host/hvx_host.py --fake-sdk &
python tools/latency_capture.py --host-url http://127.0.0.1:18765 --out <dir> \
  --handle 1 --pulses 3 --spacing 1 --viewers 3 --saturate --passive-seconds 3 --yes
python tools/latency_report.py <dir> <host trace dir>
```

The numbers describe a developer laptop and a fake DLL. They are not
measurements of the Windows rig.
